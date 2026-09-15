"""启动序列与旧状态容错测试（对应用户报告：窗口加载完成后消失）。

用户环境：进程存活、窗口不可见、日志静默。两个结构性防线：
1. 主窗先显示，印章库后加载且全容错（旧版本残留的损坏库不得挡窗口）
2. 可见性看门狗：窗口隐形时自动强制拉起并留日志
"""
import json
import logging
import unittest
from unittest import mock
from unittest.mock import MagicMock

from processing.stamp_manager import StampManager


class TestStampLibraryCorruptionTolerance(unittest.TestCase):
    def setUp(self):
        import tempfile
        from pathlib import Path
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)

    def _manager_with(self, content: str) -> StampManager:
        self.dir.mkdir(parents=True, exist_ok=True)
        (self.dir / "stamps.json").write_text(content, encoding="utf-8")
        return StampManager(config_dir=str(self.dir))

    def test_non_dict_entries_degrade_to_empty(self):
        manager = self._manager_with('["corrupt-entry", {"id": 123}, "junk"]')
        self.assertEqual(manager.list_stamps(), [])

    def test_invalid_json_degrades_to_empty(self):
        manager = self._manager_with("{ this is not json")
        self.assertEqual(manager.list_stamps(), [])

    def test_partial_corruption_keeps_valid_entries(self):
        payload = json.dumps([
            {"id": "a-1", "name": "好章", "image_base64": "iVBORw0KGgo=",
             "created_at": "2026-09-15T00:00:00"},
            "corrupt-entry",
            {"id": "a-2", "name": "缺图章"},  # 缺 image_base64 字段
        ])
        manager = self._manager_with(payload)
        stamps = manager.list_stamps()
        self.assertEqual(len(stamps), 1, "单条损坏只丢弃该条")
        self.assertEqual(stamps[0].id, "a-1")

    def test_manager_never_raises_on_garbage(self):
        for garbage in ("", "null", "[]", "123", '"str"', "\\x00\\x01"):
            with self.subTest(garbage=garbage):
                manager = self._manager_with(garbage)
                self.assertIsInstance(manager.list_stamps(), list)


class TestShowMainWindowOrdering(unittest.TestCase):
    def _run_show(self, load_error=None):
        from main import _show_main_window

        root = MagicMock()
        window = MagicMock()
        if load_error:
            window.controls.set_stamp_manager.side_effect = load_error
        app = MagicMock()
        app.stamp_manager = MagicMock()

        logging.disable(logging.CRITICAL)
        try:
            _show_main_window(root, window, app)
        finally:
            logging.disable(logging.NOTSET)
        return root, window, app

    def test_window_shown_before_library_load(self):
        """主窗必须先显示（deiconify），再加载印章库。"""
        order = []
        root, window, app = MagicMock(), MagicMock(), MagicMock()
        root.deiconify.side_effect = lambda: order.append("deiconify")
        window.controls.set_stamp_manager.side_effect = lambda *a: order.append("load")

        from main import _show_main_window
        logging.disable(logging.CRITICAL)
        try:
            _show_main_window(root, window, app)
        finally:
            logging.disable(logging.NOTSET)

        self.assertEqual(order[:2], ["deiconify", "load"],
                         "旧顺序在加载库期间应用零可见窗口——用户报告的「消失」")

    def test_library_failure_does_not_hide_window(self):
        root, window, app = self._run_show(load_error=RuntimeError("boom"))
        root.deiconify.assert_called_once()
        window.set_status.assert_called()  # 最终状态仍被设置

    def test_status_messages_tell_user_what_is_happening(self):
        root, window, app = self._run_show()
        messages = [c.args[0] for c in window.set_status.call_args_list]
        self.assertIn("正在加载印章库…", messages)
        self.assertIn("就绪 · 打开文档后，双击右侧印章即可添加", messages)


class TestVisibilityGuard(unittest.TestCase):
    def test_guard_retries_when_invisible(self):
        from main import _guard_window_visibility

        root = MagicMock()
        root.winfo_viewable.return_value = False
        scheduled = []
        root.after.side_effect = lambda ms, cb=None, *a: (scheduled.append((ms, cb)), "id")[1]

        logging.disable(logging.CRITICAL)
        try:
            _guard_window_visibility(root)
            # 触发第一次检查（模拟 Tk 定时器到期）
            first_cb = scheduled[0][1]
            first_cb()
        finally:
            logging.disable(logging.NOTSET)

        root.deiconify.assert_called()
        root.lift.assert_called()
        # 隐形时排布下一次检查
        self.assertTrue(any(cb for ms, cb in scheduled[1:]))

    def test_guard_stops_when_visible(self):
        from main import _guard_window_visibility

        root = MagicMock()
        root.winfo_viewable.return_value = True
        scheduled = []
        root.after.side_effect = lambda ms, cb=None, *a: (scheduled.append((ms, cb)), "id")[1]

        _guard_window_visibility(root)
        before = len(scheduled)
        scheduled[0][1]()  # 第一次检查：可见
        root.deiconify.assert_not_called()
        self.assertEqual(len(scheduled), before, "可见后不再排布重试")


if __name__ == "__main__":
    unittest.main()
