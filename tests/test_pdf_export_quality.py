"""PDF export must preserve source pixels independently of placement size."""
import io
import math
from pathlib import Path
import tempfile
import unittest

import fitz
from PIL import Image, ImageDraw

from app import App
from processing.handlers.pdf_handler import PDFHandler
from processing.stamp_instance import StampInstanceManager
from processing.stamp_manager import StampManager


class TestPDFExportQuality(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        self.source = self.root / 'source.pdf'
        with fitz.open() as doc:
            for width, height in ((595.28, 841.89), (841.89, 595.28)):
                page = doc.new_page(width=width, height=height)
                page.insert_text((30, 30), 'Original document text')
            doc.save(str(self.source))
        self.handler = PDFHandler()
        self.handler.load(str(self.source))
        self.addCleanup(self.handler.close)
        self.stamp = Image.new('RGBA', (1200, 600), (255, 0, 0, 128))
        draw = ImageDraw.Draw(self.stamp)
        for x in range(10, 1190, 12):
            draw.line((x, 20, x, 580), fill=(150, 0, 0, 255), width=2)

    def test_original_pixels_and_alpha_survive_small_placement(self):
        output = self.root / 'output.pdf'
        self.handler.export_with_stamp(str(output), self.stamp, (0.3, 0.4), 0.2, {0})
        with fitz.open(str(output)) as doc:
            info = doc[0].get_images(full=True)[0]
            self.assertEqual(info[2:4], self.stamp.size)
            image = Image.open(io.BytesIO(doc.extract_image(info[0])['image'])).convert('RGB')
            self.assertEqual(image.tobytes(), self.stamp.convert('RGB').tobytes())
            alpha = Image.open(io.BytesIO(doc.extract_image(info[1])['image'])).convert('L')
            self.assertEqual(alpha.tobytes(), self.stamp.getchannel('A').tobytes())
            rect = doc[0].get_image_rects(info[0])[0]
            self.assertAlmostEqual(rect.width, doc[0].rect.width * 0.2, places=3)
            self.assertAlmostEqual(rect.height, rect.width / 2, places=3)
            self.assertAlmostEqual(rect.x0, doc[0].rect.width * 0.3, places=3)
            self.assertAlmostEqual(rect.y0, doc[0].rect.height * 0.4, places=3)
            self.assertEqual(doc[1].get_images(), [])
            self.assertIn('Original document text', doc[0].get_text())

    def test_rotation_keeps_source_density_on_portrait_and_landscape(self):
        for angle in (45, 90):
            with self.subTest(angle=angle):
                output = self.root / f'rotated-{angle}.pdf'
                self.handler.export_with_stamp(str(output), self.stamp, (0.2, 0.3), 0.2, {0, 1}, rotation=angle)
                with fitz.open(str(output)) as doc:
                    for page in doc:
                        info = page.get_images(full=True)[0]
                        if angle == 90:
                            self.assertEqual(info[2:4], (600, 1200))
                        else:
                            self.assertGreater(info[2], 1200)
                            self.assertGreater(info[3], 1200)
                        rect = page.get_image_rects(info[0])[0]
                        points_per_pixel = page.rect.width * 0.2 / self.stamp.width
                        self.assertAlmostEqual(rect.width / info[2], points_per_pixel, places=5)
                        self.assertAlmostEqual(rect.height / info[3], points_per_pixel, places=5)
                        radians = math.radians(angle)
                        width = page.rect.width * 0.2
                        expected_width = width * abs(math.cos(radians)) + width / 2 * abs(math.sin(radians))
                        self.assertAlmostEqual(rect.width, expected_width, delta=points_per_pixel * 2)

    def test_multiple_instances_keep_resolution_through_repeated_export(self):
        app = App.__new__(App)
        app.handler = self.handler
        app.stamp_manager = StampManager(str(self.root / 'library'))
        template = app.stamp_manager.add_stamp('高清印章', self.stamp)
        app.instance_manager = StampInstanceManager()
        app.instance_manager.add_instance(template.id, 0)
        app.instance_manager.add_instance(template.id, 1)
        output = self.root / 'multiple.pdf'
        app._export_with_instances(str(output))
        with fitz.open(str(output)) as doc:
            for page in doc:
                images = page.get_images(full=True)
                self.assertTrue(images)
                for info in images:
                    self.assertEqual(info[2:4], self.stamp.size)
