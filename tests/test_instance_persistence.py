"""StampInstance 持久化测试"""
import json
import os
import shutil
import tempfile
import unittest

from processing.stamp_instance import StampInstance, StampInstanceManager


class TestInstancePersistence(unittest.TestCase):
    """实例配置 JSON 持久化测试"""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _make_doc(self, name="doc.pdf"):
        """创建空文档文件并返回路径"""
        path = os.path.join(self.tmpdir, name)
        with open(path, "w") as f:
            f.write("")
        return path

    # @dod instance-save-load-roundtrip v1.0
    def test_save_load_roundtrip(self):
        """save/load 往返一致性：多实例、多页、不同配置值"""
        doc_path = self._make_doc()

        manager = StampInstanceManager(doc_path)
        inst_a = manager.add_instance("t1", 0)
        manager.update_instance(inst_a.instance_id, pos_x=0.2, pos_y=0.3,
                                size_ratio=0.3, rotation=45.0, opacity=0.8)
        inst_b = manager.add_instance("t2", 1)
        manager.update_instance(inst_b.instance_id, pos_x=0.5, pos_y=0.5,
                                size_ratio=0.5, rotation=0.0, opacity=1.0)

        original_a = manager.get_instance(inst_a.instance_id)
        original_b = manager.get_instance(inst_b.instance_id)

        manager.save()

        # 新 manager 从同一文件加载
        new_manager = StampInstanceManager(doc_path)
        new_manager.load()

        loaded_a = new_manager.get_page_instances(0)
        loaded_b = new_manager.get_page_instances(1)

        self.assertEqual(len(loaded_a), 1)
        self.assertEqual(len(loaded_b), 1)

        # 用 dataclass 相等性验证所有字段
        self.assertEqual(loaded_a[0], original_a)
        self.assertEqual(loaded_b[0], original_b)

    # @dod instance-persist-file-format v1.0
    def test_persist_file_format(self):
        """持久化文件格式：命名规则、JSON 合法性、顶层结构"""
        doc_path = self._make_doc("report.pdf")

        manager = StampInstanceManager(doc_path)
        manager.add_instance("t1", 0)
        manager.save()

        expected_file = os.path.join(self.tmpdir, ".report.pdf.stamp-config.json")
        self.assertTrue(os.path.exists(expected_file))

        with open(expected_file, "r") as f:
            data = json.load(f)

        self.assertIn("instances", data)
        self.assertIsInstance(data["instances"], list)
        self.assertEqual(len(data["instances"]), 1)

    # @dod instance-save-empty v1.0
    def test_save_empty_instances(self):
        """空实例列表保存：文件内容为 {"instances": []}"""
        doc_path = self._make_doc("empty.pdf")

        manager = StampInstanceManager(doc_path)
        manager.save()

        expected_file = os.path.join(self.tmpdir, ".empty.pdf.stamp-config.json")
        self.assertTrue(os.path.exists(expected_file))

        with open(expected_file, "r") as f:
            data = json.load(f)

        self.assertEqual(data, {"instances": []})

        # 从空文件加载后实例列表为空
        new_manager = StampInstanceManager(doc_path)
        new_manager.load()
        self.assertEqual(new_manager.get_page_instances(0), [])

    # @dod doc-move-config-lost v1.0
    def test_doc_move_config_lost(self):
        """文档移动后配置丢失"""
        doc_path = self._make_doc()

        manager = StampInstanceManager(doc_path)
        manager.add_instance("t1", 0)
        manager.save()

        # 确认配置文件存在
        config_file = os.path.join(self.tmpdir, ".doc.pdf.stamp-config.json")
        self.assertTrue(os.path.exists(config_file))

        # 移动文档到新目录
        other_dir = os.path.join(self.tmpdir, "other")
        os.makedirs(other_dir)
        new_doc_path = os.path.join(other_dir, "doc.pdf")
        shutil.move(doc_path, new_doc_path)

        # 新目录下不存在配置文件
        new_config = os.path.join(other_dir, ".doc.pdf.stamp-config.json")
        self.assertFalse(os.path.exists(new_config))

        # 新 manager 加载后实例为空
        new_manager = StampInstanceManager(new_doc_path)
        new_manager.load()
        self.assertEqual(new_manager.get_page_instances(0), [])


if __name__ == "__main__":
    unittest.main()
