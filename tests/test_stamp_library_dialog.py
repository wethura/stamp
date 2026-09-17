"""Exercise library editing using real Tk widgets and temporary data."""
import tempfile
import unittest
from unittest.mock import MagicMock, patch
from PIL import Image
from processing.stamp_manager import StampManager
from tests.gui_support import shared_ctk_root
from ui.stamp_library_dialog import StampLibraryDialog


class TestStampLibraryDialog(unittest.TestCase):
    def test_edit_discard_save_delete_and_empty_state(self):
        with tempfile.TemporaryDirectory() as folder:
            manager = StampManager(folder)
            first = manager.add_stamp('公章', Image.new('RGBA', (60, 60), 'red'))
            second = manager.add_stamp('财务章', Image.new('RGBA', (90, 30), 'red'))
            root = shared_ctk_root()
            changed = MagicMock()
            deleted = MagicMock(side_effect=lambda sid, parent=None: manager.delete_stamp(sid))
            dialog = StampLibraryDialog(root, manager, changed, deleted)
            try:
                dialog.update()
                self.assertEqual(dialog._selected_id, first.id)
                self.assertLessEqual(dialog._save.winfo_rooty() + dialog._save.winfo_height(),
                                     dialog.winfo_rooty() + dialog.winfo_height())
                dialog._name.delete(0, 'end')
                dialog._name.insert(0, '修改中的名称')
                with patch('ui.stamp_library_dialog.messagebox.askyesno', return_value=False):
                    dialog._select(second.id)
                    dialog._close()
                self.assertTrue(dialog.winfo_exists())
                self.assertEqual(dialog._selected_id, first.id)
                self.assertEqual(manager.get_stamp(first.id).name, '公章')
                with patch('ui.stamp_library_dialog.messagebox.askyesno', return_value=True):
                    dialog._select(second.id)
                dialog._name.delete(0, 'end')
                dialog._name.insert(0, '   ')
                with patch('ui.stamp_library_dialog.messagebox.showwarning') as warning:
                    dialog._save_selected()
                warning.assert_called_once()
                changed.assert_not_called()
                dialog._name.delete(0, 'end')
                dialog._name.insert(0, '新财务章')
                dialog._replacement = Image.new('RGBA', (40, 80), 'blue')
                dialog._save.invoke()
                self.assertEqual(manager.get_stamp(second.id).name, '新财务章')
                self.assertEqual(manager.get_stamp(second.id).get_image().size, (40, 80))
                changed.assert_called_once()
                self.assertFalse(dialog._dirty())
                dialog._delete.invoke()
                self.assertIsNone(manager.get_stamp(second.id))
                self.assertEqual(dialog._selected_id, first.id)
                dialog._delete.invoke()
                self.assertIsNone(dialog._selected_id)
                for button in (dialog._save, dialog._replace, dialog._delete):
                    self.assertEqual(button.cget('state'), 'disabled')
                self.assertEqual(manager.list_stamps(), [])
            finally:
                dialog.destroy()
