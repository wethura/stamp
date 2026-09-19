"""remove_white_background 数值安全测试。

回归背景：np.where 的两个分支都会被求值，纯黑像素（mx=0）触发 0/0 的
RuntimeWarning——经日志重定向后以 ERROR 级别出现在用户日志里，污染诊断
信息（2026-09-19 Windows 用户日志实况）。
"""
import unittest
import warnings

from PIL import Image

from processing.stamp import remove_white_background


class TestRemoveWhiteBackground(unittest.TestCase):
    def _image_with_black_pixel(self) -> Image.Image:
        img = Image.new("RGBA", (8, 8), (255, 255, 255, 255))
        img.putpixel((4, 4), (0, 0, 0, 255))
        return img

    def test_black_pixel_no_runtime_warning(self):
        with warnings.catch_warnings():
            warnings.simplefilter("error", RuntimeWarning)
            result = remove_white_background(self._image_with_black_pixel())

        self.assertEqual(result.getpixel((0, 0))[3], 0)   # 白背景移除
        self.assertEqual(result.getpixel((4, 4))[3], 255)  # 黑像素保留


if __name__ == "__main__":
    unittest.main()
