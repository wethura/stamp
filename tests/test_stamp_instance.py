"""StampInstance 数据模型测试"""
import unittest
from processing.stamp_instance import StampInstance, StampInstanceManager


class TestStampInstanceManager(unittest.TestCase):

    # @dod instance-create-page v1.0
    def test_add_instance(self):
        """添加实例并关联到页面"""
        manager = StampInstanceManager()
        instance = manager.add_instance("template_1", 0)

        self.assertEqual(instance.template_id, "template_1")
        self.assertEqual(instance.page_index, 0)
        self.assertIsNotNone(instance.instance_id)

    # @dod instance-create-page v1.0
    def test_get_page_instances(self):
        """获取页面实例列表"""
        manager = StampInstanceManager()
        manager.add_instance("template_1", 0)
        instances = manager.get_page_instances(0)

        self.assertEqual(len(instances), 1)
        self.assertEqual(instances[0].template_id, "template_1")

    # @dod same-template-multi-instance v1.0
    def test_same_template_multiple_instances(self):
        """同一模板在同一页创建多个实例"""
        manager = StampInstanceManager()
        manager.add_instance("template_1", 0)
        manager.add_instance("template_1", 0)
        instances = manager.get_page_instances(0)

        self.assertEqual(len(instances), 2)
        self.assertEqual(instances[0].template_id, instances[1].template_id)
        self.assertNotEqual(instances[0].instance_id, instances[1].instance_id)

    # @dod backspace-delete-instance v1.0
    def test_remove_instance(self):
        """删除实例"""
        manager = StampInstanceManager()
        instance = manager.add_instance("template_1", 0)
        manager.remove_instance(instance.instance_id)
        instances = manager.get_page_instances(0)

        self.assertEqual(len(instances), 0)

    # @dod instance-drag-position v1.0
    def test_update_instance_position(self):
        """更新实例位置"""
        manager = StampInstanceManager()
        instance = manager.add_instance("template_1", 0)
        manager.update_instance(instance.instance_id, pos_x=0.8, pos_y=0.8)
        updated = manager.get_page_instances(0)[0]

        self.assertEqual(updated.pos_x, 0.8)
        self.assertEqual(updated.pos_y, 0.8)

    # @dod size-slider-instance-only v1.0
    def test_update_instance_size(self):
        """更新实例大小"""
        manager = StampInstanceManager()
        instance = manager.add_instance("template_1", 0)
        manager.update_instance(instance.instance_id, size_ratio=0.5)
        updated = manager.get_page_instances(0)[0]

        self.assertEqual(updated.size_ratio, 0.5)

    # @dod opacity-slider-instance-only v1.0
    def test_update_instance_opacity(self):
        """更新实例透明度"""
        manager = StampInstanceManager()
        instance = manager.add_instance("template_1", 0)
        manager.update_instance(instance.instance_id, opacity=0.5)
        updated = manager.get_page_instances(0)[0]

        self.assertEqual(updated.opacity, 0.5)

    # @dod rotation-45-preview v1.0
    def test_update_instance_rotation(self):
        """更新实例旋转角度"""
        manager = StampInstanceManager()
        instance = manager.add_instance("template_1", 0)
        manager.update_instance(instance.instance_id, rotation=45.0)
        updated = manager.get_page_instances(0)[0]

        self.assertEqual(updated.rotation, 45.0)

    def test_get_instance_by_id(self):
        """按 ID 获取单个实例"""
        manager = StampInstanceManager()
        instance = manager.add_instance("template_1", 0)
        found = manager.get_instance(instance.instance_id)

        self.assertIsNotNone(found)
        self.assertEqual(found.template_id, "template_1")

    def test_list_all_instances(self):
        """获取全部实例"""
        manager = StampInstanceManager()
        manager.add_instance("t1", 0)
        manager.add_instance("t2", 1)
        all_instances = manager.list_instances()

        self.assertEqual(len(all_instances), 2)

    def test_remove_nonexistent_instance(self):
        """删除不存在的实例返回 False"""
        manager = StampInstanceManager()
        self.assertFalse(manager.remove_instance("nonexistent"))

    def test_update_nonexistent_instance(self):
        """更新不存在的实例返回 None"""
        manager = StampInstanceManager()
        result = manager.update_instance("nonexistent", pos_x=0.5)
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
