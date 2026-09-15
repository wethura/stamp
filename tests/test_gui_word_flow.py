"""真实 GUI 窗口的 Word 打开端到端回归（用户场景复现）。

用户报告（Windows）：打开 .docx 后「只弹出了加载的进度框，之后没有
下文」。原因：工作线程内调用 tkinter after 在 Windows 不可靠。此测试
用真实 CTk 主循环 + 桩引擎走完整异步链路，验证流程必达终点——
无论平台如何，进度框出现后必须推进到文档加载/明确报告。

需要可用显示环境；无显示时跳过。
"""
import tempfile
import threading
import time
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from PIL import Image

import fitz

from app import App
from processing.handlers.word_handler import WordHandler
from processing.word_support.engines import EngineInfo
from processing.word_support.service import ConversionService
from ui.main_window import MainWindow


class SlowStubEngine:
    """带人为延迟的桩引擎：确保流程真正跨线程异步完成。"""

    engine_id = "gui-stub"
    NAME = "GUI Stub"

    def __init__(self, delay=0.5, pages=2):
        self.delay = delay
        self.pages = pages

    def probe(self):
        return EngineInfo(self.engine_id, self.NAME, True, version="stub")

    def convert(self, work_copy, out_pdf, timeout_s=120.0, cancel_event=None):
        for _ in range(int(self.delay / 0.05)):
            if cancel_event is not None and cancel_event.is_set():
                return {"ok": False, "error_kind": "cancelled",
                        "error_detail": "已取消"}
            time.sleep(0.05)
        with fitz.open() as doc:
            for i in range(self.pages):
                page = doc.new_page(width=595, height=842)
                page.insert_text((50, 80), f"gui e2e page {i + 1}")
            doc.save(str(out_pdf))
        return {"ok": True, "pdf_path": str(out_pdf)}


@unittest.skipUnless(__import__("sys").platform in ("darwin", "win32", "linux"),
                     "桌面平台")
class TestGuiWordFlowEndToEnd(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            import customtkinter as ctk
        except Exception:
            raise unittest.SkipTest("customtkinter 不可用")
        try:
            cls.root = ctk.CTk()
            cls.root.geometry("1200x800+4000+4000")
        except Exception:
            raise unittest.SkipTest("无可用显示环境")

        cls.tmp = tempfile.TemporaryDirectory()
        cls.root_dir = Path(cls.tmp.name)
        cls.docx = cls.root_dir / "e2e.docx"
        with zipfile.ZipFile(cls.docx, "w") as z:
            z.writestr("[Content_Types].xml", "<Types/>")
            z.writestr("word/document.xml", "<document/>")

        cls.app = App()
        cls.window = MainWindow(cls.root, cls.app)
        cls.app.window = cls.window
        cls._pump()

    @classmethod
    def tearDownClass(cls):
        try:
            cls.root.destroy()
        finally:
            cls.tmp.cleanup()

    @classmethod
    def _pump(cls, rounds=3):
        for _ in range(rounds):
            cls.root.update_idletasks()
            cls.root.update()

    def test_docx_open_completes_after_progress_dialog(self):
        """进度框出现后，流程必须推进到文档加载完成（不得无声中断）。"""
        service = ConversionService(engines=[SlowStubEngine(delay=0.4, pages=2)],
                                    preference_path=str(self.root_dir / "pref.json"))
        # 记住偏好，跳过引擎选择弹窗（无人工交互）
        service.save_preference("gui-stub")
        handler = WordHandler(service=service)

        self.app._load_word_document(str(self.docx), handler)

        # 驱动主循环：处理进度框显示、队列轮询、看门狗与完成回调
        deadline = time.monotonic() + 20
        loaded = False
        while time.monotonic() < deadline:
            self._pump(2)
            if self.app.handler is handler and len(self.app.pages) == 2:
                loaded = True
                break
            time.sleep(0.05)

        self.assertTrue(loaded,
                        "20 秒内未完成加载——流程在进度框后中断（用户报告的 bug）")
        self.assertEqual(self.app.instance_manager.list_instances() if self.app.instance_manager else [], [])
        status = self.window._status_label.cget("text")
        self.assertIn("已加载", status)

        # 清理会话，避免影响后续用例
        handler.close()
        self.app.handler = None
        self.app.pages = []

    def test_flow_guard_recovers_from_silent_hang(self):
        """看门狗兜底：即使回调永远不来，进度框也会收起并给出状态。"""
        service = ConversionService(engines=[SlowStubEngine(delay=99.0)],
                                    preference_path=str(self.root_dir / "pref2.json"))
        handler = WordHandler(service=service)
        # 压缩看门狗时间，避免测试等待 180 秒（挂起的是转换阶段）
        with mock.patch.object(App, "CONVERT_GUARD_S", 1.0), \
                mock.patch("app.messagebox.askyesno", return_value=False):
            self.app._load_word_document(str(self.docx), handler)
            deadline = time.monotonic() + 8
            recovered = False
            while time.monotonic() < deadline:
                self._pump(2)
                status = self.window._status_label.cget("text")
                if "无响应" in status:
                    recovered = True
                    break
                time.sleep(0.05)

        self.assertTrue(recovered, "看门狗未在超时后收框报告——会回到「无声挂起」")
        # 迟到的探测结果（99 秒后才会来）因令牌失效不会覆盖状态；
        # 不等待它，直接结束测试（守护线程随进程退出）。


if __name__ == "__main__":
    unittest.main()
