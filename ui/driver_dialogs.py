"""LibreOffice 转换组件的下载/管理 UI。

用户自行决定是否下载：明确确认对话（体积/来源/许可/目标路径）→
进度窗口（实时字节进度 + 取消）→ 完成后引擎立即可用。
"""
from typing import Optional

import customtkinter as ctk

from processing.word_support.driver_manager import (
    KIND_LABEL,
    DriverError,
    DriverManager,
)
from ui.theme import Colors, Fonts

PHASE_TEXT = {
    "download": "正在下载 LibreOffice…",
    "verify": "正在校验文件…",
    "extract": "正在解包安装…",
}


def confirm_driver_download(parent, info: dict) -> bool:
    """下载前的明确确认；返回是否继续。"""
    from tkinter import messagebox

    size_mb = info.get("size_mb") or "约 300+"
    return messagebox.askyesno(
        "下载 LibreOffice 转换组件",
        f"将下载 LibreOffice {info.get('version', '')}（{KIND_LABEL.get(info.get('kind'), '')}）\n\n"
        f"大小：约 {size_mb} MB\n"
        f"来源：{info.get('url', '')}\n"
        f"安装位置：本用户目录（~/.stamp_tool/drivers，不影响系统）\n"
        f"许可：MPL-2.0（The Document Foundation）\n\n"
        f"下载仅用于 Word 文档转换，是否继续？")


class DriverProgressDialog(ctk.CTkToplevel):
    """下载进度窗口：按字节显示进度，支持取消。"""

    def __init__(self, parent, size_bytes: int):
        super().__init__(parent)
        self.title("下载转换组件")
        self.geometry("440x190")
        self.resizable(False, False)
        self.attributes("-topmost", True)
        self.protocol("WM_DELETE_WINDOW", lambda: None)

        self._label = ctk.CTkLabel(
            self, text="正在下载 LibreOffice…",
            font=(Fonts.FAMILY, Fonts.HEADING_SIZE, "bold"),
            text_color=Colors.TEXT_PRIMARY)
        self._label.pack(pady=(20, 4))
        self._detail = ctk.CTkLabel(
            self, text="准备中…",
            font=(Fonts.FAMILY, Fonts.SMALL_SIZE),
            text_color=Colors.TEXT_SECONDARY)
        self._detail.pack()
        self._bar = ctk.CTkProgressBar(self, width=340)
        self._bar.pack(pady=12)
        self._bar.set(0)
        self._cancel = ctk.CTkButton(
            self, text="取消", width=110, height=32,
            fg_color=Colors.SURFACE_RAISED,
            hover_color=Colors.SURFACE_OVERLAY,
            text_color=Colors.TEXT_PRIMARY,
            command=self._on_cancel)
        self._cancel.pack(pady=(2, 12))

        self._size = size_bytes
        self._cancelled = False
        self.transient(parent)
        self.grab_set()

    def on_cancel(self):
        self._cancelled = True

    @property
    def cancelled(self) -> bool:
        return self._cancelled

    def update_progress(self, phase: str, done: int, total: int):
        """DriverManager 的进度回调（在工作线程执行——只改文本/数值，
        由调用方保证线程安全：经主线程 after 派发调用本方法）。"""
        self._label.configure(text=PHASE_TEXT.get(phase, phase))
        if total > 0:
            self._bar.set(max(0.0, min(1.0, done / total)))
            done_mb = done / 1024 / 1024
            total_mb = total / 1024 / 1024
            pct = int(done / total * 100)
            self._detail.configure(
                text=f"{done_mb:.0f} / {total_mb:.0f} MB（{pct}%）")
        else:
            self._detail.configure(text="处理中…")
        self.update_idletasks()

    def close(self):
        try:
            self.grab_release()
            self.destroy()
        except Exception:  # noqa: BLE001
            pass


def run_driver_install(parent, on_done: Optional[callable] = None) -> None:
    """完整的安装流程：确认 → 后台下载/解包（可取消）→ 结果反馈。

    线程纪律与 App 相同：工作线程只入队，主线程轮询器执行 UI 更新
    （Windows 上线程内 root.after 不可靠）。on_done(installed) 主线程回调。
    """
    import threading
    from queue import Empty, Queue
    from tkinter import messagebox

    manager = DriverManager()
    info = manager.catalog_info()
    if not info:
        messagebox.showinfo(
            "暂不支持",
            "当前平台暂不提供内置下载。\n"
            "请通过系统包管理器安装 LibreOffice 后重试。")
        if on_done:
            on_done(False)
        return
    if manager.status()["installed"]:
        messagebox.showinfo("已安装", "LibreOffice 转换组件已就绪。")
        if on_done:
            on_done(True)
        return
    if not confirm_driver_download(parent, info):
        if on_done:
            on_done(False)
        return

    dialog = DriverProgressDialog(parent, info.get("size_bytes") or 0)
    cancel_event = threading.Event()
    dialog._cancel.configure(command=lambda: (dialog.on_cancel(),
                                              cancel_event.set()))
    root = parent.winfo_toplevel()

    queue: Queue = Queue()

    def poller():  # 仅主线程执行
        try:
            while True:
                kind, payload = queue.get_nowait()
                if kind == "progress":
                    phase, done, total = payload
                    if dialog.winfo_exists():
                        dialog.update_progress(phase, done, total)
                elif kind == "done":
                    dialog.close()
                    error = payload
                    if error is None:
                        messagebox.showinfo(
                            "安装完成",
                            "LibreOffice 转换组件已就绪。\n"
                            "现在可以直接打开 Word 文档了。")
                        if on_done:
                            on_done(True)
                    elif error.kind == "cancelled":
                        if on_done:
                            on_done(False)
                    else:
                        messagebox.showerror("安装失败", str(error))
                        if on_done:
                            on_done(False)
                    return  # 结束轮询
        except Empty:
            pass
        root.after(80, poller)

    def safe_progress(phase, done, total):  # 工作线程调用：只入队
        queue.put(("progress", (phase, done, total)))

    def worker():
        try:
            manager.install(progress_cb=safe_progress,
                            cancel_event=cancel_event)
            queue.put(("done", None))
        except DriverError as exc:
            queue.put(("done", exc))
        except Exception as exc:  # noqa: BLE001
            queue.put(("done", DriverError("extract", f"安装过程出错: {exc}")))

    root.after(80, poller)  # 主线程启动轮询器
    threading.Thread(target=worker, daemon=True,
                     name="driver-install").start()
