"""模板拖拽到预览区创建实例测试"""
import unittest
from unittest.mock import MagicMock

from processing.stamp_instance import StampInstanceManager
from ui.controls_panel import ControlsPanel


class TestTemplateDragCreate(unittest.TestCase):
    """模板拖拽回调测试 — 验证拖拽释放后触发创建实例"""

    def test_drag_callback_triggers_create_instance(self):
        """拖拽释放回调调用 on_create_instance"""
        on_create = MagicMock()
        panel = ControlsPanel.__new__(ControlsPanel)
        panel.on_create_instance = on_create
        panel._stamp_manager = None
        panel._instance_manager = StampInstanceManager()
        panel._editing_instance_id = None
        panel._stamps = []
        panel._stamp_previews = {}

        # 模拟拖拽释放调用
        panel._on_stamp_drag_release("template_123")

        on_create.assert_called_once_with("template_123")

    def test_drag_callback_with_none_handler(self):
        """on_create_instance 为 None 时不报错"""
        panel = ControlsPanel.__new__(ControlsPanel)
        panel.on_create_instance = None

        # 不应抛出异常
        panel._on_stamp_drag_release("template_123")


if __name__ == "__main__":
    unittest.main()
