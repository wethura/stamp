"""Word 转换引擎后端。

与 scripts/word_probe 的探测实现同源；产品化差异：
- convert 返回统一的 dict 结果（ok / error_kind / error_detail / pdf_path）
- 支持 cancel_event（soffice 为本任务子进程可终止；COM 调用中途不可中断，
  自启实例由 watchdog 兜底退出，共享实例仅放弃结果）
- word-jxa 保留 MER 清退、分阶段限时与容器暂存策略（P0 实测根因）
- Windows：Word / WPS 走 COM（spec P0.2：Word Word.Application；WPS
  kwps.application，接口与 Word 同源，ExportAsFixedFormat 导出 PDF）
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .errors import (
    KIND_CANCELLED,
    KIND_CONVERT,
    KIND_ENGINE_MISSING,
    KIND_PERMISSION,
    KIND_TIMEOUT,
)

DEFAULT_TIMEOUT_S = 120.0

# Word 脚本自动化路径的「防呆开关」（2026-09-17 真机诊断后默认关闭=启用引擎）：
# Word 16.112.4 / macOS 26 空启动会停在模态的开始画面（图库），阻塞后续全部
# AppleEvent——save as -1708「信息无法识别」、quit -128、文档属性全 null；
# JXA 用 POSIX 字符串路径 open 还会弹「找不到文件」。可靠配方（已真机验证）：
# LaunchServices 带文档启动 + AppleScript save as。若未来 Word 版本再现
# save as 被拒收，置 True 即可整体停用该后端；STAMPTOOL_ENABLE_WORD_JXA=1
# 为人工复核保留的强制启用口。
WORD_JXA_SAVEAS_BROKEN = False
_WORD_JXA_OVERRIDE_ENV = "STAMPTOOL_ENABLE_WORD_JXA"

# Windows 注册表模块：函数内 import 对 PyInstaller 静态分析不可靠，
# 顶层条件导入让打包器必然收录；非 Windows 平台不触发。
if sys.platform == "win32":  # pragma: no cover - 平台分支
    import winreg  # noqa: F401

# GUI 程序调用外部进程时避免闪出控制台窗口（Windows 打包版的常见噪音）
_NO_WINDOW_FLAGS = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0


@dataclass
class EngineInfo:
    engine_id: str
    name: str
    available: bool
    version: str = ""
    detail: str = ""
    manual_path_only: bool = False


def _result(ok: bool, error_kind: str = None, error_detail: str = "",
            pdf_path: str = None, cleanup_note: str = "") -> dict:
    return {"ok": ok, "error_kind": error_kind, "error_detail": error_detail,
            "pdf_path": pdf_path, "cleanup_note": cleanup_note}


def _read_bundle_version(plist_path: Path) -> str:
    try:
        out = subprocess.run(
            ["defaults", "read", str(plist_path), "CFBundleShortVersionString"],
            capture_output=True, text=True, timeout=10,
        )
        return out.stdout.strip()
    except Exception:  # noqa: BLE001
        return ""


class SofficeEngine:
    """LibreOffice 无界面转换；独立 UserInstallation → 进程归属本任务，可终止。

    查找优先级：STAMPTOOL_SOFFICE 环境覆盖 > 应用自管理驱动
    （见 driver_manager，用户可选下载）> 系统安装路径。
    """

    ENGINE_ID = "soffice"
    NAME = "LibreOffice (无界面)"
    PROBE_TIMEOUT_S = 8.0  # 能力探测要快；转换阶段另用 120s
    _CANDIDATES = (
        "/Applications/LibreOffice.app/Contents/MacOS/soffice",
        "/usr/bin/soffice",
        "C:/Program Files/LibreOffice/program/soffice.exe",
        "C:/Program Files (x86)/LibreOffice/program/soffice.exe",
        "soffice",
    )

    def __init__(self, driver_manager=None):
        self._bin = None
        self._source = ""
        if driver_manager is None:
            from .driver_manager import DriverManager
            driver_manager = DriverManager()
        self._drivers = driver_manager

    def _find_bin(self) -> Optional[Path]:
        if self._bin is not None:
            return self._bin
        from . import paths as lo_paths
        # 1) 测试/高级用户覆盖
        override = os.environ.get("STAMPTOOL_SOFFICE")
        if override:
            candidate = Path(override)
            if candidate.exists():
                self._bin, self._source = candidate, "环境覆盖"
                return self._bin
        # 2) 用户手动指定的安装位置（探测不到时的第二层）
        try:
            manual = lo_paths.get_manual_soffice()
        except Exception:  # noqa: BLE001
            manual = None
        if manual is not None:
            self._bin, self._source = manual, "手动指定"
            return self._bin
        # 3) 应用自管理的下载驱动
        try:
            managed = self._drivers.managed_soffice_path()
        except Exception:  # noqa: BLE001
            managed = None
        if managed is not None:
            self._bin, self._source = managed, "内置下载"
            return self._bin
        # 4) 系统安装（含注册表/每用户目录等全量候选，扫描过程落日志）
        candidates = lo_paths.candidate_paths()
        for cand in candidates:
            if cand.exists():
                self._bin, self._source = cand, "系统安装"
                lo_paths.log_detection_scan(candidates, cand, self._source)
                return self._bin
        found_in_path = shutil.which("soffice")
        if found_in_path:
            self._bin, self._source = Path(found_in_path), "系统 PATH"
            lo_paths.log_detection_scan(candidates, self._bin, self._source)
            return self._bin
        lo_paths.log_detection_scan(candidates, None, "自动探测")
        return None

    @property
    def engine_id(self) -> str:
        return self.ENGINE_ID

    def probe(self) -> EngineInfo:
        # 探测绝不抛异常，且单个候选超时必须短：LibreOffice 首次启动
        # 可能弹窗/初始化，30 秒会让「检查转换引擎」卡死界面
        try:
            bin_path = self._find_bin()
            if bin_path is None:
                return EngineInfo(self.ENGINE_ID, self.NAME, False,
                                  detail="未找到 soffice")
            version = ""
            try:
                out = subprocess.run([bin_path.as_posix(), "--version"],
                                     capture_output=True, text=True,
                                     timeout=self.PROBE_TIMEOUT_S,
                                     creationflags=_NO_WINDOW_FLAGS)
                lines = (out.stdout or out.stderr).strip().splitlines()
                version = lines[0] if lines else ""
            except Exception:  # noqa: BLE001  超时/启动失败一律降级
                pass
            # 即使取不到版本，可执行文件存在即可用（转换阶段还有完整校验）
            detail = bin_path.as_posix()
            if self._source in ("内置下载", "手动指定"):
                detail += f" · {self._source}"
            return EngineInfo(self.ENGINE_ID, self.NAME, True,
                              version=version, detail=detail)
        except Exception as exc:  # noqa: BLE001
            return EngineInfo(self.ENGINE_ID, self.NAME, False,
                              detail=f"探测失败: {exc}")

    def convert(self, work_copy: Path, out_pdf: Path, timeout_s: float = DEFAULT_TIMEOUT_S,
                cancel_event=None) -> dict:
        bin_path = self._find_bin()
        if bin_path is None:
            return _result(False, KIND_ENGINE_MISSING, "未找到 soffice 可执行文件")

        out_dir = out_pdf.parent
        profile = tempfile.mkdtemp(prefix="stamp-soffice-")
        cmd = [
            bin_path.as_posix(),
            f"-env:UserInstallation=file://{profile}",
            "--headless", "--norestore", "--nolockcheck",
            "--convert-to", "pdf:writer_pdf_Export",
            "--outdir", out_dir.as_posix(),
            work_copy.as_posix(),
        ]
        deadline = time.monotonic() + timeout_s
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                creationflags=_NO_WINDOW_FLAGS)
        try:
            while proc.poll() is None:
                if cancel_event is not None and cancel_event.is_set():
                    proc.terminate()
                    try:
                        proc.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                    return _result(False, KIND_CANCELLED, "已取消")
                if time.monotonic() > deadline:
                    proc.terminate()
                    try:
                        proc.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                    return _result(False, KIND_TIMEOUT,
                                   f"转换超过 {int(timeout_s)} 秒，已终止")
                time.sleep(0.1)
        finally:
            shutil.rmtree(profile, ignore_errors=True)

        produced = out_dir / (work_copy.stem + ".pdf")
        if proc.returncode != 0 or not produced.exists():
            detail = ""
            try:
                detail = (proc.stderr.read() or proc.stdout.read() or b"").decode(
                    "utf-8", "ignore").strip()[:300]
            except Exception:  # noqa: BLE001
                pass
            return _result(False, KIND_CONVERT,
                           detail or f"soffice 退出码 {proc.returncode}，未生成 PDF")
        if produced.resolve() != out_pdf.resolve():
            produced.rename(out_pdf)
        return _result(True, pdf_path=str(out_pdf),
                       cleanup_note="soffice 单次转换自动退出，配置目录已删除")


class WordJxaEngine:
    """macOS Microsoft Word 自动化（engine_id 沿用 word-jxa）。

    2026-09-17 重写自动化路径（真机诊断，见 design.md 决策 7）：
    - 绝不空启动 Word（会停在模态开始画面，阻塞全部 AppleEvent）；
      用 LaunchServices 带文档启动（open -a Word <file>）。
    - 另存用 AppleScript `save as active document file format format PDF`
      （真机验证通过）；JXA 字符串路径 open 会触发「找不到文件」弹窗，弃用。
    - 输出落在 Word 沙盒容器内的暂存目录，避免「授权访问」弹窗。
    """

    ENGINE_ID = "word-jxa"
    NAME = "Microsoft Word"
    WORD_APP = Path("/Applications/Microsoft Word.app")
    MER_PATTERN = "SharedSupport/Microsoft Error Reporting.app/Contents/MacOS"

    AS_ACTIVE_DOC_NAME = r"""
