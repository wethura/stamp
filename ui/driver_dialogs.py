"""LibreOffice 转换组件的下载/管理 UI。

用户自行决定是否下载：确认对话（体积/来源/许可 + 可修改的安装位置）→
进度窗口（实时字节进度 + 取消）→ 完成后引擎立即可用。
"""
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import customtkinter as ctk
from tkinter import messagebox

from processing.word_support.driver_manager import (
    KIND_LABEL,
    UNPACK_FACTOR,
    DriverError,
    DriverManager,
)
from ui.theme import Colors, Fonts

PHASE_TEXT = {
    "download": "正在下载 LibreOffice…",
    "verify": "正在校验文件…",
    "extract": "正在解包安装…",
}


def _fmt_size(n: float) -> str:
    if n >= 1024 ** 3:
        return f"{n / 1024 ** 3:.1f} GB"
    return f"{max(1, round(n / 1024 / 1024))} MB"


class DriverConfirmDialog(ctk.CTkToplevel):
    """下载前的确认 + 安装位置选择。

    模态用法：构造后由调用方 wait_window；关闭后读
    confirmed（是否继续）与 target_dir（安装目录字符串）。
    """

    def __init__(self, parent, info: dict, default_dir):
        super().__init__(parent)
        self.title("下载 LibreOffice 转换组件")
        self.geometry("560x400")
        self.resizable(False, False)
        self.attributes("-topmost", True)
        self.confirmed = False
        self.target_dir = str(default_dir)

        ctk.CTkLabel(
            self, text="下载 LibreOffice 转换组件",
            font=(Fonts.FAMILY, Fonts.HEADING_SIZE, "bold"),
            text_color=Colors.TEXT_PRIMARY).pack(anchor="w", padx=24, pady=(18, 2))

        source = urlparse(info.get("url", "")).netloc or info.get("url", "")
        unpacked = (info.get("size_bytes") or 0) * UNPACK_FACTOR
        ctk.CTkLabel(
            self, justify="left",
            text=f"版本 {info.get('version', '')}"
                 f"（{KIND_LABEL.get(info.get('kind'), '')}）\n"
                 f"大小：约 {_fmt_size(info.get('size_bytes') or 0)}　"
                 f"来源：{source}（官方）\n"
                 f"许可：MPL-2.0（The Document Foundation）。解包安装不需要"
                 f"管理员权限、不写注册表。",
            font=(Fonts.FAMILY, Fonts.BODY_SIZE),
            text_color=Colors.TEXT_SECONDARY).pack(anchor="w", padx=24, pady=(6, 0))

        ctk.CTkLabel(
            self, text="安装位置",
            font=(Fonts.FAMILY, Fonts.BODY_SIZE, "bold"),
            text_color=Colors.TEXT_PRIMARY).pack(anchor="w", padx=24, pady=(16, 2))
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", padx=24)
        self._path = ctk.CTkEntry(
            row, height=36,
            font=(Fonts.FAMILY, Fonts.BODY_SIZE),
            fg_color=Colors.SURFACE_RAISED,
            border_color=Colors.BORDER_SUBTLE,
            text_color=Colors.TEXT_PRIMARY)
        self._path.insert(0, str(default_dir))
        self._path.pack(side="left", fill="x", expand=True)
        ctk.CTkButton(
            row, text="浏览…", width=84, height=36,
            fg_color="transparent", border_width=1,
            border_color=Colors.BORDER_SUBTLE,
            hover_color=Colors.SURFACE_OVERLAY,
            text_color=Colors.TEXT_PRIMARY,
            font=(Fonts.FAMILY, Fonts.BODY_SIZE),
            command=self._browse).pack(side="left", padx=(8, 0))
        ctk.CTkLabel(
            self, text=f"可改为其他磁盘上的空目录（如 D:\\LibreOffice）；"
                       f"解包后约占用 {_fmt_size(unpacked)}",
            font=(Fonts.FAMILY, Fonts.SMALL_SIZE),
            text_color=Colors.TEXT_SECONDARY).pack(anchor="w", padx=24, pady=(4, 0))

        bottom = ctk.CTkFrame(self, fg_color="transparent")
        bottom.pack(fill="x", padx=24, pady=(18, 18))
        ctk.CTkButton(
            bottom, text="取消", width=96, height=36,
            fg_color="transparent", border_width=1,
            border_color=Colors.BORDER_SUBTLE,
            hover_color=Colors.SURFACE_OVERLAY,
            text_color=Colors.TEXT_SECONDARY,
            font=(Fonts.FAMILY, Fonts.BODY_SIZE),
            command=self._cancel).pack(side="right")
        ctk.CTkButton(
            bottom, text="下载并安装", width=120, height=36,
            fg_color=Colors.PRIMARY, hover_color=Colors.PRIMARY_HOVER,
            text_color="white",
            font=(Fonts.FAMILY, Fonts.BODY_SIZE, "bold"),
            command=self._ok).pack(side="right", padx=(0, 8))

        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self.transient(parent)
        self.grab_set()

    # ── 内部 ─────────────────────────────────────────────────────────

    def _browse(self):
        from tkinter import filedialog
        current = Path(self._path.get().strip() or str(Path.home())).expanduser()
        initial = current
        while not initial.exists():
            initial = initial.parent
        chosen = filedialog.askdirectory(
            title="选择安装位置（空目录）", initialdir=str(initial), parent=self)
        if chosen:
            self._path.delete(0, "end")
            self._path.insert(0, chosen)

    def _ok(self):
        text = self._path.get().strip()
        if not text:
            self._warn("请先填写安装位置，或点击「浏览…」选择目录。")
            return
        path = Path(text).expanduser()
        if not path.is_absolute():
            self._warn("安装位置必须是绝对路径，例如 D:\\LibreOffice。")
            return
        if (path.exists() and any(path.iterdir())
                and not (path / "driver.json").exists()):
            self._warn(f"所选目录不是空的：\n{path}\n\n"
                       f"请选择一个空目录，组件将直接安装到该目录。")
            return
        self.target_dir = str(path)
        self.confirmed = True
        self.destroy()

    def _cancel(self):
        self.confirmed = False
        self.destroy()

    def _warn(self, message: str):
        messagebox.showwarning("安装位置", message, parent=self)


