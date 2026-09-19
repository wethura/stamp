"""跨平台打印支持：把文件交给操作系统的打印管线。

设计立场（2026-09-19 用户纠偏后确立）：
- 不自造打印机选择/份数界面，也不枚举打印机——双面、份数、纸张、
  预设等能力因机而异，只有系统打印窗口知道全部；我们的职责是生成
  盖章文件并唤起系统打印。
- macOS：经 Preview 的标准 AppleEvent「print ... with print dialog」
  （见 Preview sdef：print 命令带 print dialog 布尔参数）弹出系统
  打印面板；用户取消/失败时降级为用默认应用打开。
- Windows：ShellExecute 的 print 动词（依赖文件关联，由关联程序
  的打印流程接管）；未注册 print 动词时回退为打开文件。
- Linux：桌面环境无统一打印对话框 CLI，PDF/图片直接入 CUPS 队列，
  其余格式用默认程序打开。
- 任何失败都不抛出、不阻断主流程，结果以 PrintOutcome 返回。
"""

import logging
import os
import subprocess
import sys
import time
from typing import NamedTuple

logger = logging.getLogger(__name__)

_DIALOG_ACK_S = 5.0       # osascript 早失败侦测窗口；面板开着属于正常
_DOC_READY_S = 6.0        # 等待 Preview 打开文档（冷启动需数秒）
_LP_TIMEOUT_S = 30.0      # lp 提交：正常瞬时完成，CUPS 忙时留余量

# 可直接交给打印管线的格式；xlsx 等办公格式改为用默认程序打开
_PRINTABLE_EXT = {".pdf", ".png", ".jpg", ".jpeg", ".gif", ".bmp",
                  ".tif", ".tiff"}


class PrintOutcome(NamedTuple):
    """一次打印提交的结果；message 可直接放状态栏。"""
    ok: bool          # 已入队 / 已交给可打印的程序 / 用户主动取消
    kind: str         # queued | dialog | opened | cancelled | error
    message: str


def _run(cmd, timeout: float) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def print_file(path: str) -> PrintOutcome:
    """把文件交给系统打印管线；绝不抛出，结果以 PrintOutcome 返回。"""
    if not os.path.exists(path):
        return PrintOutcome(False, "error", f"文件不存在，无法打印: {path}")
    try:
        if sys.platform == "darwin":
            return _print_macos(path)
        if sys.platform == "win32":
            return _print_windows(path)
        return _print_posix(path)
    except Exception as exc:  # noqa: BLE001
        logger.error("打印提交失败: %s", path, exc_info=True)
        return PrintOutcome(False, "error", f"打印失败: {exc}")


def _print_macos(path: str) -> PrintOutcome:
    ext = os.path.splitext(path)[1].lower()
    if ext not in _PRINTABLE_EXT:
        # xlsx 等格式 Preview 不认：交给 Excel/WPS 等默认程序
        return _open_with_default_app_posix(path)

    # 真机验证的完整链路（2026-09-19）：
    # 1) open 带文档唤起 Preview（LaunchServices 同时授予沙盒读权限）；
    # 2) 轮询等文档就位（Preview 冷启动需数秒）；
    # 3) 打印「已打开的文档对象」。不能按文件路径再次打印——文档已开
    #    着时 Preview 会报「未能打开文稿以进行打印」（二次打开冲突）。
    try:
        _run(["open", "-a", "Preview", path], 10.0)
    except Exception:  # noqa: BLE001
        logger.warning("open Preview 失败，退回按文件路径打印", exc_info=True)

    real = os.path.realpath(path)
    quoted = real.replace("\\", "\\\\").replace('"', '\\"')
    probe = (f'tell application "Preview" to count '
             f'(documents whose path is "{quoted}")')
    deadline = time.monotonic() + _DOC_READY_S
    ready = False
    while time.monotonic() < deadline:
        try:
            result = _run(["osascript", "-e", probe], 4.0)
        except Exception:  # noqa: BLE001  探测失败继续重试
            result = None
        if (result is not None and result.returncode == 0
                and result.stdout.strip().isdigit()
                and int(result.stdout.strip()) > 0):
            ready = True
            break
        time.sleep(0.4)

    if ready:
        script = (f'tell application "Preview" to print '
                  f'(first document whose path is "{quoted}") '
                  f'with print dialog')
    else:
        # 文档一直没就位（open 失败等）：退回按文件路径打印
        file_quoted = path.replace("\\", "\\\\").replace('"', '\\"')
        script = (f'tell application "Preview" to '
                  f'print POSIX file "{file_quoted}" with print dialog')
    logger.info("打印事件分支: ready=%s script=%s", ready, script)

    outcome = _run_print_event(script, path)
    # Preview 被残留弹窗/面板占住时会拒发事件（-10000，2026-09-19 实机
    # 出现过两次、稍后自愈）：间隔重试一次再判失败
    if outcome.kind == "error" and "-10000" in outcome.message:
        time.sleep(1.5)
        logger.info("打印事件被拒(-10000)，重试一次")
        outcome = _run_print_event(script, path)
    if outcome.kind != "error":
        return outcome
    return _open_with_default_app_posix(path)


