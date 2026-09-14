"""WordHandler 行为与注册测试（桩引擎，不依赖办公软件）。"""
import tempfile
import unittest
import zipfile
from pathlib import Path

import fitz
from PIL import Image

from processing import HandlerRegistry
from processing.handlers.word_handler import WordHandler
from processing.word_support.service import ConversionError, ConversionService
from processing.word_support.engines import EngineInfo


def make_docx(path: Path):
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        z.writestr("word/document.xml", "<document/>")


def make_pdf(path: Path, pages: int = 3):
    with fitz.open() as doc:
        for i in range(pages):
            doc.new_page(width=595, height=842)
        doc.save(str(path))


class StubEngine:
    def __init__(self, pages=3, available=True, manual=False):
        self.engine_id = "stub"
        self.name = "Stub"
        self.pages = pages
        self.available = available
        self.manual = manual

    def probe(self) -> EngineInfo:
        return EngineInfo("stub", "Stub", self.available, version="1.0",
                          detail="stub", manual_path_only=self.manual)

    def convert(self, work_copy, out_pdf, timeout_s=120.0, cancel_event=None):
        make_pdf(out_pdf, self.pages)
        return {"ok": True, "pdf_path": str(out_pdf)}


def make_service(tmp_root: Path, **engine_kw):
    return ConversionService(
        engines=[StubEngine(**engine_kw)],
        preference_path=str(tmp_root / "pref.json"),
    )


class TestWordHandlerBasics(unittest.TestCase):
    def test_extensions_and_metadata(self):
        self.assertEqual(WordHandler.extensions(), {".docx", ".DOCX"})
        self.assertTrue(WordHandler.can_handle("a.docx"))
        self.assertTrue(WordHandler.can_handle("a.DOCX"))
        self.assertFalse(WordHandler.can_handle("a.pdf"))
        self.assertFalse(WordHandler.can_handle("a.doc"))
        self.assertEqual(WordHandler.display_name(), "Word 文档")
        handler = WordHandler()
        self.assertEqual(handler.default_output_extension(), ".pdf")

    def test_load_delegates_pages_to_snapshot(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        source = root / "in.docx"
        make_docx(source)
        handler = WordHandler(service=make_service(root, pages=3))
        self.addCleanup(handler.close)
        handler.load(str(source))
        self.assertEqual(handler.page_count(), 3)
        size = handler.get_page_size(0)
        self.assertAlmostEqual(size[0], 595.0, places=1)
        self.assertAlmostEqual(size[1], 842.0, places=1)
        page_img = handler.render_page(0)
        self.assertIsInstance(page_img, Image.Image)

    def test_export_with_stamp_draws_only_selected_pages(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        source = root / "in.docx"
        make_docx(source)
        out = root / "out.pdf"
        handler = WordHandler(service=make_service(root, pages=2))
        self.addCleanup(handler.close)
        handler.load(str(source))
        stamp = Image.new("RGBA", (200, 200), (180, 0, 0, 200))
        handler.export_with_stamp(str(out), stamp, (0.3, 0.3), 0.2, {0})
        with fitz.open(str(out)) as doc:
            self.assertEqual(doc.page_count, 2)
            self.assertTrue(doc[0].get_images(full=True), "第 1 页应有印章")
            self.assertFalse(doc[1].get_images(full=True), "第 2 页不应有印章")

    def test_engine_missing_raises_with_manual_hint(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        source = root / "in.docx"
        make_docx(source)
        handler = WordHandler(service=make_service(root, available=False))
        with self.assertRaises(ConversionError) as ctx:
            handler.load(str(source))
        self.assertEqual(ctx.exception.kind, "engine_missing")
        self.assertIn("PDF", str(ctx.exception), "错误文案必须给出手动导入 PDF 出口")

    def test_corrupt_source_raises_precheck_without_engine_call(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        source = root / "in.docx"
        source.write_bytes(b"garbage")
        handler = WordHandler(service=make_service(root))
        with self.assertRaises(ConversionError) as ctx:
            handler.load(str(source))
        self.assertEqual(ctx.exception.kind, "precheck")

    def test_close_cleans_snapshot_workspace(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        source = root / "in.docx"
        make_docx(source)
        handler = WordHandler(service=make_service(root))
        handler.load(str(source))
        workspace = handler._workspace
        handler.close()
        self.assertFalse(Path(workspace).exists(), "close 应清理快照工作目录")


class TestRegistration(unittest.TestCase):
    def test_registry_resolves_docx(self):
        handler = HandlerRegistry.get_handler("something.docx")
        self.assertIsInstance(handler, WordHandler)
        self.assertIsNone(HandlerRegistry.get_handler("note.txt"))

    def test_word_appears_in_file_filters(self):
        filters = HandlerRegistry.get_file_filters()
        word_filters = [f for f in filters if "Word" in f[0]]
        self.assertTrue(word_filters, f"文件过滤器应包含 Word: {filters}")
        self.assertIn("*.docx", word_filters[0][1])

    def test_output_filter_is_pdf(self):
        handler = WordHandler()
        name, pattern = HandlerRegistry.get_output_filter(handler)
        self.assertEqual(pattern, "*.pdf")


if __name__ == "__main__":
    unittest.main()
