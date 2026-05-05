"""Per-page stamp configuration tests - integration with app, controls, preview"""
import unittest
from unittest.mock import MagicMock, patch
import tempfile
import os
from PIL import Image

from processing.stamp_instance import StampInstance, StampInstanceManager
from processing.stamp_manager import StampData, StampManager


class TestAppInstanceIntegration(unittest.TestCase):
    """Test App class integration with StampInstanceManager"""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.doc_path = os.path.join(self.temp_dir, "test.pdf")
        open(self.doc_path, 'w').close()

        self.stamp_img = Image.new("RGBA", (100, 100), (255, 0, 0, 255))

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _make_app(self):
        """Create a partially mocked App for testing"""
        from app import App
        app = App.__new__(App)
        app.handler = None
        app.doc_path = None
        app.pages = []
        app.stamp_manager = StampManager(config_dir=self.temp_dir)
        app.instance_manager = None
        app.selected_pages = set()
        app.current_preview_page = 0
        app._selected_instance_id = None
        app.window = MagicMock()
        return app

    def test_instance_manager_created_on_document_load(self):
        app = self._make_app()

        mock_handler = MagicMock()
        mock_handler.page_count.return_value = 3
        mock_handler.render_page.return_value = Image.new("RGB", (800, 600))

        app._load_document(self.doc_path, mock_handler)

        self.assertIsNotNone(app.instance_manager)

    def test_create_instance_on_double_click(self):
        app = self._make_app()
        app.doc_path = self.doc_path
        app.pages = [Image.new("RGB", (800, 600)) for _ in range(3)]
        app.instance_manager = StampInstanceManager()
        app.current_preview_page = 1
        app.selected_pages = {0, 1, 2}

        template = app.stamp_manager.add_stamp("TestStamp", self.stamp_img)

        app.create_instance_from_template(template.id)

        instances = app.instance_manager.get_page_instances(1)
        self.assertEqual(len(instances), 1)
        self.assertEqual(instances[0].template_id, template.id)
        self.assertEqual(instances[0].page_index, 1)

    def test_delete_instance_by_id(self):
        app = self._make_app()
        app.doc_path = self.doc_path
        app.pages = [Image.new("RGB", (800, 600))]
        app.instance_manager = StampInstanceManager()
        app.current_preview_page = 0
        app.selected_pages = {0}

        template = app.stamp_manager.add_stamp("TestStamp", self.stamp_img)
        instance = app.instance_manager.add_instance(template.id, 0)

        app.delete_instance(instance.instance_id)

        instances = app.instance_manager.get_page_instances(0)
        self.assertEqual(len(instances), 0)

    def test_update_instance_position(self):
        app = self._make_app()
        app.doc_path = self.doc_path
        app.pages = [Image.new("RGB", (800, 600))]
        app.instance_manager = StampInstanceManager()
        app.current_preview_page = 0
        app.selected_pages = {0}

        template = app.stamp_manager.add_stamp("TestStamp", self.stamp_img)
        instance = app.instance_manager.add_instance(template.id, 0)

        app.on_instance_position_changed(instance.instance_id, 0.5, 0.6)

        updated = app.instance_manager.get_instance(instance.instance_id)
        self.assertAlmostEqual(updated.pos_x, 0.5)
        self.assertAlmostEqual(updated.pos_y, 0.6)

    def test_update_instance_property(self):
        app = self._make_app()
        app.doc_path = self.doc_path
        app.pages = [Image.new("RGB", (800, 600))]
        app.instance_manager = StampInstanceManager()
        app.current_preview_page = 0
        app.selected_pages = {0}

        template = app.stamp_manager.add_stamp("TestStamp", self.stamp_img)
        instance = app.instance_manager.add_instance(template.id, 0)

        app.update_instance_property(instance.instance_id, size_ratio=0.5)
        app.update_instance_property(instance.instance_id, opacity=0.7)
        app.update_instance_property(instance.instance_id, rotation=45.0)

        updated = app.instance_manager.get_instance(instance.instance_id)
        self.assertAlmostEqual(updated.size_ratio, 0.5)
        self.assertAlmostEqual(updated.opacity, 0.7)
        self.assertAlmostEqual(updated.rotation, 45.0)

    def test_get_page_stamp_data_for_preview(self):
        app = self._make_app()
        app.doc_path = self.doc_path
        app.pages = [Image.new("RGB", (800, 600))]
        app.instance_manager = StampInstanceManager()
        app.current_preview_page = 0
        app.selected_pages = {0}

        template = app.stamp_manager.add_stamp("TestStamp", self.stamp_img)
        instance = app.instance_manager.add_instance(template.id, 0)
        app.instance_manager.update_instance(instance.instance_id, rotation=30.0, opacity=0.8)

        data = app.get_page_stamp_data(0)
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0].instance_id, instance.instance_id)
        self.assertEqual(data[0].template_id, template.id)
        self.assertAlmostEqual(data[0].rotation, 30.0)
        self.assertAlmostEqual(data[0].opacity, 0.8)


