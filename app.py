"""Application controller — bridges UI and processing layers."""

import logging
import threading
from queue import Empty, Queue
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

logger = logging.getLogger(__name__)


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

        # ── 跨线程调度与流程看门狗 ─────────────────────────────────
        # tkinter 的 after/控件调用只在主线程安全；工作线程通过队列投递
        # 结果，由主线程轮询器执行（Windows 上线程内 root.after 不可靠，
        # 曾表现为进度框出现后流程无声中断）。
        self._main_queue: "Queue" = Queue()
        self._poller_active = False
        self._flow_token = 0
        self._flow_lock = threading.Lock()
        self._flow_guards: Dict[int, object] = {}

    # --- 跨线程调度（工作线程 → 主线程） ---

    def _ensure_main_poller(self):
        """在主线程启动队列轮询器（幂等；只允许主线程调用）。"""
        if not self._poller_active:
            self._poller_active = True
            self.window.after(80, self._drain_main_queue)

    def _drain_main_queue(self):
        while True:
            try:
                fn, args = self._main_queue.get_nowait()
            except Empty:
                break
            try:
                fn(*args)
            except Exception:  # noqa: BLE001  单个回调失败不拖垮轮询器
                logger.exception("主线程回调执行失败: %r", fn)
        self.window.after(80, self._drain_main_queue)

    def _dispatch_to_main(self, fn, *args):
        """线程安全：任何线程都可调用；结果由主线程轮询器执行。"""
        self._main_queue.put((fn, args))

    # --- Word 流程令牌与看门狗 ---

    def _next_flow_token(self) -> int:
        with self._flow_lock:
            self._flow_token += 1
            return self._flow_token

    def _is_stale_token(self, token: int) -> bool:
        with self._flow_lock:
            return token != self._flow_token

    def _arm_flow_guard(self, token: int, dialog, seconds: float, stage: str):
        """超时未收到下一阶段回调时收起进度框并报告（防「无声挂起」）。"""
        def guard():
            if self._is_stale_token(token):
                return  # 流程已前进/取消，对话框由对应路径处理
            logger.error("%s 阶段 %ss 无响应，自动收起进度框", stage, seconds)
            try:
                dialog.close()
            except Exception:  # noqa: BLE001
                pass
            with self._flow_lock:
                self._flow_token += 1  # 使迟到的回调失效
            self.window.set_status(f"{stage}无响应，已中止（详情见日志）")

        try:
            after_id = self.window.after(int(seconds * 1000), guard)
            with self._flow_lock:
                self._flow_guards[token] = after_id
        except Exception:  # noqa: BLE001  看门狗自身失败不影响主流程
            logger.warning("看门狗注册失败（%s）", stage, exc_info=True)

    def _disarm_flow_guard(self, token: int):
        with self._flow_lock:
            after_id = self._flow_guards.pop(token, None)
        if after_id is not None:
            try:
                self.window.after_cancel(after_id)
            except Exception:  # noqa: BLE001
                pass

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

    # --- Word 转换（P2.3/P2.4：后台探测 + 后台转换 + 取消 + 手动 PDF）---

    PROBE_GUARD_S = 30.0    # 探测看门狗：引擎检查超过此时长自动收框报告
    CONVERT_GUARD_S = 180.0  # 转换看门狗：超过 120s 转换上限 + 余量

    def _load_word_document(self, path: str, handler: WordHandler):
        """后台探测引擎 → （可选）选择 → 后台转换；全程不阻塞 UI。

        线程纪律：工作线程绝不触碰 tkinter（含 after——Windows 上线程内
        after 不可靠，曾表现为进度框出现后流程无声中断）。结果一律经
        `_dispatch_to_main` 队列回主线程，并由看门狗兜底超时。
        """
        service = handler.service
        cancel_event = threading.Event()
        handler.cancel_event = cancel_event
        dialog = ConversionProgressDialog(
            self.window, lambda: cancel_event.set(),
            message="正在检查可用的转换引擎…")
        self.window.update()
        self._ensure_main_poller()
        token = self._next_flow_token()
        self._arm_flow_guard(token, dialog, self.PROBE_GUARD_S, "检查转换引擎")

        def probe_worker():
            try:
                engines = service.available_engines(refresh=True)
                error = None
            except Exception as exc:  # noqa: BLE001  兜底，绝不外抛
                logger.exception("引擎探测失败")
                engines, error = [], exc
            self._dispatch_to_main(self._word_probed, token, path, handler,
                                   engines, error, dialog, cancel_event)

        threading.Thread(target=probe_worker, daemon=True, name="word-probe").start()

    def _word_probed(self, token, path, handler, engines, error,
                     dialog, cancel_event):
        if self._is_stale_token(token):
            logger.info("忽略过期的探测结果（会话已前进/超时）")
            return
        self._disarm_flow_guard(token)
        dialog.close()
        if cancel_event.is_set():
            handler.close()
            self.window.set_status("已取消，原文档保持不变")
            return
        if error is not None:
            handler.close()
            self._report_word_open_failure("检查转换引擎时出错", str(error),
                                           offer_manual=True)
            return
        if not engines:
            handler.close()
            self._report_no_engine(handler.service)
            return

        chosen = self._resolve_engine(handler, engines)
        if chosen is None:
            handler.close()
            self.window.set_status("未选择转换引擎，已取消打开")
            return

        self._start_word_conversion(path, handler, cancel_event)

    def _resolve_engine(self, handler: WordHandler, engines):
        """确定使用的引擎：已有指定 → 偏好 → 单选直接定 → 多选询问。"""
        if handler.engine_id:
            return handler.engine_id
        service = handler.service
        preferred = service.current_preference()
        valid_ids = [info.engine_id for info in engines]

        if len(engines) > 1 and preferred not in valid_ids:
            chosen = choose_engine(self.window, engines, preferred)
            if chosen is None:
                return None
            service.save_preference(chosen)
        elif preferred in valid_ids:
            chosen = preferred
        else:
            chosen = engines[0].engine_id

        handler.engine_id = chosen
        return chosen

    def _start_word_conversion(self, path, handler, cancel_event):
        dialog = ConversionProgressDialog(
            self.window, lambda: cancel_event.set(),
            message="正在转换 Word 文档…")
        self.window.update()
        token = self._next_flow_token()
        self._arm_flow_guard(token, dialog, self.CONVERT_GUARD_S, "转换")

        def worker():
            try:
                handler.load(path)
                pages = [handler.render_page(i) for i in range(handler.page_count())]
                error = None
            except ConversionError as exc:
                pages, error = None, exc
            except Exception as exc:  # noqa: BLE001
                logger.exception("Word 转换异常")
                pages, error = None, ConversionError("convert", str(exc))
            self._dispatch_to_main(self._word_load_finished, token, path,
                                   handler, pages, dialog, error)

        threading.Thread(target=worker, daemon=True, name="word-convert").start()

    def _report_no_engine(self, service):
        """没有可自动转换的引擎：给出可执行的出口，不弹错误堆栈。

        探测只是一层便利、可能遗漏（自定义目录、非标准安装），
        因此首选出口是「用户指定安装目录」，下载组件是最后手段。
        """
        from ui.word_dialogs import choose_no_engine_action

        probes = service.probe_all().values()
        manual_only = [info for info in probes
                       if info.available and info.manual_path_only]
        if manual_only:
            # 检测到了 WPS 但接口不可用：没有可指定的本地程序，走手动 PDF
            if messagebox.askyesno(
                    "暂无自动转换方式",
                    "已检测到 WPS，当前版本暂不能自动转换。\n"
                    "是否改为手动导入已导出的 PDF？"):
                self._manual_pdf_import()
            else:
                self.window.set_status("未转换：可在办公软件中导出 PDF 后拖入本工具")
            return

        choice = choose_no_engine_action(self.window)
        if choice == "manual_pdf":
            self._manual_pdf_import()
        else:
            self.window.set_status("未转换：可在 ⚙ 设置 中指定安装目录或下载组件")

    def _install_converter_driver(self):
        """下载内置 LibreOffice 转换组件（设置页/无引擎弹窗共用入口）。"""
        from ui.driver_dialogs import run_driver_install

        def on_done(installed):
            if not installed:
                return
            # 组件就绪后立即生效：刷新探测缓存并提示重新打开文档
            get_shared_service().probe_all(refresh=True)
            self.window.set_status("转换组件已就绪，可重新打开 Word 文档")

        run_driver_install(self.window, on_done=on_done)

    def _report_word_open_failure(self, title: str, detail: str, offer_manual=False):
        logger.error("%s: %s", title, detail)
        self.window.set_status(f"{title}（详情见日志）")
        if offer_manual and messagebox.askyesno(
                title, f"{detail}\n\n是否改为手动导入已导出的 PDF？"):
            self._manual_pdf_import()

    def _word_load_finished(self, token, path, handler, pages, dialog, error):
        if self._is_stale_token(token):
            logger.info("忽略过期的转换结果（会话已前进/超时）")
            return
        self._disarm_flow_guard(token)
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

        self._report_word_open_failure("Word 转换失败", str(error), offer_manual=True)

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
