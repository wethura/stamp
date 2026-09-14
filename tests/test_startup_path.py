"""启动路径测试：守护 main.py 的控制器构造。

历史 bug：main.py 曾用 App.__new__ + 手工赋值构造控制器，字段名
（current_preview_page）与 App.__init__ 的 active_page 漂移后，
打包版双击添加印章直接 AttributeError 崩溃。这里锁住构造契约。
"""
import unittest
from unittest.mock import MagicMock

from PIL import Image

from main import create_app_controller
from processing.stamp_instance import StampInstanceManager

REQUIRED_STATE = (
    "handler", "doc_path", "pages", "stamp_manager", "instance_manager",
    "active_page", "_selected_instance_id", "window",
)


class TestStartupController(unittest.TestCase):
    def test_controller_exposes_every_attribute_the_app_relies_on(self):
        controller = create_app_controller()
        for attr in REQUIRED_STATE:
            self.assertTrue(hasattr(controller, attr),
                            f"启动构造的控制器缺少 {attr}（字段漂移会致运行期崩溃）")

    def test_initial_state_is_sane(self):
        controller = create_app_controller()
        self.assertIsNone(controller.handler)
        self.assertIsNone(controller.doc_path)
        self.assertEqual(controller.pages, [])
        self.assertIsNone(controller.instance_manager)
        self.assertEqual(controller.active_page, 0)
        self.assertIsNone(controller._selected_instance_id)

    def test_add_instance_works_through_startup_controller(self):
        """核心流程回归：启动路径构造的控制器必须能添加印章实例。"""
        controller = create_app_controller()
        controller.instance_manager = StampInstanceManager()
        controller.pages = [Image.new("RGB", (800, 1130))]
        controller.window = MagicMock()

        controller.create_instance_from_template("tmpl-1")

        instances = controller.instance_manager.list_instances()
        self.assertEqual(len(instances), 1)
        self.assertEqual(instances[0].page_index, controller.active_page)
        self.assertEqual(instances[0].template_id, "tmpl-1")

    def test_add_instance_respects_active_page(self):
        controller = create_app_controller()
        controller.instance_manager = StampInstanceManager()
        controller.pages = [Image.new("RGB", (800, 1130)) for _ in range(3)]
        controller.window = MagicMock()
        controller.active_page = 2

        controller.create_instance_from_template("tmpl-1")

        self.assertEqual(controller.instance_manager.list_instances()[0].page_index, 2)


if __name__ == "__main__":
    unittest.main()
