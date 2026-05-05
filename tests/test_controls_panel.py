"""ControlsPanel 测试"""
import unittest
import tkinter as tk
from unittest.mock import MagicMock, patch

from ui.controls_panel import ControlsPanel
from processing.stamp_manager import StampManager, StampData
from processing.stamp_instance import StampInstance


class TestDeleteButton(unittest.TestCase):
    """删除按钮相关测试"""

    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.panel = ControlsPanel(self.root)
        self.panel.pack()
        self.panel.update_idletasks()

        self.mock_manager = MagicMock(spec=StampManager)
        self.panel.set_stamp_manager(self.mock_manager)

    def tearDown(self):
        self.root.destroy()

    def _create_mock_stamp(self, stamp_id, name="测试章"):
        stamp = MagicMock(spec=StampData)
        stamp.id = stamp_id
        stamp.name = name
        from PIL import Image
        img = Image.new("RGBA", (100, 100), color=(255, 0, 0, 255))
        stamp.get_image.return_value = img
        return stamp

    # @dod delete-btn-visible v1.0
    def test_delete_button_visible(self):
        stamp = self._create_mock_stamp("stamp1", "章A")
        self.mock_manager.list_stamps.return_value = [stamp]
        self.mock_manager.get_stamp.return_value = stamp
        self.panel._refresh_stamp_list()
        self.panel.update_idletasks()

        children = self.panel._stamp_inner.winfo_children()
        self.assertEqual(len(children), 1)

        container = children[0]
        container_children = container.winfo_children()

        delete_btn = None
        for w in container_children:
            if isinstance(w, (tk.Button, tk.Label)) and w.cget("text") == "删除":
                delete_btn = w
                break

        self.assertIsNotNone(delete_btn, "应存在 text='删除' 的按钮")
        self.assertEqual(delete_btn.cget("fg"), "red")

    # @dod delete-confirm-dialog v1.0
    @patch("ui.controls_panel.messagebox.askyesno")
    def test_delete_confirm_cancel(self, mock_askyesno):
        stamp = self._create_mock_stamp("stamp1", "章A")
        self.mock_manager.list_stamps.return_value = [stamp]
        self.mock_manager.get_stamp.return_value = stamp
        self.panel._refresh_stamp_list()
        self.panel.update_idletasks()

        mock_askyesno.return_value = False

        container = self.panel._stamp_inner.winfo_children()[0]
        for w in container.winfo_children():
            if isinstance(w, (tk.Button, tk.Label)) and w.cget("text") == "删除":
                w.event_generate("<Button-1>")
                break

        self.mock_manager.delete_stamp.assert_not_called()

    # @dod delete-confirm-dialog v1.0
    @patch("ui.controls_panel.messagebox.askyesno")
    def test_delete_confirm_ok(self, mock_askyesno):
        stamp = self._create_mock_stamp("stamp1", "章A")
        self.mock_manager.list_stamps.return_value = [stamp]
        self.mock_manager.get_stamp.return_value = stamp
        self.panel._refresh_stamp_list()
        self.panel.update_idletasks()

        mock_askyesno.return_value = True

        self.panel._delete_stamp("stamp1")

        self.mock_manager.delete_stamp.assert_called_once_with("stamp1")

    # @dod delete-editing-cleared v1.0
    @patch("ui.controls_panel.messagebox.askyesno")
    def test_delete_editing_stamp_clears_edit_state(self, mock_askyesno):
        stamp_a = self._create_mock_stamp("stamp1", "章A")
        stamp_b = self._create_mock_stamp("stamp2", "章B")
        self.mock_manager.list_stamps.return_value = [stamp_a, stamp_b]
        self.mock_manager.get_stamp.return_value = stamp_a
        self.panel._refresh_stamp_list()
        self.panel.update_idletasks()

        mock_askyesno.return_value = True

        # Set up editing instance for template that is being deleted
        mock_instance_manager = MagicMock()
        mock_inst = StampInstance(
            instance_id="inst1", template_id="stamp1", page_index=0
        )
        mock_instance_manager.get_instance.return_value = mock_inst
        self.panel._instance_manager = mock_instance_manager
        self.panel._editing_instance_id = "inst1"

        self.panel._delete_stamp("stamp1")

        # Editing instance should be cleared since the template was deleted
        self.assertIsNone(self.panel._editing_instance_id)

    # @dod delete-last-empty v1.0
    @patch("ui.controls_panel.messagebox.askyesno")
    def test_delete_last_stamp_empty_list(self, mock_askyesno):
        stamp = self._create_mock_stamp("stamp1", "章A")
        self.mock_manager.list_stamps.return_value = [stamp]
        self.mock_manager.get_stamp.return_value = stamp
        self.panel._refresh_stamp_list()
        self.panel.update_idletasks()

        mock_askyesno.return_value = True

        self.panel._delete_stamp("stamp1")

        self.mock_manager.list_stamps.return_value = []
        self.panel._refresh_stamp_list()


if __name__ == "__main__":
    unittest.main()
