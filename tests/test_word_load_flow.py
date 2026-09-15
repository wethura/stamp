"""Word 打开流程的降级测试（对应用户报告的 Windows 场景）。

用户环境可能没有任何可自动转换的办公软件，且探测本身可能失败。
这条路径曾因探测异常未捕获而闪退，这里锁住：*
- 无可用引擎 → 说明原因 + 提供手动 PDF 入口，不崩溃
- 探测异常 → 同一出口，不崩溃
- 用户取消 → 干净收场，旧会话不受影响
"""
import logging
import threading
import unittest
from unittest import mock
from unittest.mock import MagicMock

# 这些用例故意制造探测异常（并期望被记录），静默日志保持输出可读
logging.disable(logging.CRITICAL)


def tearDownModule():
    """恢复日志级别，避免影响同进程的其他测试模块。"""
    logging.disable(logging.NOTSET)

from app import App
from processing.word_support.engines import EngineInfo
from processing.word_support.service import ConversionService


class DeadEngine:
    """所有探测都失败的最小引擎（模拟缺模块/注册表异常）。"""

    engine_id = "dead"
    NAME = "Dead"
    manual_path_only = False

    def probe(self):
        raise ImportError("simulated: winreg missing in frozen build")


class ManualOnlyEngine:
    engine_id = "wps"
    NAME = "WPS Office"

    def probe(self):
        return EngineInfo("wps", "WPS Office", True, manual_path_only=True)


class TestWordLoadDegradation(unittest.TestCase):
    def setUp(self):
        self.app = App()
        self.app.window = MagicMock()
        self.dialog = MagicMock()
        self.cancel = threading.Event()
        self.handler = MagicMock()

    def _probed(self, engines, error=None, service=None):
        self.handler.service = service or ConversionService(engines=[DeadEngine()])
        self.app._word_probed("/tmp/文档.docx", self.handler, engines,
                              error, self.dialog, self.cancel)

    def test_no_engine_does_not_crash_and_explains(self):
        with mock.patch("app.messagebox.askyesno", return_value=False) as ask:
            self._probed(engines=[])
        self.assertTrue(ask.called, "必须告知用户为何打不开，并给出可选出口")
        self.handler.close.assert_called_once()
        self.app.window.set_status.assert_called()

    def test_no_engine_offers_manual_pdf_import(self):
        with mock.patch("app.messagebox.askyesno", return_value=True), \
                mock.patch.object(self.app, "_manual_pdf_import") as manual:
            self._probed(engines=[])
        manual.assert_called_once()

    def test_probe_exception_degrades_instead_of_crashing(self):
        with mock.patch("app.messagebox.askyesno", return_value=False):
            self._probed(engines=[], error=ImportError("winreg missing"))
        self.handler.close.assert_called_once()
        status = self.app.window.set_status.call_args[0][0]
        self.assertIn("日志", status, "失败必须指向日志，便于用户反馈")

    def test_manual_only_engine_offers_its_specific_path(self):
        service = ConversionService(engines=[ManualOnlyEngine()])
        self.handler.service = service
        with mock.patch("app.messagebox.askyesno", return_value=False) as ask:
            self.app._word_probed("/tmp/文档.docx", self.handler, [], None,
                                  self.dialog, self.cancel)
        _title, message = ask.call_args[0][:2]
        self.assertIn("WPS", message, "已检测到 WPS 时应说明其手动路径")

    def test_cancel_is_clean(self):
        self.cancel.set()
        with mock.patch("app.messagebox.askyesno") as ask:
            self._probed(engines=[])
        ask.assert_not_called()
        status = self.app.window.set_status.call_args[0][0]
        self.assertIn("取消", status)
        self.handler.close.assert_called_once()

    def test_probe_all_never_raises_for_dead_engine(self):
        service = ConversionService(engines=[DeadEngine()])
        infos = service.probe_all()
        self.assertFalse(infos["dead"].available)
        self.assertIsNone(service.pick_engine())


class TestWordProbeRunsOffThread(unittest.TestCase):
    """探测必须在后台线程：阻塞 UI 是用户报告的「检查很慢」根因。"""

    def test_load_word_document_returns_immediately(self):
        import time

        app = App()
        app.window = MagicMock()
        # winfo_toplevel 需要返回可调 after 的对象
        toplevel = MagicMock()
        app.window.winfo_toplevel.return_value = toplevel
        handler = MagicMock()
        handler.service = ConversionService(engines=[DeadEngine()])

        # 进度对话框是真实 CTk 窗口，测试环境没有根窗口——替换成桩
        with mock.patch("app.ConversionProgressDialog", MagicMock()):
            started = time.monotonic()
            app._load_word_document("/tmp/文档.docx", handler)
            elapsed = time.monotonic() - started
        self.assertLess(elapsed, 0.5,
                        "打开文档必须立即返回（探测在后台），否则界面卡死")

        # 后台线程通过 after(0, ...) 回主线程
        for _ in range(60):
            if toplevel.after.called:
                break
            time.sleep(0.05)
        self.assertTrue(toplevel.after.called, "探测完成后应回到主线程继续流程")


if __name__ == "__main__":
    unittest.main()
