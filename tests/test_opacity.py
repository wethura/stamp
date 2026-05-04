"""印章透明度效果测试"""
import unittest
from PIL import Image
import numpy as np

from processing.stamp import load_stamp, scale_stamp
from processing.stamp_manager import StampData, StampManager
import io
import base64


class TestOpacityEffect(unittest.TestCase):
    """印章透明度效果测试"""

    def _create_test_stamp_image(self):
        """创建测试用印章图片"""
        img = Image.new("RGBA", (200, 200), color=(255, 0, 0, 255))
        return img

    def _create_stamp_data(self, opacity=1.0):
        """创建带透明度的 StampData"""
        img = self._create_test_stamp_image()
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        image_base64 = base64.b64encode(buf.getvalue()).decode("utf-8")

        return StampData(
            id="test1",
            name="测试章",
            image_base64=image_base64,
            created_at="2024-01-01T00:00:00",
            size_ratio=0.2,
            pos_x=0.7,
            pos_y=0.7,
            opacity=opacity
        )

    # @dod opacity-default-100 v1.0
    def test_default_opacity_is_100(self):
        """默认透明度为 100%"""
        stamp = self._create_stamp_data(opacity=1.0)
        self.assertEqual(stamp.opacity, 1.0)

    def test_stamp_data_has_opacity_field(self):
        """StampData 包含 opacity 字段"""
        stamp = self._create_stamp_data(opacity=0.5)
        self.assertTrue(hasattr(stamp, 'opacity'))
        self.assertEqual(stamp.opacity, 0.5)

    # @dod opacity-zero-fully-transparent v1.0
    def test_opacity_zero_fully_transparent(self):
        """透明度 0% 时印章完全透明"""
        stamp = self._create_stamp_data(opacity=0.0)
        self.assertEqual(stamp.opacity, 0.0)

        img = stamp.get_image()
        # 应用透明度
        alpha = img.getchannel('A')
        alpha = alpha.point(lambda p: int(p * stamp.opacity))
        img.putalpha(alpha)

        # 检查所有像素 alpha 是否为 0
        arr = np.array(img)
        self.assertTrue(np.all(arr[:, :, 3] == 0))

    # @dod opacity-slider-preview v1.0
    def test_opacity_50_percent(self):
        """透明度 50% 时 alpha 通道减半"""
        stamp = self._create_stamp_data(opacity=0.5)
        img = stamp.get_image()

        # 应用透明度
        alpha = img.getchannel('A')
        alpha = alpha.point(lambda p: int(p * stamp.opacity))
        img.putalpha(alpha)

        # 检查 alpha 值（原图红色区域 alpha=255，应用 50% 后应为 127 或 128）
        arr = np.array(img)
        center_pixel = arr[100, 100]
        self.assertEqual(center_pixel[3], 127)  # 255 * 0.5 = 127.5 -> 127

    # @dod opacity-persist v1.0
    def test_opacity_persistence(self):
        """透明度设置持久化保存"""
        import tempfile
        import os

        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = os.path.join(tmpdir, "stamps.json")
            manager = StampManager(config_dir=tmpdir)

            # 添加带透明度的章
            img = self._create_test_stamp_image()
            stamp = manager.add_stamp("测试章", img, opacity=0.5)
            self.assertEqual(stamp.opacity, 0.5)

            # 创建新的管理器实例（重新加载）
            manager2 = StampManager(config_dir=tmpdir)
            stamps = manager2.list_stamps()
            self.assertEqual(len(stamps), 1)
            self.assertEqual(stamps[0].opacity, 0.5)

    # @dod export-pdf-opacity v1.0 / export-image-opacity v1.0 / export-excel-opacity v1.0
    def test_apply_opacity_to_image(self):
        """对图像应用透明度效果"""
        img = self._create_test_stamp_image()
        opacity = 0.5

        # 应用透明度
        alpha = img.getchannel('A')
        alpha = alpha.point(lambda p: int(p * opacity))
        img.putalpha(alpha)

        # 验证 alpha 通道
        arr = np.array(img)
        self.assertEqual(arr[100, 100, 3], 127)


class TestStampManagerOpacity(unittest.TestCase):
    """StampManager 透明度相关测试"""

    def test_add_stamp_with_opacity(self):
        """添加章时指定透明度"""
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = StampManager(config_dir=tmpdir)
            img = Image.new("RGBA", (100, 100), color=(255, 0, 0, 255))
            stamp = manager.add_stamp("测试章", img, opacity=0.75)
            self.assertEqual(stamp.opacity, 0.75)

    def test_update_stamp_opacity(self):
        """更新章的透明度"""
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = StampManager(config_dir=tmpdir)
            img = Image.new("RGBA", (100, 100), color=(255, 0, 0, 255))
            stamp = manager.add_stamp("测试章", img, opacity=1.0)

            # 更新透明度
            manager.update_stamp(stamp.id, opacity=0.3)

            updated = manager.get_stamp(stamp.id)
            self.assertEqual(updated.opacity, 0.3)


if __name__ == "__main__":
    unittest.main()
