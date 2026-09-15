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
    """LibreOffice 无界面转换；独立 UserInstallation → 进程归属本任务，可终止。"""

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

    def __init__(self):
        self._bin = None

    def _find_bin(self) -> Optional[Path]:
        if self._bin is not None:
            return self._bin
        for cand in self._CANDIDATES:
            if "/" in cand:
                if Path(cand).exists():
                    self._bin = Path(cand)
                    return self._bin
            else:
                found = shutil.which(cand)
                if found:
                    self._bin = Path(found)
                    return self._bin
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
            return EngineInfo(self.ENGINE_ID, self.NAME, True,
                              version=version, detail=bin_path.as_posix())
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
    """macOS Microsoft Word：JXA 分阶段自动化（详见 design.md 决策 2/6/7）。"""

    ENGINE_ID = "word-jxa"
    NAME = "Microsoft Word (JXA)"
    WORD_APP = Path("/Applications/Microsoft Word.app")
    MER_PATTERN = "SharedSupport/Microsoft Error Reporting.app/Contents/MacOS"

    JXA_ENSURE_READY = r"""
function run() {
    var app = Application('com.microsoft.Word');
    var wasRunning = app.running();
    app.includeStandardAdditions = true;
    try {
        if (!wasRunning) { app.launch(); }
        app.activate();
    } catch (e) {
        return JSON.stringify({ok: false, error: String(e), wasRunning: wasRunning});
    }
    return JSON.stringify({ok: true, wasRunning: wasRunning});
}
"""

    JXA_OPEN_SAVE = r"""
function run(argv) {
    var inPath = argv[0];
    var outPath = argv[1];
    var app = Application('com.microsoft.Word');
    try {
        app.activate();
        app.open(inPath);
        app.activeDocument.saveAs({ fileName: outPath, fileFormat: 'format PDF' });
    } catch (e) {
        try { app.activeDocument.close({ saving: 'no' }); } catch (e2) {}
        return JSON.stringify({ok: false, error: String(e)});
    }
    try { app.activeDocument.close({ saving: 'no' }); } catch (e3) {}
    return JSON.stringify({ok: true});
}
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
            return EngineInfo(self.ENGINE_ID, self.NAME, True,
                              version=version, detail=str(self.WORD_APP))
        except Exception as exc:  # noqa: BLE001
            return EngineInfo(self.ENGINE_ID, self.NAME, False,
                              detail=f"探测失败: {exc}")

    # ── JXA 辅助 ────────────────────────────────────────────────────
    @staticmethod
    def _jxa(script: str, args: list, timeout_s: float):
        cmd = ["osascript", "-l", "JavaScript", "-"] + args
        try:
            proc = subprocess.run(cmd, input=script, capture_output=True,
                                  text=True, timeout=timeout_s)
        except subprocess.TimeoutExpired:
            return None, KIND_TIMEOUT
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": f"osascript 执行异常: {exc}"}, KIND_CONVERT
        stdout = (proc.stdout or "").strip()
        try:
            payload = json.loads(stdout.splitlines()[-1]) if stdout else {}
        except (ValueError, IndexError):
            payload = {"ok": False,
                       "error": f"无法解析 JXA 输出: {stdout[:120]}"}
        return payload, None

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

        try:
            return self._convert_staged(work_copy, out_pdf, staged_pdf,
                                        timeout_s, cancel_event, mer_note)
        finally:
            shutil.rmtree(self._stage_dir, ignore_errors=True)

    def _convert_staged(self, work_copy, out_pdf, staged_pdf, timeout_s,
                        cancel_event, mer_note) -> dict:
        payload, err = self._jxa(self.JXA_ENSURE_READY, [], min(30, timeout_s))
        if cancel_event is not None and cancel_event.is_set():
            return _result(False, KIND_CANCELLED, "已取消")
        if err is not None or not payload.get("ok"):
            msg = str(payload.get("error", "")) if payload else f"启动阶段超时({err})"
            if "-1743" in msg:
                return _result(False, KIND_PERMISSION,
                               "自动化权限被拒：需在系统设置中允许本应用控制 Microsoft Word")
            return _result(False, err or KIND_CONVERT, f"启动 Word 失败: {msg}")
        we_launched = not payload.get("wasRunning", True)

        deadline = time.monotonic() + 30
        while not self._word_running() and time.monotonic() < deadline:
            if cancel_event is not None and cancel_event.is_set():
                return _result(False, KIND_CANCELLED, "已取消",
                               cleanup_note=self._best_effort_quit(we_launched))
            time.sleep(0.5)
        time.sleep(5)  # 首启/恢复弹窗静置窗口

        payload, err = self._jxa(self.JXA_OPEN_SAVE,
                                 [work_copy.as_posix(), staged_pdf.as_posix()],
                                 timeout_s)
        cleanup = self._best_effort_quit(we_launched)
        if err == KIND_TIMEOUT or (payload and not payload.get("ok")
                                   and "-1712" in str(payload.get("error"))):
            return _result(False, KIND_TIMEOUT,
                           "Word 保存超时：存在待处理的模态弹窗（登录/激活/文件访问确认），"
                           "请处理后重试，或手动导出 PDF", cleanup_note=cleanup)
        if err is not None:
            return _result(False, err, str(payload) if payload else "转换失败",
                           cleanup_note=cleanup)
        if not payload.get("ok"):
            msg = str(payload.get("error", ""))
            kind = KIND_PERMISSION if "-1743" in msg else KIND_CONVERT
            return _result(False, kind, msg, cleanup_note=cleanup)
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
