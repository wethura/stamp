"""旋转功能测试"""
import unittest
from PIL import Image
import numpy as np

from processing.stamp import apply_rotation


class TestRotation(unittest.TestCase):
    """旋转功能测试"""

    # @dod rotation-45-preview v1.0
    def test_rotation_45_expands_canvas(self):
        """45°旋转扩展画布"""
        img = Image.new("RGBA", (100, 100), color=(255, 0, 0, 255))
        rotated = apply_rotation(img, 45)

        self.assertGreater(rotated.width, 100)
        self.assertGreater(rotated.height, 100)

    # @dod rotation-45-preview v1.0
    def test_rotation_0_returns_original(self):
        """0°旋转返回原图"""
        img = Image.new("RGBA", (100, 100), color=(255, 0, 0, 255))
        rotated = apply_rotation(img, 0)

        self.assertEqual(rotated.size, img.size)

    # @dod rotation-45-preview v1.0
    def test_rotation_preserves_transparency(self):
        """旋转保持透明背景"""
        img = Image.new("RGBA", (100, 100), color=(0, 0, 0, 0))
        # 中心画一个红点
        pixels = img.load()
        for i in range(45, 55):
            for j in range(45, 55):
                pixels[i, j] = (255, 0, 0, 255)

        rotated = apply_rotation(img, 45)
        arr = np.array(rotated)

        # 角落应该是透明的
        self.assertEqual(arr[0, 0, 3], 0)

    # @dod rotation-90-export v1.0
    def test_rotation_90(self):
        """90°旋转"""
        img = Image.new("RGBA", (100, 50), color=(255, 0, 0, 255))
        rotated = apply_rotation(img, 90)

        self.assertEqual(rotated.width, 50)
        self.assertEqual(rotated.height, 100)


if __name__ == "__main__":
    unittest.main()
