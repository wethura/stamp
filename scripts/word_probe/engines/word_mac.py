"""macOS Microsoft Word 引擎：JXA / Apple Events 自动化转换。

对应 spec P0.3。2026-09-14 实测教训（Word 16.112.4 / macOS 26.6 arm64）：

- Apple Events 通路本身可用（running/quit 正常应答），但 Word 首启或存在
  模态弹窗（登录/授权/文件访问确认）时会阻塞 open/save 事件，表现为
  -1712 AppleEvent 超时或调用挂起；quit 会被弹窗以 -128 取消。
- 因此拆分为「就绪等待 → open+save+close → 退出」三个阶段，分别限时，
  便于定位卡点；仅当 Word 由本任务启动时才负责退出，退出失败如实上报。
"""

import json
import os
import shutil
import subprocess
import time
from pathlib import Path

from .base import (
    ERR_CONVERT,
    ERR_INTERNAL,
    ERR_PERMISSION,
    ERR_TIMEOUT,
    DEFAULT_TIMEOUT_S,
    ConvertResult,
    EngineInfo,
    sha256_of,
)

WORD_APP = Path("/Applications/Microsoft Word.app")

# 阶段 1：确保 Word 已启动并来到前台
JXA_ENSURE_READY = r"""
function run(argv) {
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

# 阶段 2：打开工作副本 → 另存 PDF（容器暂存）→ 不保存关闭
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

# Word 崩溃报告器：其模态「发送报告」窗会阻塞 Word 的全部 Apple Events，
# 且由本探测的异常退出循环触发。无用户文档，退出安全（2026-09-14 实测根因）。
MER_PROCESS_PATTERN = "SharedSupport/Microsoft Error Reporting.app/Contents/MacOS"


def _dismiss_error_reporter() -> str:
    """检测并退出 Microsoft Error Reporting。返回动作说明（未检测到则空串）。"""
    try:
        out = subprocess.run(["pgrep", "-f", MER_PROCESS_PATTERN],
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
    subprocess.run(["pkill", "-TERM", "-f", MER_PROCESS_PATTERN], capture_output=True)
    time.sleep(1)
    return "已退出 Microsoft Error Reporting（其模态报告窗会阻塞自动化）"


def _jxa(script: str, args: list, timeout_s: float):
    """Run one JXA phase; returns (payload, error_kind)."""
    cmd = ["osascript", "-l", "JavaScript", "-"] + args
    try:
        proc = subprocess.run(cmd, input=script, capture_output=True,
                              text=True, timeout=timeout_s)
    except subprocess.TimeoutExpired:
        return None, ERR_TIMEOUT
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"osascript 执行异常: {exc}"}, ERR_INTERNAL

    stdout = (proc.stdout or "").strip()
    try:
        payload = json.loads(stdout.splitlines()[-1]) if stdout else {}
    except (ValueError, IndexError):
        payload = {"ok": False,
                   "error": f"无法解析 JXA 输出: {stdout[:120]} / {(proc.stderr or '')[:120]}"}
        return payload, ERR_CONVERT
    return payload, None


def probe() -> EngineInfo:
    if not WORD_APP.exists():
        return EngineInfo("word-jxa", "Microsoft Word (JXA)", False,
                          detail="未安装 /Applications/Microsoft Word.app")
    version = ""
    try:
        out = subprocess.run(
            ["defaults", "read", str(WORD_APP / "Contents/Info.plist"),
             "CFBundleShortVersionString"],
            capture_output=True, text=True, timeout=10,
        )
        version = out.stdout.strip()
    except Exception:
        pass
    return EngineInfo("word-jxa", "Microsoft Word (JXA)", True,
                      version=version, detail=str(WORD_APP))


def convert(work_copy: Path, out_pdf: Path, timeout_s: float = DEFAULT_TIMEOUT_S) -> ConvertResult:
    result = ConvertResult(ok=False, engine_id="word-jxa",
                           sample=work_copy.name,
                           source_sha_before=sha256_of(work_copy))

    # Word 是沙盒应用：对任意用户目录执行 saveAs 可能触发不可见的「授予访问」
    # 面板并阻塞 Apple Events。改为先存入其容器暂存目录（必定可写），再移回目标位置。
    stage_dir = Path.home() / "Library/Containers/com.microsoft.word/Data/Documents/WordProbeStage"
    staged_pdf = stage_dir / f"{out_pdf.stem}-{os.getpid()}.pdf"
    try:
        return _convert_staged(work_copy, out_pdf, staged_pdf, stage_dir, result)
    finally:
        shutil.rmtree(stage_dir, ignore_errors=True)


def _convert_staged(work_copy: Path, out_pdf: Path, staged_pdf: Path,
                    stage_dir: Path, result: ConvertResult) -> ConvertResult:
    stage_dir.mkdir(parents=True, exist_ok=True)
    mer_note = _dismiss_error_reporter()
    if mer_note:
        result.metrics["error_reporter_dismissed"] = mer_note

    # ── 阶段 1：启动并等待就绪（最多 30s + 5s 静置）────────────────
    payload, err = _jxa(JXA_ENSURE_READY, [], timeout_s=min(30, timeout_s))
    if err is not None or not payload.get("ok"):
        msg = str(payload.get("error", "")) if payload else f"阶段1超时({err})"
        result.error_kind = err or ERR_CONVERT
        result.error_detail = f"启动 Word 失败: {msg}"
        if "-1743" in msg:
            result.error_kind = ERR_PERMISSION
            result.error_detail = "自动化权限被拒（err -1743）：需在系统设置允许控制 Microsoft Word"
        return result
    we_launched = not payload.get("wasRunning", True)

    deadline = time.monotonic() + 30
    while not _word_running() and time.monotonic() < deadline:
        time.sleep(0.5)
    time.sleep(5)  # 首启界面/自动恢复弹窗静置窗口

    # ── 阶段 2：open + saveAs（容器暂存）+ close（整体限时）────────
    payload, err = _jxa(JXA_OPEN_SAVE,
                        [work_copy.as_posix(), staged_pdf.as_posix()],
                        timeout_s=timeout_s)
    if err == ERR_TIMEOUT or (payload and not payload.get("ok") and "-1712" in str(payload.get("error"))):
        result.error_kind = ERR_TIMEOUT
        result.error_detail = ("open/save 阶段 AppleEvent 超时：Word 存在待处理的"
                               "模态弹窗（登录/激活/文件访问确认），需人工处理后重试")
        result.cleanup_note = _best_effort_quit(we_launched)
        return result
    if err is not None:
        result.error_kind = err
        result.error_detail = str(payload) if payload else f"阶段2异常({err})"
        result.cleanup_note = _best_effort_quit(we_launched)
        return result
    if not payload.get("ok"):
        msg = str(payload.get("error", ""))
        result.error_kind = ERR_PERMISSION if "-1743" in msg else ERR_CONVERT
        result.error_detail = msg
        result.cleanup_note = _best_effort_quit(we_launched)
        return result

    if not staged_pdf.exists():
        result.error_kind = ERR_CONVERT
        result.error_detail = "JXA 报告成功但暂存 PDF 未生成"
        result.cleanup_note = _best_effort_quit(we_launched)
        return result

    shutil.move(str(staged_pdf), str(out_pdf))
    result.ok = True
    result.pdf_path = out_pdf.as_posix()
    result.metrics["we_launched_word"] = we_launched
    result.metrics["staged_in_container"] = True
    result.source_sha_after = sha256_of(work_copy)
    result.source_untouched = result.source_sha_before == result.source_sha_after
    result.cleanup_note = _best_effort_quit(we_launched)
    return result


def _word_running() -> bool:
    try:
        out = subprocess.run(
            ["osascript", "-l", "JavaScript", "-e",
             "Application('com.microsoft.Word').running()"],
            capture_output=True, text=True, timeout=10)
        return out.stdout.strip() == "true"
    except Exception:  # noqa: BLE001
        return False


def _best_effort_quit(we_launched: bool) -> str:
    """仅当 Word 由本任务启动时尝试退出；弹窗会以 -128 取消 quit，如实记录。"""
    if not we_launched:
        return "Word 原本就在运行，保持不动"
    try:
        subprocess.run(["osascript", "-l", "JavaScript", "-e",
                        "Application('com.microsoft.Word').quit()"],
                       capture_output=True, text=True, timeout=8)
    except Exception:  # noqa: BLE001
        pass
    if _word_running():
        return "尝试退出 Word 未成功（可能有待处理弹窗），需人工确认后关闭"
    return "已退出本任务启动的 Word"
