import tkinter as tk
from tkinter import filedialog, messagebox
from PIL import Image

from processing.document import load_document, render_page, is_image_input
from processing.stamp import load_stamp, scale_stamp
from processing.exporter import export_pdf
from ui.main_window import MainWindow


class App:
    def __init__(self):
        self.doc_path = None
        self.fitz_doc = None
        self.is_image = False
        self.pages = []  # list of PIL.Image (rendered pages)

        self.stamp_img = None  # RGBA, original unscaled
        self.position_ratio = (0.7, 0.7)
        self.stamp_size_ratio = 0.2
        self.selected_pages = set()
        self.current_preview_page = 0

        self.window = MainWindow(self)

    def run(self):
        self.window.mainloop()

    # --- Document ---

    def open_document(self):
        path = filedialog.askopenfilename(
            title="打开文档",
            filetypes=[
                ("支持的文件", "*.pdf *.jpg *.jpeg *.png *.bmp *.tiff *.tif *.webp"),
                ("PDF 文件", "*.pdf"),
                ("图片文件", "*.jpg *.jpeg *.png *.bmp *.tiff *.tif *.webp"),
            ]
        )
        if not path:
            return
        try:
            fitz_doc, pages = load_document(path)
            self.doc_path = path
            self.fitz_doc = fitz_doc
            self.is_image = is_image_input(path)
            self.pages = pages
            self.current_preview_page = 0
            self.selected_pages = set(range(len(pages)))

            self.window.controls.set_pages(len(pages))
            self.window.set_status(f"已加载: {path}  ({len(pages)} 页)")
            self._refresh_preview()
        except Exception as e:
            messagebox.showerror("加载失败", str(e))

    # --- Stamp ---

    def open_stamp(self):
        path = filedialog.askopenfilename(
            title="打开章",
            filetypes=[
                ("图片文件", "*.jpg *.jpeg *.png *.bmp *.tiff *.tif *.webp"),
            ]
        )
        if not path:
            return
        try:
            self.stamp_img = load_stamp(path)
            # Default: bottom-right, accounting for stamp size
            self.position_ratio = self._clamp(0.75, 0.75)
            self.window.set_status(f"已加载章: {path}")
            self._refresh_preview()
        except Exception as e:
            messagebox.showerror("加载章失败", str(e))

    # --- Callbacks ---

    def on_position_change(self, x: float, y: float):
        self.position_ratio = self._clamp(x, y)
        self._refresh_preview()

    def on_size_change(self, ratio: float):
        self.stamp_size_ratio = ratio
        self.position_ratio = self._clamp(*self.position_ratio)
        self._refresh_preview()

    def on_pages_changed(self, selected: set):
        self.selected_pages = selected

    def on_preview_page_change(self, idx: int):
        self.current_preview_page = idx
        self._refresh_preview()

    # --- Export ---

    def export_pdf(self):
        if not self.doc_path:
            messagebox.showwarning("提示", "请先打开文档")
            return
        if self.stamp_img is None:
            messagebox.showwarning("提示", "请先打开章")
            return
        if not self.selected_pages:
            messagebox.showwarning("提示", "请至少选择一页进行盖章")
            return

        out_path = filedialog.asksaveasfilename(
            title="导出 PDF",
            defaultextension=".pdf",
            filetypes=[("PDF 文件", "*.pdf")]
        )
        if not out_path:
            return

        try:
            export_pdf(
                src_path=self.doc_path,
                is_image=self.is_image,
                stamp_img=self.stamp_img,
                position_ratio=self.position_ratio,
                stamp_size_ratio=self.stamp_size_ratio,
                selected_pages=self.selected_pages,
                output_path=out_path,
            )
            self.window.set_status(f"已导出: {out_path}")
            messagebox.showinfo("导出成功", f"已保存到:\n{out_path}")
        except Exception as e:
            messagebox.showerror("导出失败", str(e))

    # --- Internal ---

    def _clamp(self, x: float, y: float) -> tuple:
        """Clamp position so stamp stays within page bounds."""
        sr = self.stamp_size_ratio
        if self.stamp_img:
            aspect = self.stamp_img.height / self.stamp_img.width
        else:
            aspect = 1.0
        sh = sr * aspect
        x = max(0.0, min(x, 1.0 - sr))
        y = max(0.0, min(y, 1.0 - sh))
        return (x, y)

    def _refresh_preview(self):
        if not self.pages:
            return
        idx = min(self.current_preview_page, len(self.pages) - 1)
        page_img = self.pages[idx]
        self.window.preview.update_preview(
            page_img,
            self.stamp_img,
            self.position_ratio,
            self.stamp_size_ratio,
        )
