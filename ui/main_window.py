import tkinter as tk
from PIL import Image, ImageTk
import os
from ui.preview_canvas import PreviewCanvas
from ui.controls_panel import ControlsPanel


class MainWindow(tk.Tk):
    """主窗口类 - 继承自 tk.Tk（兼容旧代码）"""

    def __init__(self, controller):
        super().__init__()
        self.controller = controller
        self.title("盖章工具")
        self.geometry("1100x750")
        self.minsize(800, 500)

        self._set_icon()
        self._build_ui()

    def _build_ui(self):
        # Toolbar
        toolbar = tk.Frame(self, bd=1, relief=tk.RAISED)
        toolbar.pack(side=tk.TOP, fill=tk.X)

        tk.Button(toolbar, text="打开文档", command=self.controller.open_document).pack(
            side=tk.LEFT, padx=2, pady=2)
        tk.Button(toolbar, text="导出盖章文档", command=self.controller.export_pdf).pack(
            side=tk.LEFT, padx=2, pady=2)

        # Main area
        main = tk.Frame(self)
        main.pack(fill=tk.BOTH, expand=True)

        self.preview = PreviewCanvas(
            main,
            on_stamp_position_changed=self.controller.on_stamp_position_changed,
            on_editing_stamp_changed=self.controller.on_editing_stamp_changed,
            bg="#2b2b2b"
        )
        self.preview.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.controls = ControlsPanel(
            main,
            on_pages_changed=self.controller.on_pages_changed,
            on_preview_page_changed=self.controller.on_preview_page_change,
            on_stamp_selection_changed=self.controller.on_stamp_selection_changed,
            on_editing_stamp_changed=self.controller.on_editing_stamp_changed,
            width=240
        )
        self.controls.pack(side=tk.RIGHT, fill=tk.Y)

        # Status bar
        self._status_var = tk.StringVar(value="就绪")
        status = tk.Label(self, textvariable=self._status_var,
                          bd=1, relief=tk.SUNKEN, anchor=tk.W)
        status.pack(side=tk.BOTTOM, fill=tk.X)

    def set_status(self, msg: str):
        self._status_var.set(msg)

    def _set_icon(self):
        icon_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'assets', 'icon.png')
        if os.path.exists(icon_path):
            try:
                if os.name == 'nt':
                    self.iconbitmap(icon_path)
                else:
                    icon_img = Image.open(icon_path)
                    self.icon_photo = ImageTk.PhotoImage(icon_img)
                    self.iconphoto(True, self.icon_photo)
            except Exception:
                pass


class MainFrame(tk.Frame):
    """主窗口 Frame - 用于在现有 Tk 根窗口中显示"""

    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller

        # 设置窗口属性
        parent.title("盖章工具")
        parent.geometry("1100x750")
        parent.minsize(800, 500)

        self._set_icon(parent)
        self._build_ui()
        self.pack(fill=tk.BOTH, expand=True)

    def _build_ui(self):
        # Toolbar
        toolbar = tk.Frame(self, bd=1, relief=tk.RAISED)
        toolbar.pack(side=tk.TOP, fill=tk.X)

        tk.Button(toolbar, text="打开文档", command=self.controller.open_document).pack(
            side=tk.LEFT, padx=2, pady=2)
        tk.Button(toolbar, text="导出盖章文档", command=self.controller.export_pdf).pack(
            side=tk.LEFT, padx=2, pady=2)

        # Main area
        main = tk.Frame(self)
        main.pack(fill=tk.BOTH, expand=True)

        self.preview = PreviewCanvas(
            main,
            on_stamp_position_changed=self.controller.on_stamp_position_changed,
            on_editing_stamp_changed=self.controller.on_editing_stamp_changed,
            bg="#2b2b2b"
        )
        self.preview.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.controls = ControlsPanel(
            main,
            on_pages_changed=self.controller.on_pages_changed,
            on_preview_page_changed=self.controller.on_preview_page_change,
            on_stamp_selection_changed=self.controller.on_stamp_selection_changed,
            on_editing_stamp_changed=self.controller.on_editing_stamp_changed,
            width=240
        )
        self.controls.pack(side=tk.RIGHT, fill=tk.Y)

        # Status bar
        self._status_var = tk.StringVar(value="就绪")
        status = tk.Label(self, textvariable=self._status_var,
                          bd=1, relief=tk.SUNKEN, anchor=tk.W)
        status.pack(side=tk.BOTTOM, fill=tk.X)

    def set_status(self, msg: str):
        self._status_var.set(msg)

    def mainloop(self):
        """兼容方法：调用根窗口的 mainloop"""
        self.master.mainloop()

    def _set_icon(self, parent):
        icon_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'assets', 'icon.png')
        if os.path.exists(icon_path):
            try:
                if os.name == 'nt':
                    parent.iconbitmap(icon_path)
                else:
                    icon_img = Image.open(icon_path)
                    self.icon_photo = ImageTk.PhotoImage(icon_img)
                    parent.iconphoto(True, self.icon_photo)
            except Exception:
                pass
