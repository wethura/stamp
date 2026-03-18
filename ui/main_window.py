import tkinter as tk
from ui.preview_canvas import PreviewCanvas
from ui.controls_panel import ControlsPanel


class MainWindow(tk.Tk):
    def __init__(self, controller):
        super().__init__()
        self.controller = controller
        self.title("印章工具")
        self.geometry("1100x700")
        self.minsize(800, 500)

        self._build_ui()

    def _build_ui(self):
        # Toolbar
        toolbar = tk.Frame(self, bd=1, relief=tk.RAISED)
        toolbar.pack(side=tk.TOP, fill=tk.X)

        tk.Button(toolbar, text="打开文档", command=self.controller.open_document).pack(
            side=tk.LEFT, padx=2, pady=2)
        tk.Button(toolbar, text="打开章", command=self.controller.open_stamp).pack(
            side=tk.LEFT, padx=2, pady=2)
        tk.Button(toolbar, text="导出 PDF", command=self.controller.export_pdf).pack(
            side=tk.LEFT, padx=2, pady=2)

        # Main area
        main = tk.Frame(self)
        main.pack(fill=tk.BOTH, expand=True)

        self.preview = PreviewCanvas(
            main,
            on_position_change=self.controller.on_position_change,
            bg="#2b2b2b"
        )
        self.preview.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.controls = ControlsPanel(
            main,
            on_pages_changed=self.controller.on_pages_changed,
            on_size_changed=self.controller.on_size_change,
            on_preview_page_changed=self.controller.on_preview_page_change,
            width=200
        )
        self.controls.pack(side=tk.RIGHT, fill=tk.Y)

        # Status bar
        self._status_var = tk.StringVar(value="就绪")
        status = tk.Label(self, textvariable=self._status_var,
                          bd=1, relief=tk.SUNKEN, anchor=tk.W)
        status.pack(side=tk.BOTTOM, fill=tk.X)

    def set_status(self, msg: str):
        self._status_var.set(msg)
