"""ControlsPanel 测试"""
import unittest
import tkinter as tk
import customtkinter as ctk
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

    def test_cards_have_no_delete_button(self):
        stamp = self._create_mock_stamp("stamp1", "章A")
        self.mock_manager.list_stamps.return_value = [stamp]
        self.mock_manager.get_stamp.return_value = stamp
        self.panel._refresh_stamp_list()
        self.panel.update_idletasks()

        children = self.panel._scroll_frame.winfo_children()
        self.assertEqual(len(children), 1)
        self.assertFalse(any(isinstance(widget, (tk.Button, ctk.CTkButton))
                             for widget in children[0].winfo_children()))

    # @dod delete-confirm-dialog v1.0
    @patch("ui.controls_panel.messagebox.askyesno")
    def test_delete_confirm_cancel(self, mock_askyesno):
        stamp = self._create_mock_stamp("stamp1", "章A")
        self.mock_manager.list_stamps.return_value = [stamp]
        self.mock_manager.get_stamp.return_value = stamp
        self.panel._refresh_stamp_list()
        self.panel.update_idletasks()

        mock_askyesno.return_value = False

        self.assertFalse(self.panel._delete_stamp("stamp1"))
        mock_askyesno.assert_called_once()

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