def _run_print_event(script: str, path: str) -> PrintOutcome:
    """发送打印 AppleEvent 并归类结果（不抛出）。"""
    try:
        proc = subprocess.Popen(
            ["osascript", "-e", script],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    except FileNotFoundError:
        # 交由调用方降级（用默认程序打开）
        return PrintOutcome(False, "error", "未找到 osascript")

    try:
        _, err = proc.communicate(timeout=_DIALOG_ACK_S)
    except subprocess.TimeoutExpired:
        # 5s 未返回 = 打印面板还开着（用户在挑打印机/份数）——
        # AppleEvent 已送达，回收客户端不影响面板
        proc.kill()
        proc.communicate()
        return PrintOutcome(True, "dialog",
                            "已打开系统打印窗口，请在其中确认打印")

    if proc.returncode == 0:
        return PrintOutcome(True, "queued", "打印已交由系统处理")
    detail = (err or "").strip().splitlines()
    detail = detail[-1] if detail else f"osascript 退出码 {proc.returncode}"
    if "cancel" in detail.lower() or "-128" in detail:
        return PrintOutcome(True, "cancelled", "已取消打印")
    logger.warning("Preview 打印事件失败: %s", detail)
    return PrintOutcome(False, "error", f"打印失败: {detail}")


def _open_with_default_app_posix(path: str) -> PrintOutcome:
    opener = "open" if sys.platform == "darwin" else "xdg-open"
    try:
        proc = _run([opener, path], _LP_TIMEOUT_S)
    except FileNotFoundError:
        return PrintOutcome(False, "error",
                            f"未找到 {opener}，无法打开该文件进行打印")
    if proc.returncode != 0:
        return PrintOutcome(False, "error", "调用系统默认程序失败，无法打印")
    return PrintOutcome(True, "opened",
                        "该格式需由默认程序打印：已打开，请在其中打印（⌘P）")


def _print_windows(path: str) -> PrintOutcome:
    import win32api

    directory = os.path.dirname(path) or "."
    try:
        result = win32api.ShellExecute(0, "print", path, None, directory, 0)
    except Exception as exc:  # noqa: BLE001  关联程序缺失/动作未注册等
        logger.warning("ShellExecute print 失败: %s", exc)
        result = 0
    # ShellExecute 返回值 > 32 表示成功；打印细节由关联程序接管
    if isinstance(result, int) and result > 32:
        return PrintOutcome(True, "queued", "已提交系统打印")
    os.startfile(path)  # noqa: S316  与系统约定的标准打开方式
    return PrintOutcome(True, "opened", "已用默认程序打开，请在其中打印")


def _print_posix(path: str) -> PrintOutcome:
    ext = os.path.splitext(path)[1].lower()
    if ext not in _PRINTABLE_EXT:
        return _open_with_default_app_posix(path)
    proc = _run(["lp", path], _LP_TIMEOUT_S)
    if proc.returncode == 0:
        return PrintOutcome(True, "queued", "已发送到默认打印机")
    lines = (proc.stderr or proc.stdout or "").strip().splitlines()
    detail = lines[-1] if lines else f"退出码 {proc.returncode}"
    return PrintOutcome(False, "error", f"打印失败: {detail}")
