"""Library edits persist templates and keep document placements consistent."""
import tempfile
import unittest
from unittest.mock import MagicMock, patch
from PIL import Image
from app import App
from processing.stamp_manager import StampManager
from processing.stamp_instance import StampInstanceManager


class TestStampLibrary(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.manager = StampManager(self.folder.name)
        self.stamp = self.manager.add_stamp('原章', Image.new('RGBA', (30, 30), 'red'))

    def test_replace_and_rename_persist_without_changing_identity(self):
        self.manager.update_stamp(self.stamp.id, name='新名称', image=Image.new('RGBA', (70, 20), 'blue'))
        loaded = StampManager(self.folder.name).get_stamp(self.stamp.id)
        self.assertEqual(loaded.name, '新名称')
        self.assertEqual(loaded.created_at, self.stamp.created_at)
        self.assertEqual(loaded.get_image().size, (70, 20))
        self.assertEqual(loaded.get_image().getpixel((0, 0)), (0, 0, 255, 255))

    def test_rename_preserves_image(self):
        image = self.stamp.image_base64
        self.manager.update_stamp(self.stamp.id, name='财务章')
        self.assertEqual(self.stamp.image_base64, image)
        self.assertEqual(StampManager(self.folder.name).get_stamp(self.stamp.id).name, '财务章')

    def test_failed_save_keeps_original_memory_and_file(self):
        with patch('processing.stamp_manager.os.replace', side_effect=OSError('磁盘错误')):
            with self.assertRaises(OSError):
                self.manager.update_stamp(self.stamp.id, name='未保存', image=Image.new('RGBA', (10, 10)))
        self.assertEqual(self.stamp.name, '原章')
        self.assertEqual(self.stamp.get_image().size, (30, 30))
        self.assertEqual(StampManager(self.folder.name).get_stamp(self.stamp.id).name, '原章')

    def test_failed_delete_restores_stamp(self):
        with patch.object(self.manager, '_save', side_effect=OSError('磁盘错误')):
            with self.assertRaises(OSError):
                self.manager.delete_stamp(self.stamp.id)
        self.assertIs(self.manager.get_stamp(self.stamp.id), self.stamp)

    def make_app(self):
        app = App.__new__(App)
        app.stamp_manager = self.manager
        app.instance_manager = StampInstanceManager()
        app.window = MagicMock()
        app._refresh_preview = MagicMock()
        return app

    def test_deleted_template_removes_only_its_placements(self):
        app = self.make_app()
        other = self.manager.add_stamp('其他章', Image.new('RGBA', (20, 20)))
        removed = app.instance_manager.add_instance(self.stamp.id, 0)
        app.instance_manager.add_instance(self.stamp.id, 1)
        kept = app.instance_manager.add_instance(other.id, 1)
        app._selected_instance_id = removed.instance_id
        self.manager.delete_stamp(self.stamp.id)
        app.on_stamp_library_changed()
        self.assertEqual(app.instance_manager.list_instances(), [kept])
        self.assertIsNone(app._selected_instance_id)
        app.window.controls.set_editing_instance.assert_called_once_with(None)
        app._refresh_preview.assert_called_once()

    def test_template_edit_keeps_placement_settings(self):
        app = self.make_app()
        instance = app.instance_manager.add_instance(self.stamp.id, 2)
        app.instance_manager.update_instance(instance.instance_id, rotation=45, pos_x=0.3)
        app._selected_instance_id = instance.instance_id
        self.manager.update_stamp(self.stamp.id, image=Image.new('RGBA', (60, 20)))
        app.on_stamp_library_changed()
        self.assertEqual(instance.rotation, 45)
        self.assertEqual(instance.pos_x, 0.3)
        self.assertEqual(app._selected_instance_id, instance.instance_id)
        self.assertEqual(app.get_template_image(instance.template_id).size, (60, 20))
        app._refresh_preview.assert_called_once()
