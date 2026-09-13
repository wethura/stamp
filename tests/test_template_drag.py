"""模板拖拽释放的位置判定与会话清理。"""
import tkinter as tk
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, call

from ui.controls_panel import ControlsPanel


class TestTemplateDragCreate(unittest.TestCase):
    def setUp(self):
        self.panel = ControlsPanel.__new__(ControlsPanel)
        self.panel.on_create_instance = MagicMock()
        self.root = MagicMock()
        self.panel.winfo_toplevel = MagicMock(return_value=self.root)
        self.panel._drag_template_id = 'template_123'
        self.panel._drag_motion_binding = 'motion_binding'
        self.panel._drag_release_binding = 'release_binding'
        self.drag_window = MagicMock()
        self.panel._drag_window = self.drag_window
        self.panel._drop_target = MagicMock()
        self.panel._drop_target.winfo_rootx.return_value = 100
        self.panel._drop_target.winfo_rooty.return_value = 200
        self.panel._drop_target.winfo_width.return_value = 400
        self.panel._drop_target.winfo_height.return_value = 300
        self.event = SimpleNamespace(x_root=250, y_root=350)

    def test_drag_callback_triggers_create_instance(self):
        self.panel._on_stamp_drag_release(self.event)
        self.panel.on_create_instance.assert_called_once_with('template_123')
        self.drag_window.destroy.assert_called_once()
        self.root.unbind.assert_has_calls([
            call('<B1-Motion>', 'motion_binding'),
            call('<ButtonRelease-1>', 'release_binding'),
        ])

    def test_drag_callback_with_none_handler(self):
        self.panel.on_create_instance = None
        self.panel._on_stamp_drag_release(self.event)
        self.drag_window.destroy.assert_called_once()

    def test_drop_outside_preview_does_not_create_instance(self):
        for x, y in ((99, 350), (501, 350), (250, 199), (250, 501)):
            with self.subTest(x=x, y=y):
                self.panel._drag_template_id = 'template_123'
                self.panel._on_stamp_drag_release(SimpleNamespace(x_root=x, y_root=y))
        self.panel.on_create_instance.assert_not_called()

    def test_missing_or_destroyed_target_does_not_create_instance(self):
        self.panel._drop_target.winfo_rootx.side_effect = tk.TclError('已关闭')
        self.panel._on_stamp_drag_release(self.event)
        self.panel._drop_target = None
        self.panel._drag_template_id = 'template_123'
        self.panel._on_stamp_drag_release(self.event)
        self.panel.on_create_instance.assert_not_called()

    def test_repeated_release_does_not_create_duplicate_instance(self):
        self.panel._on_stamp_drag_release(self.event)
        self.panel._on_stamp_drag_release(self.event)
        self.panel.on_create_instance.assert_called_once_with('template_123')
        self.drag_window.destroy.assert_called_once()
        self.assertEqual(self.root.unbind.call_count, 2)

    def test_cancelled_drag_cannot_be_reused_by_later_release(self):
        self.panel._on_stamp_drag_release(SimpleNamespace(x_root=20, y_root=20))
        self.panel._on_stamp_drag_release(self.event)
        self.panel.on_create_instance.assert_not_called()


if __name__ == '__main__':
    unittest.main()