class TestPreviewCanvasInstances(unittest.TestCase):
    """Test preview canvas with instance-based rendering"""

    def test_build_instance_display_data_with_rotation(self):
        from ui.preview_canvas import build_instance_display_data

        instances = [
            StampInstance(
                instance_id="inst1",
                template_id="tmpl1",
                page_index=0,
                pos_x=0.5,
                pos_y=0.5,
                size_ratio=0.2,
                rotation=45.0,
                opacity=0.8
            )
        ]

        stamp_img = Image.new("RGBA", (100, 100), (255, 0, 0, 255))
        template_images = {"tmpl1": stamp_img}

        display_list = build_instance_display_data(instances, template_images, 800, 600)

        self.assertEqual(len(display_list), 1)
        disp_w, disp_h, x, y = display_list[0][:4]
        expected_w = int(800 * 0.2)
        self.assertEqual(disp_w, expected_w)
        # Position should match the instance's ratio
        self.assertEqual(x, int(0.5 * 800))
        self.assertEqual(y, int(0.5 * 600))

    def test_build_instance_display_data_no_rotation(self):
        from ui.preview_canvas import build_instance_display_data

        instances = [
            StampInstance(
                instance_id="inst1",
                template_id="tmpl1",
                page_index=0,
                pos_x=0.3,
                pos_y=0.3,
                size_ratio=0.2,
                rotation=0.0,
                opacity=1.0
            )
        ]

        stamp_img = Image.new("RGBA", (100, 100), (255, 0, 0, 255))
        template_images = {"tmpl1": stamp_img}

        display_list = build_instance_display_data(instances, template_images, 800, 600)

        self.assertEqual(len(display_list), 1)
        disp_w, disp_h, x, y = display_list[0][:4]
        expected_w = int(800 * 0.2)
        self.assertEqual(disp_w, expected_w)

    def test_find_instance_at_position(self):
        instances = [
            StampInstance(
                instance_id="inst1",
                template_id="tmpl1",
                page_index=0,
                pos_x=0.5,
                pos_y=0.5,
                size_ratio=0.2,
                rotation=0.0,
                opacity=1.0
            )
        ]
        stamp_img = Image.new("RGBA", (100, 100), (255, 0, 0, 255))

        # At the instance position should find it
        from ui.preview_canvas import build_instance_display_data
        display_list = build_instance_display_data(instances, {"tmpl1": stamp_img}, 800, 600)

        sw, sh, px, py = display_list[0][:4]
        disp_w, disp_h = 800, 600

        # Ratio inside the stamp area
        ratio_x = (px + sw / 2) / disp_w
        ratio_y = (py + sh / 2) / disp_h
        self.assertEqual(_find_at(display_list, instances, ratio_x, ratio_y, disp_w, disp_h), "inst1")

        # Ratio outside should miss
        self.assertIsNone(_find_at(display_list, instances, 0.05, 0.05, disp_w, disp_h))


class TestControlsPanelTemplateLibrary(unittest.TestCase):
    """Test ControlsPanel as template library"""

    def test_double_click_triggers_callback(self):
        create_callback = MagicMock()

        from ui.controls_panel import ControlsPanel
        panel = ControlsPanel.__new__(ControlsPanel)
        panel.on_create_instance = create_callback
        panel._stamp_manager = MagicMock()
        panel._stamp_manager.get_stamp.return_value = StampData(
            id="tmpl1", name="TestStamp", image_base64="", created_at="2026-01-01"
        )

        panel._on_stamp_double_click("tmpl1")

        create_callback.assert_called_once_with("tmpl1")

    def test_edit_controls_show_instance_info(self):
        from ui.controls_panel import ControlsPanel
        panel = ControlsPanel.__new__(ControlsPanel)

        panel._editing_label = MagicMock()
        panel._size_var = MagicMock()
        panel._size_label = MagicMock()
        panel._size_slider = MagicMock()
        panel._opacity_var = MagicMock()
        panel._opacity_label = MagicMock()
        panel._opacity_slider = MagicMock()
        panel._rotation_var = MagicMock()
        panel._rotation_label = MagicMock()
        panel._rotation_slider = MagicMock()
        panel._stamp_manager = MagicMock()
        panel._instance_manager = MagicMock()

        panel._stamp_manager.get_stamp.return_value = StampData(
            id="tmpl1", name="TestStamp", image_base64="", created_at="2026-01-01"
        )

        panel._instance_manager.get_instance.return_value = StampInstance(
            instance_id="inst1",
            template_id="tmpl1",
            page_index=2,
            size_ratio=0.3,
            opacity=0.7,
            rotation=45.0
        )

        panel._editing_instance_id = "inst1"
        panel._update_edit_controls()

        label_text = panel._editing_label.config.call_args[1].get('text', '')
        self.assertIn("TestStamp", label_text)
        self.assertIn("3", label_text)  # page_index 2 -> display "第3页"


def _find_at(display_list, instances, ratio_x, ratio_y, disp_w, disp_h):
    """Find which instance is at the given ratio position"""
    for (sw, sh, px, py, *_), instance in zip(display_list, instances):
        x1 = px / disp_w
        y1 = py / disp_h
        x2 = x1 + (sw / disp_w)
        y2 = y1 + (sh / disp_h)
        if x1 <= ratio_x <= x2 and y1 <= ratio_y <= y2:
            return instance.instance_id
    return None


if __name__ == "__main__":
    unittest.main()
