"""Word 打开流程的降级与线程调度测试（对应用户报告的 Windows 场景）。

用户环境可能没有任何可自动转换的办公软件，且探测本身可能失败。
两轮用户报告对应两条防线：
1. 探测异常/无引擎 → 说明原因 + 手动 PDF 出口，不崩溃（v0.1.2）
2. 进度框出现后「没有下文」→ 工作线程不得触碰 tkinter（Windows 上
   线程内 after 不可靠）；结果经队列回主线程 + 看门狗兜底（v0.1.5）
"""
import logging
import threading
import time
import unittest
from queue import Empty
from unittest import mock
from unittest.mock import MagicMock

from app import App
from processing.word_support.engines import EngineInfo
from processing.word_support.service import ConversionService

# 这些用例故意制造探测异常（并期望被记录），静默日志保持输出可读
logging.disable(logging.CRITICAL)


def tearDownModule():
    """恢复日志级别，避免影响同进程的其他测试模块。"""
    logging.disable(logging.NOTSET)


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
        self.token = self.app._next_flow_token()

    def _probed(self, engines, error=None, service=None):
        self.handler.service = service or ConversionService(engines=[DeadEngine()])
        self.app._word_probed(self.token, "/tmp/文档.docx", self.handler,
                              engines, error, self.dialog, self.cancel)

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
            self.app._word_probed(self.token, "/tmp/文档.docx", self.handler,
                                  [], None, self.dialog, self.cancel)
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


class TestMainThreadDispatch(unittest.TestCase):
    """工作线程 → 主线程的调度纪律（「进度框后没有下文」的防线）。"""

    def _make_app(self):
        app = App()
        app.window = MagicMock()
        return app

    def test_worker_never_touches_tkinter(self):
        """探测线程只允许往队列投递结果，不允许调用任何 tkinter 方法。

        Windows 上线程内调用 after/控件方法不可靠——v0.1.4 打开 docx
        「进度框出现后无声中断」即因此而来。陷阱只拦工作线程：主线程
        的调用是合法的。
        """
        app = self._make_app()
        handler = MagicMock()
        handler.service = ConversionService(engines=[DeadEngine()])

        class TkCallTrap(Exception):
            pass

        main_thread = threading.main_thread()

        def trap(name):
            def _f(*a, **k):
                if threading.current_thread() is not main_thread:
                    raise TkCallTrap(f"worker 调用了 tkinter 方法: {name}")
                return MagicMock()()
            return _f

        for name in ["after", "winfo_toplevel", "update", "set_status",
                     "update_idletasks"]:
            setattr(app.window, name, trap(name))

        with mock.patch("app.ConversionProgressDialog", MagicMock()):
            app._load_word_document("/tmp/文档.docx", handler)

        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            try:
                item = app._main_queue.get(timeout=0.2)
                break
            except Empty:
                continue
        else:
            self.fail("工作线程 5 秒内没有投递结果（可能卡在 tkinter 调用上）")

        # 恢复 after 以便后续清理逻辑可用
        app.window.after = MagicMock(return_value="id")
        fn, args = item
        self.assertEqual(fn.__name__, "_word_probed")

    def test_stale_token_result_is_ignored(self):
        """迟到的结果按会话号丢弃（A06：不得覆盖新会话）。"""
        app = self._make_app()
        old_token = app._next_flow_token()
        app._next_flow_token()  # 流程前进（重新打开/超时推进）

        dialog = MagicMock()
        handler = MagicMock()
        with mock.patch.object(app, "_report_no_engine") as report:
            app._word_probed(old_token, "/tmp/a.docx", handler, [], None,
                             dialog, threading.Event())
        report.assert_not_called()
        handler.close.assert_not_called()

    def test_flow_guard_closes_dialog_and_reports(self):
        """看门狗：超时后收起进度框、报告状态、使迟到结果失效。"""
        app = self._make_app()
        token = app._next_flow_token()
        dialog = MagicMock()

        guards = {}
        app.window.after = MagicMock(
            side_effect=lambda ms, cb=None, *a: (guards.setdefault(ms, cb), f"id-{ms}")[1])

        app._arm_flow_guard(token, dialog, 30, "检查转换引擎")
        guard_cb = guards[30000]
        guard_cb()

        dialog.close.assert_called_once()
        status = app.window.set_status.call_args[0][0]
        self.assertIn("无响应", status)

        # 看门狗推进了令牌 → 迟到的探测结果应被忽略
        with mock.patch.object(app, "_report_no_engine") as report:
            app._word_probed(token, "/tmp/a.docx", MagicMock(), [], None,
                             MagicMock(), threading.Event())
        report.assert_not_called()

    def test_guard_disarmed_on_normal_completion(self):
        app = self._make_app()
        token = app._next_flow_token()
        app.window.after = MagicMock(return_value="guard-id")

        app._arm_flow_guard(token, MagicMock(), 30, "探测")
        app._disarm_flow_guard(token)
        app.window.after_cancel.assert_called_once_with("guard-id")


class TestWordProbeRunsOffThread(unittest.TestCase):
    """探测必须在后台线程：阻塞 UI 是用户报告的「检查很慢」根因。"""

    def test_load_word_document_returns_immediately(self):
        app = App()
        app.window = MagicMock()
        handler = MagicMock()
        handler.service = ConversionService(engines=[DeadEngine()])

        with mock.patch("app.ConversionProgressDialog", MagicMock()):
            started = time.monotonic()
            app._load_word_document("/tmp/文档.docx", handler)
            elapsed = time.monotonic() - started
        self.assertLess(elapsed, 0.5,
                        "打开文档必须立即返回（探测在后台），否则界面卡死")
        self.assertTrue(app._poller_active, "必须启动主线程轮询器")


if __name__ == "__main__":
    unittest.main()
