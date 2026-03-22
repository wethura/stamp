import tkinter as tk
from tkinter import filedialog, messagebox
from PIL import Image
from typing import Optional, List

from processing import HandlerRegistry
from processing.base import DocumentHandler
from processing.stamp_manager import StampManager
from ui.main_window import MainWindow
from ui.controls_panel import StampSelection


class App:
    def __init__(self):
        self.handler: Optional[DocumentHandler] = None
        self.doc_path = None
        self.pages: List[Image.Image] = []

        # 章管理器
        self.stamp_manager = StampManager()

        # 待盖章的章列表（用户选中要盖到文档上的章）
        self.selected_stamps: List[StampSelection] = []

        self.selected_pages = set()
        self.current_preview_page = 0

        self.window = MainWindow(self)

        # 设置章管理器到控制面板
        self.window.controls.set_stamp_manager(self.stamp_manager)

    def run(self):
        self.window.mainloop()

    # --- Document ---

    def open_document(self):
        filters = HandlerRegistry.get_file_filters()

        path = filedialog.askopenfilename(
            title="打开文档",
            filetypes=filters
        )
        if not path:
            return

        try:
            handler = HandlerRegistry.get_handler(path)
            if handler is None:
                messagebox.showerror("错误", "不支持的文件格式")
                return

            if self.handler is not None:
                self.handler.close()

            handler.load(path)
            self.handler = handler
            self.doc_path = path

            self.pages = []
            for i in range(handler.page_count()):
                self.pages.append(handler.render_page(i))

            self.current_preview_page = 0
            self.selected_pages = set(range(len(self.pages)))

            self.window.controls.set_pages(len(self.pages))
            self.window.set_status(f"已加载: {path}  ({len(self.pages)} 页)")
            self._refresh_preview()
        except Exception as e:
            messagebox.showerror("加载失败", str(e))

    # --- Stamp Selection Callback ---

    def on_stamp_selection_changed(self, stamps: List[StampSelection]):
        """待盖章的章变化回调"""
        self.selected_stamps = stamps
        self._refresh_preview()

    def on_editing_stamp_changed(self, stamp_id: Optional[str]):
        """正在编辑的章变化回调"""
        # 更新控制面板的编辑状态显示
        self.window.controls.set_editing_stamp(stamp_id)
        self._refresh_preview()

    def on_stamp_position_changed(self, stamp_id: str, pos_x: float, pos_y: float):
        """章位置变化回调（拖拽）"""
        self.stamp_manager.update_stamp(stamp_id, pos_x=pos_x, pos_y=pos_y)
        # 重新获取所有选中章的最新数据
        self.selected_stamps = self.window.controls.get_selected_stamps()
        self._refresh_preview()

    # --- Callbacks ---

    def on_pages_changed(self, selected: set):
        self.selected_pages = selected

    def on_preview_page_change(self, idx: int):
        self.current_preview_page = idx
        self._refresh_preview()

    # --- Export ---

    def export_pdf(self):
        if self.handler is None or self.doc_path is None:
            messagebox.showwarning("提示", "请先打开文档")
            return
        if not self.selected_stamps:
            messagebox.showwarning("提示", "请至少选择一个章")
            return
        if not self.selected_pages:
            messagebox.showwarning("提示", "请至少选择一页进行盖章")
            return

        filter_name, filter_pattern = HandlerRegistry.get_output_filter(self.handler)
        default_ext = self.handler.default_output_extension()

        import os
        original_name = os.path.splitext(os.path.basename(self.doc_path))[0]
        default_filename = f"{original_name}-已盖章{default_ext}"

        out_path = filedialog.asksaveasfilename(
            title="导出文档",
            initialfile=default_filename,
            defaultextension=default_ext,
            filetypes=[(filter_name, filter_pattern)]
        )
        if not out_path:
            return

        try:
            self._export_with_multiple_stamps(out_path)
            self.window.set_status(f"已导出: {out_path}")
            messagebox.showinfo("导出成功", f"已保存到:\n{out_path}")
        except Exception as e:
            messagebox.showerror("导出失败", str(e))

    def _export_with_multiple_stamps(self, output_path: str):
        """导出时叠加多个章"""
        first_stamp = self.selected_stamps[0]

        self.handler.export_with_stamp(
            output_path=output_path,
            stamp_img=first_stamp.stamp_img,
            position_ratio=(first_stamp.pos_x, first_stamp.pos_y),
            stamp_size_ratio=first_stamp.size_ratio,
            selected_pages=self.selected_pages,
        )

        if len(self.selected_stamps) > 1:
            from processing.handlers.pdf_handler import PDFHandler
            temp_handler = PDFHandler()
            temp_handler.load(output_path)

            for stamp_sel in self.selected_stamps[1:]:
                temp_path = output_path + ".tmp"
                temp_handler.export_with_stamp(
                    output_path=temp_path,
                    stamp_img=stamp_sel.stamp_img,
                    position_ratio=(stamp_sel.pos_x, stamp_sel.pos_y),
                    stamp_size_ratio=stamp_sel.size_ratio,
                    selected_pages=self.selected_pages,
                )
                temp_handler.close()

                import shutil
                shutil.move(temp_path, output_path)

                temp_handler = PDFHandler()
                temp_handler.load(output_path)

            temp_handler.close()

    # --- Internal ---

    def _refresh_preview(self):
        if not self.pages:
            return
        idx = min(self.current_preview_page, len(self.pages) - 1)
        page_img = self.pages[idx]
        self.window.preview.update_preview(page_img, self.selected_stamps)
