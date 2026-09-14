"""Word 转换的 GUI 对话框：引擎选择（P2.4）与进度/取消（P2.3）。

按 spec：多引擎时询问「平时用哪个软件编辑这个文件」并记住选择；
转换显示不定进度条与取消按钮；无法获取真实进度时用不定进度。
"""
from typing import List, Optional

import customtkinter as ctk

from ui.theme import Colors, Fonts


def choose_engine(parent, engines: List, preferred_id: Optional[str] = None) -> Optional[str]:
    """模态询问使用哪个引擎；返回选中的 engine_id，取消返回 None。"""
    result = {"engine_id": None}
    dialog = ctk.CTkToplevel(parent)
    dialog.title("选择转换引擎")
    dialog.geometry(f"400x{190 + 54 * len(engines)}")
    dialog.resizable(False, False)
    dialog.attributes("-topmost", True)

    ctk.CTkLabel(dialog, text="平时用哪个软件编辑这个文件？",
                 font=(Fonts.FAMILY, Fonts.HEADING_SIZE, "bold"),
                 text_color=Colors.TEXT_PRIMARY).pack(pady=(18, 2))
    ctk.CTkLabel(dialog, text="预览和盖章基于转换出的 PDF，原始 Word 文件保留不变",
                 font=(Fonts.FAMILY, Fonts.SMALL_SIZE),
                 text_color=Colors.TEXT_SECONDARY).pack(pady=(0, 10))

    for info in engines:
        label = f"用 {info.name} 打开"
        if info.version:
            label += f"  （{info.version.split()[0]}）"
        if info.engine_id == preferred_id:
            label += "  · 上次使用"

        def make_command(chosen=info):
            def _choose():
                result["engine_id"] = chosen.engine_id
                dialog.destroy()
            return _choose

        ctk.CTkButton(dialog, text=label, height=38, corner_radius=8,
                      fg_color=Colors.SURFACE_RAISED,
                      hover_color=Colors.SURFACE_OVERLAY,
                      text_color=Colors.TEXT_PRIMARY,
                      border_width=1, border_color=Colors.BORDER_SUBTLE,
                      font=(Fonts.FAMILY, Fonts.BODY_SIZE),
                      command=make_command()).pack(fill="x", padx=28, pady=5)

    ctk.CTkButton(dialog, text="取消", width=110, height=30,
                  fg_color="transparent", border_width=1,
                  border_color=Colors.BORDER_SUBTLE,
                  hover_color=Colors.SURFACE_OVERLAY,
                  text_color=Colors.TEXT_SECONDARY,
                  command=dialog.destroy).pack(pady=(6, 14))

    dialog.transient(parent)
    dialog.grab_set()
    parent.wait_window(dialog)
    return result["engine_id"]


class ConversionProgressDialog(ctk.CTkToplevel):
    """不定进度 + 取消按钮的转换对话框（模态）。"""

    def __init__(self, parent, on_cancel):
        super().__init__(parent)
        self.title("正在转换")
        self.geometry("380x150")
        self.resizable(False, False)
        self.attributes("-topmost", True)
        self.protocol("WM_DELETE_WINDOW", lambda: None)  # 仅允许通过取消按钮关闭

        ctk.CTkLabel(self, text="正在转换 Word 文档…",
                     font=(Fonts.FAMILY, Fonts.HEADING_SIZE, "bold"),
                     text_color=Colors.TEXT_PRIMARY).pack(pady=(20, 8))
        ctk.CTkLabel(self, text="转换期间不会改动原始 Word 文件",
                     font=(Fonts.FAMILY, Fonts.SMALL_SIZE),
                     text_color=Colors.TEXT_SECONDARY).pack()
        self._bar = ctk.CTkProgressBar(self, mode="indeterminate", width=300)
        self._bar.pack(pady=12)
        self._bar.start()
        ctk.CTkButton(self, text="取消", width=110, height=32,
                      fg_color=Colors.SURFACE_RAISED,
                      hover_color=Colors.SURFACE_OVERLAY,
                      text_color=Colors.TEXT_PRIMARY,
                      command=on_cancel).pack(pady=(2, 14))

        self.transient(parent)
        self.grab_set()

    def close(self):
        try:
            self._bar.stop()
        except Exception:  # noqa: BLE001
            pass
        try:
            self.grab_release()
            self.destroy()
        except Exception:  # noqa: BLE001
            pass
