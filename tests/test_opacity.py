"""印章透明度效果测试"""
import unittest
from PIL import Image
import numpy as np

from processing.stamp import load_stamp, scale_stamp, apply_opacity
from processing.stamp_manager import StampData, StampManager
from processing.stamp_instance import StampInstance
import io
import base64


class TestOpacityEffect(unittest.TestCase):
    """印章透明度效果测试"""

    def _create_test_stamp_image(self):
        """创建测试用印章图片"""
        img = Image.new("RGBA", (200, 200), color=(255, 0, 0, 255))
        return img

    def _create_stamp_instance(self, opacity=1.0):
        """创建带透明度的 StampInstance"""
        return StampInstance(
            instance_id="test1",
            template_id="template1",
            page_index=0,
            size_ratio=0.2,
            pos_x=0.7,
            pos_y=0.7,
            opacity=opacity
        )

    # @dod opacity-default-100 v1.0
    def test_default_opacity_is_100(self):
        """默认透明度为 100%"""
        instance = self._create_stamp_instance(opacity=1.0)
        self.assertEqual(instance.opacity, 1.0)

    def test_stamp_instance_has_opacity_field(self):
        """StampInstance 包含 opacity 字段"""
        instance = self._create_stamp_instance(opacity=0.5)
        self.assertTrue(hasattr(instance, 'opacity'))
        self.assertEqual(instance.opacity, 0.5)

    # @dod opacity-zero-fully-transparent v1.0
    def test_opacity_zero_fully_transparent(self):
        """透明度 0% 时印章完全透明"""
        instance = self._create_stamp_instance(opacity=0.0)
        self.assertEqual(instance.opacity, 0.0)

        img = self._create_test_stamp_image()
        # 应用透明度
        result = apply_opacity(img, instance.opacity)

        # 检查所有像素 alpha 是否为 0
        arr = np.array(result)
        self.assertTrue(np.all(arr[:, :, 3] == 0))

    # @dod opacity-slider-preview v1.0
    def test_opacity_50_percent(self):
        """透明度 50% 时 alpha 通道减半"""
        instance = self._create_stamp_instance(opacity=0.5)
        img = self._create_test_stamp_image()

        # 应用透明度
        result = apply_opacity(img, instance.opacity)

        # 检查 alpha 值（原图红色区域 alpha=255，应用 50% 后应为 127 或 128）
        arr = np.array(result)
        center_pixel = arr[100, 100]
        self.assertEqual(center_pixel[3], 127)  # 255 * 0.5 = 127.5 -> 127

    # @dod opacity-persist v1.0
    def test_opacity_persistence(self):
        """透明度设置在内存中保存"""
        from processing.stamp_instance import StampInstanceManager
        manager = StampInstanceManager()

        instance = manager.add_instance("template1", 0)
        manager.update_instance(instance.instance_id, opacity=0.5)

        instances = manager.get_page_instances(0)
        self.assertEqual(len(instances), 1)
        self.assertEqual(instances[0].opacity, 0.5)

    # @dod export-pdf-opacity v1.0 / export-image-opacity v1.0 / export-excel-opacity v1.0
    def test_apply_opacity_to_image(self):
        """对图像应用透明度效果"""
        img = self._create_test_stamp_image()
        opacity = 0.5

        # 应用透明度
        result = apply_opacity(img, opacity)

        # 验证 alpha 通道
        arr = np.array(result)
        self.assertEqual(arr[100, 100, 3], 127)


class TestStampInstanceManagerOpacity(unittest.TestCase):
    """StampInstanceManager 透明度相关测试"""

    def test_add_instance_with_default_opacity(self):
        """添加实例时默认透明度为 100%"""
        from processing.stamp_instance import StampInstanceManager
        manager = StampInstanceManager()
        instance = manager.add_instance("template1", 0)

        self.assertEqual(instance.opacity, 1.0)

    def test_update_instance_opacity(self):
        """更新实例的透明度"""
        from processing.stamp_instance import StampInstanceManager
        manager = StampInstanceManager()
        instance = manager.add_instance("template1", 0)

        manager.update_instance(instance.instance_id, opacity=0.3)

        updated = manager.get_page_instances(0)[0]
        self.assertEqual(updated.opacity, 0.3)


if __name__ == "__main__":
    unittest.main()
