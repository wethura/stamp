"""App.print_document 流程测试：前置校验与系统打印管线的接线。"""
import unittest
from unittest.mock import MagicMock, patch

from app import App
from processing.printing import PrintOutcome


def make_app(doc_loaded=True, has_instances=True, ext=".pdf"):
    app = App()
    app.window = MagicMock()
    if doc_loaded:
        app.doc_path = "/tmp/合同.pdf"
        handler = MagicMock()
        handler.default_output_extension.return_value = ext
        app.handler = handler
    if has_instances:
        manager = MagicMock()
        manager.list_instances.return_value = [MagicMock()]
        app.instance_manager = manager
    return app


class _FakeThread:
    """同步执行的线程替身：start() 直接跑 target，结果留在主队列。"""

    last_name = None

    def __init__(self, target=None, daemon=None, name=None):
        self._target = target
        _FakeThread.last_name = name

    def start(self):
        self._target()


def drain_main_queue(app):
    from queue import Empty
    while True:
        try:
            fn, args = app._main_queue.get_nowait()
        except Empty:
            break
        fn(*args)


class TestPrintGuards(unittest.TestCase):
    @patch("app.messagebox")
    def test_no_document_warns(self, messagebox):
        app = make_app(doc_loaded=False)
        app.print_document()
        messagebox.showwarning.assert_called_once()
        self.assertIn("请先打开文档", messagebox.showwarning.call_args[0])

    @patch("app.messagebox")
    def test_no_instances_warns(self, messagebox):
        app = make_app(has_instances=False)
        app.print_document()
        messagebox.showwarning.assert_called_once()
        self.assertIn("请先添加印章", messagebox.showwarning.call_args[0][1])


class TestPrintFlow(unittest.TestCase):
    @patch("app.print_file")
    def test_exports_then_spools_to_system_off_ui_thread(self, print_file):
        print_file.return_value = PrintOutcome(
            True, "dialog", "已打开系统打印窗口，请在其中确认打印")
        app = make_app()
        exported = {}

        def fake_export(out_path):
            exported["path"] = out_path

        with patch("app.threading.Thread", _FakeThread), \
             patch.object(App, "_export_with_instances",
                          side_effect=fake_export):
            app.print_document()

        self.assertEqual(_FakeThread.last_name, "print")
        self.assertTrue(exported["path"].endswith("合同-已盖章.pdf"))
        print_file.assert_called_once_with(exported["path"])
        drain_main_queue(app)
        app.window.set_status.assert_called_with(
            "已打开系统打印窗口，请在其中确认打印")
        self.assertFalse(app._print_busy)
        # 回调依赖主线程队列轮询器：打印流程必须自己启动它
        # （此前只有 Word 流程启动，PDF/图片文档下回调无人消费）
        self.assertTrue(app._poller_active)

    @patch("app.print_file")
    def test_busy_guard_prevents_double_dialogs(self, print_file):
        print_file.return_value = PrintOutcome(True, "dialog", "已唤起")
        app = make_app()
        app._print_busy = True
        with patch.object(App, "_export_with_instances") as export:
            app.print_document()
        export.assert_not_called()
        print_file.assert_not_called()

    @patch("app.print_file")
    def test_excel_uses_handler_output_extension(self, print_file):
        print_file.return_value = PrintOutcome(True, "opened", "已打开")
        app = make_app(ext=".xlsx")
        exported = {}

        def fake_export(out_path):
            exported["path"] = out_path

        with patch("app.threading.Thread", _FakeThread), \
             patch.object(App, "_export_with_instances",
                          side_effect=fake_export):
            app.print_document()
        self.assertTrue(exported["path"].endswith("合同-已盖章.xlsx"))

    @patch("app.messagebox")
    @patch("app.print_file")
    def test_spool_error_shows_dialog(self, print_file, messagebox):
        print_file.return_value = PrintOutcome(False, "error", "打印失败: 队列不可用")
        app = make_app()
        with patch("app.threading.Thread", _FakeThread), \
             patch.object(App, "_export_with_instances"):
            app.print_document()
        drain_main_queue(app)
        messagebox.showerror.assert_called_once()

    @patch("app.messagebox")
    @patch("app.print_file")
    def test_user_cancel_is_quiet(self, print_file, messagebox):
        """用户在系统打印面板点「取消」不是错误：只更新状态栏。"""
        print_file.return_value = PrintOutcome(True, "cancelled", "已取消打印")
        app = make_app()
        with patch("app.threading.Thread", _FakeThread), \
             patch.object(App, "_export_with_instances"):
            app.print_document()
        drain_main_queue(app)
        messagebox.showerror.assert_not_called()
        app.window.set_status.assert_called_with("已取消打印")

    @patch("app.messagebox")
    @patch("app.print_file")
    def test_export_failure_shows_error(self, print_file, messagebox):
        app = make_app()
        with patch.object(App, "_export_with_instances",
                          side_effect=OSError("磁盘已满")):
            app.print_document()
        messagebox.showerror.assert_called_once()
        print_file.assert_not_called()


if __name__ == "__main__":
    unittest.main()
