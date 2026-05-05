from tkinter import filedialog, messagebox
from PIL import Image
from typing import Optional, List, Dict
import os
import shlex
import shutil

from processing import HandlerRegistry
from processing.base import DocumentHandler
from processing.stamp_manager import StampManager
from processing.stamp_instance import StampInstance, StampInstanceManager
from processing.stamp import apply_opacity, apply_rotation
from processing.handlers.pdf_handler import PDFHandler
from ui.main_window import MainWindow


class App:
    def __init__(self):
        self.handler: Optional[DocumentHandler] = None
        self.doc_path = None
        self.pages: List[Image.Image] = []

        self.stamp_manager = StampManager()
        self.instance_manager: Optional[StampInstanceManager] = None

        self.selected_pages = set()
        self.current_preview_page = 0
        self._selected_instance_id: Optional[str] = None

        self.window = MainWindow(self)
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

        handler = HandlerRegistry.get_handler(path)
        if handler is None:
            messagebox.showerror("错误", "不支持的文件格式")
            return

        self._load_document(path, handler)

    def on_file_dropped(self, drop_data: str):
        try:
            paths = shlex.split(drop_data)
        except ValueError:
            paths = [drop_data.strip()]

        paths = [p for p in paths if p]

        if len(paths) > 1:
            self.window.set_status("请每次拖入一个文件")
            return

        if not paths:
            return

        path = paths[0]
        path = path.strip("{}")

        if not os.path.exists(path):
            self.window.set_status("文件不存在")
            return

        handler = HandlerRegistry.get_handler(path)
        if handler is None:
            self.window.set_status("不支持的文件格式")
            return

        self._load_document(path, handler)

    def _load_document(self, path: str, handler):
        try:
            if self.handler is not None:
                self.handler.close()

            handler.load(path)
            self.handler = handler
            self.doc_path = path

            self.pages = []
            for i in range(handler.page_count()):
                self.pages.append(handler.render_page(i))

            self.instance_manager = StampInstanceManager()
            self.current_preview_page = 0
            self.selected_pages = set(range(len(self.pages)))
            self._selected_instance_id = None

            self.window.controls.set_pages(len(self.pages))
            self.window.controls.set_instance_manager(self.instance_manager)
            self.window.set_status(f"已加载: {path}  ({len(self.pages)} 页)")
            self._refresh_preview()
        except Exception as e:
            messagebox.showerror("加载失败", str(e))

    # --- Instance Management ---

    def create_instance_from_template(self, template_id: str):
        """Double-click template to create instance on current page"""
        if self.instance_manager is None:
            return

        instance = self.instance_manager.add_instance(template_id, self.current_preview_page)
        self._selected_instance_id = instance.instance_id
        self.window.controls.set_editing_instance(instance.instance_id)
        self._refresh_preview()

    def delete_instance(self, instance_id: str):
        """Delete a stamp instance"""
        if self.instance_manager is None:
            return

        self.instance_manager.remove_instance(instance_id)
        if self._selected_instance_id == instance_id:
            self._selected_instance_id = None
            self.window.controls.set_editing_instance(None)
        self._refresh_preview()

    def on_instance_position_changed(self, instance_id: str, pos_x: float, pos_y: float):
        """Instance drag position changed"""
        if self.instance_manager is None:
            return
        self.instance_manager.update_instance(instance_id, pos_x=pos_x, pos_y=pos_y)
        self._refresh_preview()

    def on_instance_selected(self, instance_id: Optional[str]):
        """Instance selected in preview"""
        self._selected_instance_id = instance_id
        self.window.controls.set_editing_instance(instance_id)

    def update_instance_property(self, instance_id: str, **kwargs):
        """Update instance property from slider"""
        if self.instance_manager is None:
            return
        self.instance_manager.update_instance(instance_id, **kwargs)
        self._refresh_preview()

    # --- Page Navigation ---

    def on_pages_changed(self, selected: set):
        self.selected_pages = selected

    def on_preview_page_change(self, idx: int):
        self.current_preview_page = idx
        self._selected_instance_id = None
        self.window.controls.set_editing_instance(None)
        self._refresh_preview()

    # --- Preview Data ---

    def get_page_stamp_data(self, page_index: int) -> List[StampInstance]:
        """Get stamp instances for a page with resolved template images"""
        if self.instance_manager is None:
            return []
        return self.instance_manager.get_page_instances(page_index)

    def get_template_image(self, template_id: str) -> Optional[Image.Image]:
        """Get template image by ID"""
        template = self.stamp_manager.get_stamp(template_id)
        if template:
            return template.get_image()
        return None

    # --- Export ---

    def export_pdf(self):
        if self.handler is None or self.doc_path is None:
            messagebox.showwarning("提示", "请先打开文档")
            return
        if self.instance_manager is None or not self.instance_manager.list_instances():
            messagebox.showwarning("提示", "请先添加印章到文档")
            return
        if not self.selected_pages:
            messagebox.showwarning("提示", "请至少选择一页进行盖章")
            return

        filter_name, filter_pattern = HandlerRegistry.get_output_filter(self.handler)
        default_ext = self.handler.default_output_extension()

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
            self._export_with_instances(out_path)
            self.window.set_status(f"已导出: {out_path}")
            messagebox.showinfo("导出成功", f"已保存到:\n{out_path}")
        except Exception as e:
            messagebox.showerror("导出失败", str(e))

    def _export_with_instances(self, output_path: str):
        """Export with all instances applied per-page.

        Strategy: export instances one-by-one. The first instance uses the
        original handler; subsequent instances re-load the accumulating output
        via a temp PDF, stacking stamps incrementally.
        """
        all_instances = self.instance_manager.list_instances()
        page_instances: Dict[int, List[StampInstance]] = {}
        for inst in all_instances:
            if inst.page_index in self.selected_pages:
                page_instances.setdefault(inst.page_index, []).append(inst)

        if not page_instances:
            return

        # Flatten all instances into a single ordered list
        ordered = []
        for page_idx in sorted(page_instances.keys()):
            ordered.extend(page_instances[page_idx])

        current_path = output_path
        is_first = True

        for instance in ordered:
            template = self.stamp_manager.get_stamp(instance.template_id)
            if template is None:
                continue

            stamp_img = template.get_image()

            if instance.opacity < 1.0:
                stamp_img = apply_opacity(stamp_img, instance.opacity)
            if instance.rotation != 0:
                stamp_img = apply_rotation(stamp_img, instance.rotation)

            if is_first:
                handler = self.handler
                target = current_path
                is_first = False
            else:
                handler = PDFHandler()
                handler.load(current_path)
                target = current_path + ".tmp"

            handler.export_with_stamp(
                output_path=target,
                stamp_img=stamp_img,
                position_ratio=(instance.pos_x, instance.pos_y),
                stamp_size_ratio=instance.size_ratio,
                selected_pages={instance.page_index},
            )

            if handler != self.handler:
                handler.close()

            if target != current_path:
                shutil.move(target, current_path)

    # --- Internal ---

    def _refresh_preview(self):
        if not self.pages:
            return
        idx = min(self.current_preview_page, len(self.pages) - 1)
        page_img = self.pages[idx]

        instances = self.get_page_stamp_data(idx)
        template_images = {}
        for inst in instances:
            if inst.template_id not in template_images:
                img = self.get_template_image(inst.template_id)
                if img:
                    template_images[inst.template_id] = img

        self.window.preview.update_preview(page_img, instances, template_images)
