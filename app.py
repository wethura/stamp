"""Application controller — bridges UI and processing layers."""

import threading
from tkinter import filedialog, messagebox
from PIL import Image
from typing import Optional, List, Dict
import os
import shlex
import shutil

from processing import HandlerRegistry
from processing.base import DocumentHandler
from processing.handlers.pdf_handler import PDFHandler
from processing.handlers.word_handler import WordHandler
from processing.stamp_manager import StampManager
from processing.stamp_instance import StampInstance, StampInstanceManager
from processing.stamp import apply_opacity
from processing.word_support.errors import ConversionError
from processing.word_support.service import get_shared_service
from ui.word_dialogs import ConversionProgressDialog, choose_engine


class App:
    def __init__(self):
        self.handler: Optional[DocumentHandler] = None
        self.doc_path = None
        self.pages: List[Image.Image] = []

        self.stamp_manager = StampManager()
        self.instance_manager: Optional[StampInstanceManager] = None

        self.active_page = 0
        self._selected_instance_id: Optional[str] = None

        self.window = None

    # --- Document ---

    def open_settings(self):
        """打开系统设置（当前提供 Word 转换引擎选择）。"""
        from ui.settings_dialog import open_settings as open_dialog
        open_dialog(self.window, get_shared_service())

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
        if isinstance(handler, WordHandler):
            self._load_word_document(path, handler)
            return
        try:
            if self.handler is not None:
                self.handler.close()

            handler.load(path)
            pages = [handler.render_page(i) for i in range(handler.page_count())]
            self._activate_document(path, handler, pages)
        except Exception as e:
            messagebox.showerror("加载失败", str(e))

    def _activate_document(self, path: str, handler, pages: List[Image.Image]):
        """Switch the session to a freshly loaded document (UI thread only)."""
        if self.handler is not None and self.handler is not handler:
            self.handler.close()

        self.handler = handler
        self.doc_path = path
        self.pages = pages

        self.instance_manager = StampInstanceManager(path)
        self.active_page = 0
        self._selected_instance_id = None

        self.window.controls.set_instance_manager(self.instance_manager)
        self.window.preview.reset_view()
        self.window.set_status(f"已加载: {path}  ({len(pages)} 页)")
        self._refresh_preview()

    # --- Word 转换（P2.3/P2.4：后台转换 + 取消 + 引擎选择 + 手动 PDF）---

    def _load_word_document(self, path: str, handler: WordHandler):
        service = handler.service
        engines = service.available_engines(refresh=True)

        if not engines:
            handler.close()
            has_manual = any(info.available and info.manual_path_only
                             for info in service.probe_all().values())
            if has_manual and messagebox.askyesno(
                    "WPS 暂不能自动转换",
                    "已检测到 WPS，当前版本暂不能自动转换。\n"
                    "是否改为手动导入已导出的 PDF？"):
                self._manual_pdf_import()
            else:
                messagebox.showwarning(
                    "无法打开 Word 文档",
                    "未找到可用的 Word 转换引擎。\n"
                    "请安装 LibreOffice，或在 Word/WPS 中将文件导出为 PDF 后拖入本工具。")
            return

        preferred = service.current_preference()
        valid_ids = [info.engine_id for info in engines]
        if handler.engine_id is None and len(engines) > 1 and preferred not in valid_ids:
            chosen = choose_engine(self.window, engines, preferred)
            if chosen is None:
                return  # 用户取消选择，不打开
            handler.engine_id = chosen
            service.save_preference(chosen)
        elif handler.engine_id is None:
            handler.engine_id = engines[0].engine_id

        cancel_event = threading.Event()
        handler.cancel_event = cancel_event
        dialog = ConversionProgressDialog(
            self.window, lambda: cancel_event.set())
        self.window.update()

        def worker():
            try:
                handler.load(path)
                pages = [handler.render_page(i) for i in range(handler.page_count())]
                error = None
            except ConversionError as exc:
                pages, error = None, exc
            except Exception as exc:  # noqa: BLE001
                pages, error = None, ConversionError("convert", str(exc))
            root = self.window.winfo_toplevel()
            root.after(0, self._word_load_finished,
                       path, handler, pages, dialog, error)

        threading.Thread(target=worker, daemon=True).start()

    def _word_load_finished(self, path, handler, pages, dialog, error):
        dialog.close()
        if error is None:
            self._activate_document(path, handler, pages)
            engine_note = ""
            if handler.last_engine_info is not None:
                engine_note = f"  ·  引擎: {handler.last_engine_info.name}"
            self.window.set_status(
                f"已加载: {path}  ({len(pages)} 页){engine_note}  ·  导出将为 PDF")
            return

        handler.close()
        if getattr(error, "kind", None) == "cancelled":
            self.window.set_status("已取消转换，原文档保持不变")
            return

        self.window.set_status("Word 转换失败")
        if messagebox.askyesno("转换失败", f"{error}\n\n是否手动导入已导出的 PDF？"):
            self._manual_pdf_import()

    def _manual_pdf_import(self):
        path = filedialog.askopenfilename(
            title="导入 PDF",
            filetypes=[("PDF 文件", "*.pdf *.PDF")],
        )
        if not path:
            return
        handler = HandlerRegistry.get_handler(path)
        if handler is not None:
            self._load_document(path, handler)

    # --- Instance Management ---

    def on_stamp_library_changed(self):
        """Refresh template edits and remove placements of deleted templates."""
        if self.instance_manager:
            for instance in self.instance_manager.list_instances():
                if self.stamp_manager.get_stamp(instance.template_id) is None:
                    self.instance_manager.remove_instance(instance.instance_id)
            if self._selected_instance_id and self.instance_manager.get_instance(self._selected_instance_id) is None:
                self._selected_instance_id = None
                self.window.preview.clear_selection()
                self.window.controls.set_editing_instance(None)
        self._refresh_preview()

    def create_instance_from_template(self, template_id: str):
        """Double-click template to create instance on current active page"""
        if self.instance_manager is None:
            return

        page_index = self.active_page
        instance = self.instance_manager.add_instance(template_id, page_index)
        self._selected_instance_id = instance.instance_id
        self.window.controls.set_editing_instance(instance.instance_id)
        self._refresh_preview()

    def delete_instance(self, instance_id: str):
        """Delete a stamp instance"""
        if self.instance_manager is None:
            return

        self.instance_manager.remove_instance(instance_id)
        self.window.preview.clear_selection(instance_id)
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

    def on_instance_drag_end(self):
        """Instance drag ended"""
        pass

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

    def on_active_page_changed(self, page_index: int):
        """Active page changed from preview canvas scroll/click"""
        self.active_page = page_index

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
        """Export with all instances applied per-page."""
        all_instances = self.instance_manager.list_instances()
        page_instances: Dict[int, List[StampInstance]] = {}
        for inst in all_instances:
            page_instances.setdefault(inst.page_index, []).append(inst)

        if not page_instances:
            return

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
                rotation=instance.rotation,
            )

            if handler != self.handler:
                handler.close()

            if target != current_path:
                shutil.move(target, current_path)

    # --- Internal ---

    def _refresh_preview(self):
        if not self.pages:
            return

        all_instances = {}
        template_images = {}
        for i in range(len(self.pages)):
            instances = self.get_page_stamp_data(i)
            if instances:
                all_instances[i] = instances
                for inst in instances:
                    if inst.template_id not in template_images:
                        img = self.get_template_image(inst.template_id)
                        if img:
                            template_images[inst.template_id] = img

        self.window.preview.update_all_pages(self.pages, all_instances, template_images)