class DriverProgressDialog(ctk.CTkToplevel):
    """下载进度窗口：按字节显示进度，支持取消。"""

    def __init__(self, parent, size_bytes: int,
                 on_cancel: Optional[callable] = None):
        super().__init__(parent)
        self.title("下载转换组件")
        self.geometry("440x190")
        self.resizable(False, False)
        self.attributes("-topmost", True)

        self._on_cancel_cb = on_cancel
        self._cancelled = False
        self._size = size_bytes

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
            command=self.cancel)
        self._cancel.pack(pady=(2, 12))

        self.protocol("WM_DELETE_WINDOW", self.cancel)
        self.transient(parent)
        self.grab_set()

    def cancel(self):
        """用户取消：置位标志并触发回调（通知工作线程停止下载）。"""
        self._cancelled = True
        if self._on_cancel_cb:
            self._on_cancel_cb()

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
    """完整的安装流程：确认+选位置 → 后台下载/解包（可取消）→ 结果反馈。

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

    confirm = DriverConfirmDialog(parent, info, manager.default_install_dir)
    confirm.wait_window(confirm)
    if not confirm.confirmed:
        if on_done:
            on_done(False)
        return
    target_dir = confirm.target_dir

    cancel_event = threading.Event()
    dialog = DriverProgressDialog(parent, info.get("size_bytes") or 0,
                                  on_cancel=cancel_event.set)
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
                            cancel_event=cancel_event,
                            target_dir=target_dir)
            queue.put(("done", None))
        except DriverError as exc:
            queue.put(("done", exc))
        except Exception as exc:  # noqa: BLE001
            queue.put(("done", DriverError("extract", f"安装过程出错: {exc}")))

    root.after(80, poller)  # 主线程启动轮询器
    threading.Thread(target=worker, daemon=True,
                     name="driver-install").start()