on run
	tell application "Microsoft Word"
		if (count of documents) = 0 then return ""
		try
			return name of active document
		on error
			return ""
		end try
	end tell
end run
"""

    AS_SAVE_AS_PDF = r"""
on run argv
	tell application "Microsoft Word"
		save as active document file format format PDF file name (item 1 of argv)
	end tell
end run
"""

    AS_CLOSE_ACTIVE = r"""
on run
	tell application "Microsoft Word"
		try
			close active document saving no
		end try
	end tell
end run
"""

    def __init__(self):
        self._stage_dir = Path.home() / ("Library/Containers/com.microsoft.word/"
                                         "Data/Documents/WordConverterStage")

    @property
    def engine_id(self) -> str:
        return self.ENGINE_ID

    def probe(self) -> EngineInfo:
        try:
            if not self.WORD_APP.exists():
                return EngineInfo(self.ENGINE_ID, self.NAME, False,
                                  detail="未安装 /Applications/Microsoft Word.app")
            version = _read_bundle_version(self.WORD_APP / "Contents/Info.plist")
            if WORD_JXA_SAVEAS_BROKEN and not os.environ.get(_WORD_JXA_OVERRIDE_ENV):
                return EngineInfo(self.ENGINE_ID, self.NAME, False, version=version,
                                  detail="此 Word 版本的脚本导出 PDF 接口失效（-1708），"
                                         "引擎已停用；可在 Word 中导出 PDF 后拖入，"
                                         "或使用 LibreOffice")
            return EngineInfo(self.ENGINE_ID, self.NAME, True,
                              version=version, detail=str(self.WORD_APP))
        except Exception as exc:  # noqa: BLE001
            return EngineInfo(self.ENGINE_ID, self.NAME, False,
                              detail=f"探测失败: {exc}")

    # ── AppleScript 辅助 ────────────────────────────────────────────
    @staticmethod
    def _osa(script: str, args: list, timeout_s: float):
        """执行 AppleScript（stdin 传入，argv 传参），返回 (stdout, 错误)。"""
        cmd = ["osascript", "-"] + args
        try:
            proc = subprocess.run(cmd, input=script, capture_output=True,
                                  text=True, timeout=timeout_s)
        except subprocess.TimeoutExpired:
            return None, KIND_TIMEOUT
        except Exception as exc:  # noqa: BLE001
            return None, f"osascript 执行异常: {exc}"
        if proc.returncode != 0:
            return None, (proc.stderr or "osascript 失败").strip()
        return (proc.stdout or "").strip(), None

    @staticmethod
    def _word_running() -> bool:
        try:
            out = subprocess.run(
                ["osascript", "-l", "JavaScript", "-e",
                 "Application('com.microsoft.Word').running()"],
                capture_output=True, text=True, timeout=10)
            return out.stdout.strip() == "true"
        except Exception:  # noqa: BLE001
            return False

    @classmethod
    def _dismiss_error_reporter(cls) -> str:
        try:
            out = subprocess.run(["pgrep", "-f", cls.MER_PATTERN],
                                 capture_output=True, text=True, timeout=5)
            if not out.stdout.strip():
                return ""
        except Exception:  # noqa: BLE001
            return ""
        try:
            subprocess.run(["osascript", "-e",
                            'tell application "Microsoft Error Reporting" to quit'],
                           capture_output=True, text=True, timeout=8)
        except Exception:  # noqa: BLE001
            pass
        time.sleep(1)
        subprocess.run(["pkill", "-TERM", "-f", cls.MER_PATTERN], capture_output=True)
        time.sleep(1)
        return "已退出 Microsoft Error Reporting（其模态报告窗会阻塞自动化）"

    def _best_effort_quit(self, we_launched: bool) -> str:
        if not we_launched:
            return "Word 原本就在运行，保持不动"
        try:
            subprocess.run(["osascript", "-l", "JavaScript", "-e",
                            "Application('com.microsoft.Word').quit()"],
                           capture_output=True, text=True, timeout=8)
        except Exception:  # noqa: BLE001
            pass
        if self._word_running():
            return "尝试退出 Word 未成功（可能有待处理弹窗），需人工确认后关闭"
        return "已退出本任务启动的 Word"

    def probe_only_note(self) -> str:
        return "已检测到 WPS，当前版本暂不能自动转换。请在 WPS 中导出 PDF 后拖入本工具。"

    def convert(self, work_copy: Path, out_pdf: Path,
                timeout_s: float = DEFAULT_TIMEOUT_S, cancel_event=None) -> dict:
        if cancel_event is not None and cancel_event.is_set():
            return _result(False, KIND_CANCELLED, "已取消")

        mer_note = self._dismiss_error_reporter()
        self._stage_dir.mkdir(parents=True, exist_ok=True)
        staged_pdf = self._stage_dir / f"{out_pdf.stem}-{os.getpid()}.pdf"
        we_launched = not self._word_running()

        try:
            return self._convert_staged(work_copy, out_pdf, staged_pdf,
                                        timeout_s, cancel_event, mer_note,
                                        we_launched)
        finally:
            shutil.rmtree(self._stage_dir, ignore_errors=True)

    def _convert_staged(self, work_copy, out_pdf, staged_pdf, timeout_s,
                        cancel_event, mer_note, we_launched) -> dict:
        # 1) LaunchServices 带文档启动/唤起——绝不让 Word 空启动到开始画面。
        #    对未运行/已运行的实例都有效（odoc 事件走系统规范路径）。
        try:
            subprocess.run(["open", "-a", str(self.WORD_APP), str(work_copy)],
                           capture_output=True, timeout=30, check=True)
        except Exception as exc:  # noqa: BLE001
            return _result(False, KIND_CONVERT,
                           f"无法启动 Word 打开文档: {exc}",
                           cleanup_note=self._best_effort_quit(we_launched))

        # 2) 轮询直到目标文档真正打开。开始画面/登录/激活/「找不到文件」
        #    等弹窗会让文档一直打不开——超时给出可操作的指引。
        expected = work_copy.name
        deadline = time.monotonic() + min(60.0, max(timeout_s, 10.0))
        doc_ready = False
        while time.monotonic() < deadline:
            if cancel_event is not None and cancel_event.is_set():
                return _result(False, KIND_CANCELLED, "已取消",
                               cleanup_note=self._best_effort_quit(we_launched))
            name, err = self._osa(self.AS_ACTIVE_DOC_NAME, [], 10)
            if err and "-1743" in err:
                return _result(False, KIND_PERMISSION,
                               "自动化权限被拒：需在系统设置中允许本应用控制 "
                               "Microsoft Word",
                               cleanup_note=self._best_effort_quit(we_launched))
            if name == expected:
                doc_ready = True
                break
            time.sleep(1)
        if not doc_ready:
            return _result(False, KIND_TIMEOUT,
                           "Word 未能在时限内打开文档：可能停留在开始画面或有"
                           "待处理弹窗（登录/激活/文件访问确认/恢复文档）。"
                           "请切到 Word 处理后重试，或改用 LibreOffice 引擎",
                           cleanup_note=self._best_effort_quit(we_launched))

        # 3) 脚本另存为 PDF（AppleScript save as，2026-09-17 真机验证通过）
        out, err = self._osa(self.AS_SAVE_AS_PDF, [staged_pdf.as_posix()],
                             timeout_s)
        cleanup = self._best_effort_quit(we_launched)
        self._osa(self.AS_CLOSE_ACTIVE, [], 15)
        if err == KIND_TIMEOUT or (err and "-1712" in err):
            return _result(False, KIND_TIMEOUT,
                           "Word 保存超时：存在待处理的模态弹窗（登录/激活/"
                           "文件访问确认），请处理后重试，或手动导出 PDF",
                           cleanup_note=cleanup)
        if err is not None:
            if "-1708" in err or "信息无法识别" in err:
                err = ("Word 拒绝了脚本导出命令（-1708）：请切到 Word 处理可能的"
                       "弹窗/开始画面后重试，或改用 LibreOffice 引擎。")
            return _result(False, KIND_CONVERT, err, cleanup_note=cleanup)
        if not staged_pdf.exists():
            return _result(False, KIND_CONVERT, "Word 报告成功但 PDF 未生成",
                           cleanup_note=cleanup)

        shutil.move(str(staged_pdf), str(out_pdf))
        note = cleanup + (f"；{mer_note}" if mer_note else "")
        return _result(True, pdf_path=str(out_pdf), cleanup_note=note)


class WpsManualEngine:
    """macOS/其他平台 WPS：仅探测，接口未验证 → 手动路径。"""

    ENGINE_ID = "wps"
    NAME = "WPS Office"
    _APP_CANDIDATES = (
        Path("/Applications/wpsoffice.app"),
        Path("C:/Program Files/Kingsoft/WPS Office/ksolaunch.exe"),
    )

    @property
    def engine_id(self) -> str:
        return self.ENGINE_ID

    def probe(self) -> EngineInfo:
        try:
            for app in self._APP_CANDIDATES:
                if app.exists():
                    version = ""
                    if sys.platform == "darwin":
                        version = _read_bundle_version(app / "Contents/Info.plist")
                    return EngineInfo(self.ENGINE_ID, self.NAME, True,
                                      version=version, detail=str(app),
                                      manual_path_only=True)
            return EngineInfo(self.ENGINE_ID, self.NAME, False, detail="未检测到 WPS")
        except Exception as exc:  # noqa: BLE001
            return EngineInfo(self.ENGINE_ID, self.NAME, False,
                              detail=f"探测失败: {exc}")

    def convert(self, work_copy, out_pdf, timeout_s=DEFAULT_TIMEOUT_S, cancel_event=None):
        return _result(False, KIND_CONVERT,
                       "已检测到 WPS，当前版本暂不能自动转换。请在 WPS 中导出 PDF 后拖入本工具。")


class ComEngineBase:
    """Windows COM 自动化基类：Word 与 WPS 共用（WPS 实现同源接口）。

    进程归属（spec 安全条款）：优先 DispatchEx 启动独立实例（本任务私有，
    可 Quit + watchdog 兜底）；仅当无法新建实例时才附着已运行实例
    （GetActiveObject），此时永不 Quit、超时只放弃结果。
    COM 调用中途不可中断；取消在调用间隙生效。
    """

    ENGINE_ID = ""
    NAME = ""
    PROG_IDS = ()
    WD_FORMAT_PDF = 17  # wdFormatPDF / wdExportFormatPDF

    # 可注入点（测试在非 Windows 平台桩掉这些方法）
    def _is_windows(self) -> bool:
        return sys.platform == "win32"

    def _load_com_modules(self):
        import pythoncom
        import win32com.client
        return pythoncom, win32com.client

    def _registry_has(self, prog_id: str) -> bool:
        # import 放在 try 内：打包版可能缺失 winreg（延迟导入对静态分析
        # 不友好），ImportError 若逃逸会直接崩掉整个应用
        try:
            import winreg
            winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, prog_id)
            return True
        except Exception:  # noqa: BLE001  ImportError / OSError / 其他
            return False

    def _probe_version(self, prog_id: str) -> str:
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, prog_id + r"\CurVer") as key:
                return winreg.QueryValueEx(key, "")[0]
        except Exception:  # noqa: BLE001
            return ""

    @property
    def engine_id(self) -> str:
        return self.ENGINE_ID

    def _first_registered(self) -> Optional[str]:
        return next((pid for pid in self.PROG_IDS if self._registry_has(pid)), None)

    def _registry_available(self) -> bool:
        """winreg 是否可用——打包缺失时探测结果必须能自我说明，
        否则会把「查不到注册表」误报成「未安装」，排障时误导。"""
        try:
            import winreg  # noqa: F401
            return True
        except Exception:  # noqa: BLE001
            return False

    def probe(self) -> EngineInfo:
        # 探测绝不抛异常：任何失败都降级为「不可用」，否则会连带
        # 拖垮 probe_all → 打开文档流程（打包版无控制台，表现为闪退）
        try:
            if not self._is_windows():
                return EngineInfo(self.ENGINE_ID, self.NAME, False, detail="仅 Windows 可用")
            if not self._registry_available():
                return EngineInfo(self.ENGINE_ID, self.NAME, False,
                                  detail="无法读取注册表（winreg 不可用），无法检测安装")
            prog_id = self._first_registered()
            if prog_id is None:
                return EngineInfo(self.ENGINE_ID, self.NAME, False, detail="未检测到已安装")
            return EngineInfo(self.ENGINE_ID, self.NAME, True,
                              version=self._probe_version(prog_id),
                              detail=f"COM {prog_id}")
        except Exception as exc:  # noqa: BLE001
            return EngineInfo(self.ENGINE_ID, self.NAME, False,
                              detail=f"探测失败: {exc}")

    def convert(self, work_copy: Path, out_pdf: Path,
                timeout_s: float = DEFAULT_TIMEOUT_S, cancel_event=None) -> dict:
        if not self._is_windows():
            return _result(False, KIND_ENGINE_MISSING, "仅 Windows 可用")
        if cancel_event is not None and cancel_event.is_set():
            return _result(False, KIND_CANCELLED, "已取消")
        prog_id = self._first_registered()
        if prog_id is None:
            return _result(False, KIND_ENGINE_MISSING, "未检测到已安装的 " + self.NAME)
        try:
            pythoncom, client = self._load_com_modules()
        except ImportError as exc:
            return _result(False, KIND_ENGINE_MISSING,
                           f"缺少 pywin32 组件（{exc}），无法调用 {self.NAME}")

        app = None
        doc = None
        we_launched = True
        watchdog = None
        try:
            pythoncom.CoInitialize()
            try:
                app = client.GetActiveObject(prog_id)
                we_launched = False  # 附着用户实例：永不 Quit
            except Exception:  # noqa: BLE001
                app = client.DispatchEx(prog_id)
            try:
                app.Visible = False
                app.DisplayAlerts = 0
            except Exception:  # noqa: BLE001  WPS 部分属性可能不支持
                pass

            if we_launched:
                # COM 阻塞调用无法响应取消；独立实例超时后强制退出防挂死
                watchdog = threading.Timer(
                    timeout_s + 10,
                    lambda: _safe_call(app.Quit))
                watchdog.daemon = True
                watchdog.start()

            doc = app.Documents.Open(str(work_copy), ReadOnly=True,
                                     AddToRecentFiles=False)
            try:
                doc.ExportAsFixedFormat(str(out_pdf), self.WD_FORMAT_PDF)
            except Exception:  # noqa: BLE001  老版本/WPS 回退到 SaveAs2
                doc.SaveAs2(str(out_pdf), FileFormat=self.WD_FORMAT_PDF)

            if cancel_event is not None and cancel_event.is_set():
                return _result(False, KIND_CANCELLED, "已取消（丢弃迟到结果）")
            if not out_pdf.exists():
                return _result(False, KIND_CONVERT,
                               f"{self.NAME} 未生成 PDF（可能存在待处理的弹窗或文档受保护）")
            return _result(True, pdf_path=str(out_pdf))
        except Exception as exc:  # noqa: BLE001
            return _result(False, KIND_CONVERT, f"COM 转换失败: {exc}")
        finally:
            if watchdog is not None:
                watchdog.cancel()
            _safe_call(lambda: doc.Close(False))
            if app is not None and we_launched:
                _safe_call(app.Quit)
            _safe_call(pythoncom.CoUninitialize)


class WordComEngine(ComEngineBase):
    ENGINE_ID = "word-com"
    NAME = "Microsoft Word"
    PROG_IDS = ("Word.Application", "Word.Application.16", "Word.Application.15")


class WpsComEngine(ComEngineBase):
    # 个人版注册 wps.application / KWPS.Application；企业版 kwps.application
    ENGINE_ID = "wps-com"
    NAME = "WPS Office"
    PROG_IDS = ("kwps.application", "KWPS.Application",
                "wps.application", "WPS.Application")


def _safe_call(fn):
    try:
        fn()
    except Exception:  # noqa: BLE001  清理路径尽力而为
        pass


if sys.platform == "win32":
    DEFAULT_ENGINES = (SofficeEngine(), WordComEngine(), WpsComEngine())
else:
    DEFAULT_ENGINES = (SofficeEngine(), WordJxaEngine(), WpsManualEngine())
