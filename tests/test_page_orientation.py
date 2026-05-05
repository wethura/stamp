"""Page orientation and size adaptation tests"""
import unittest
from PIL import Image

from processing.stamp import scale_stamp


class TestPageOrientation(unittest.TestCase):
    """Test stamp sizing adapts to page orientation"""

    def test_stamp_size_based_on_page_width_portrait(self):
        """Portrait page: stamp size based on page width"""
        page_width = 595  # A4 portrait width in points
        stamp_img = Image.new("RGBA", (100, 100), (255, 0, 0, 255))
        size_ratio = 0.2

        scaled = scale_stamp(stamp_img, page_width, size_ratio)

        expected_w = int(page_width * size_ratio)
        self.assertEqual(scaled.width, expected_w)

    def test_stamp_size_based_on_page_width_landscape(self):
        """Landscape page: stamp size based on page width"""
        page_width = 842  # A4 landscape width in points
        stamp_img = Image.new("RGBA", (100, 100), (255, 0, 0, 255))
        size_ratio = 0.2

        scaled = scale_stamp(stamp_img, page_width, size_ratio)

        expected_w = int(page_width * size_ratio)
        self.assertEqual(scaled.width, expected_w)

    def test_same_ratio_gives_proportional_size(self):
        """Same ratio on portrait and landscape gives proportional visual size"""
        portrait_w = 595
        landscape_w = 842
        stamp_img = Image.new("RGBA", (100, 100), (255, 0, 0, 255))
        size_ratio = 0.2

        scaled_portrait = scale_stamp(stamp_img, portrait_w, size_ratio)
        scaled_landscape = scale_stamp(stamp_img, landscape_w, size_ratio)

        # Both should be 20% of their respective page widths
        self.assertEqual(scaled_portrait.width, int(portrait_w * 0.2))
        self.assertEqual(scaled_landscape.width, int(landscape_w * 0.2))

        # Aspect ratio should be preserved
        self.assertEqual(scaled_portrait.width / scaled_portrait.height,
                         scaled_landscape.width / scaled_landscape.height)

    def test_non_square_stamp_scales_correctly(self):
        """Non-square stamp maintains aspect ratio"""
        page_width = 595
        # Rectangle stamp: wider than tall
        stamp_img = Image.new("RGBA", (200, 100), (255, 0, 0, 255))
        size_ratio = 0.3

        scaled = scale_stamp(stamp_img, page_width, size_ratio)

        expected_w = int(page_width * size_ratio)
        expected_h = int(100 * expected_w / 200)
        self.assertEqual(scaled.width, expected_w)
        self.assertEqual(scaled.height, expected_h)


if __name__ == "__main__":
    unittest.main()
