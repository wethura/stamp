"""word_probe 辅助逻辑测试（不依赖已安装的办公软件）。"""
import unittest
import zipfile
from pathlib import Path
import tempfile

import fitz

from scripts.word_probe.make_samples import generate, make_corrupt
from scripts.word_probe.probe import _run_engine
from scripts.word_probe.validate import validate_pdf
from scripts.word_probe.engines.base import (
    ERR_INVALID_PDF, ConvertResult,
)


class TestSampleGeneration(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_generated_samples_are_valid_docx_zips(self):
        made = generate(self.root)
        self.assertEqual({"contract-1p", "contract-10p", "mixed-layout", "corrupt"},
                         set(made))
        for name in ("contract-1p", "contract-10p", "mixed-layout"):
            with zipfile.ZipFile(made[name]) as z:
                self.assertIn("[Content_Types].xml", z.namelist())
                self.assertIn("word/document.xml", z.namelist())

    def test_contract_page_count_is_deterministic(self):
        made = generate(self.root, ["contract-10p"])
        with zipfile.ZipFile(made["contract-10p"]) as z:
            xml = z.read("word/document.xml").decode("utf-8")
        # 9 个显式分页符 + 首末页标记
        self.assertEqual(xml.count('type="page"'), 9)
        self.assertIn("第 10 页 / 共 10 页", xml)

    def test_corrupt_sample_is_not_zip(self):
        target = self.root / "corrupt.docx"
        make_corrupt(target)
        with self.assertRaises(zipfile.BadZipFile):
            zipfile.ZipFile(target)


class TestValidatePdf(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_valid_pdf_passes_with_page_and_text_checks(self):
        pdf_path = self.root / "doc.pdf"
        with fitz.open() as doc:
            page = doc.new_page(width=612, height=792)
            page.insert_text((72, 100), "hello marker")
            doc.save(str(pdf_path))
        info = validate_pdf(pdf_path, expect_pages=1, must_contain=("hello marker",))
        self.assertTrue(info["ok"])
        self.assertEqual(info["page_count"], 1)
        self.assertEqual(info["page_sizes_pt"], [[612.0, 792.0]])
        self.assertTrue(info["text_layer_preserved"])
        self.assertTrue(Path(info["render_png"]).exists())

    def test_missing_marker_fails_validation(self):
        pdf_path = self.root / "doc.pdf"
        with fitz.open() as doc:
            doc.new_page()
            doc.save(str(pdf_path))
        info = validate_pdf(pdf_path, expect_pages=1, must_contain=("不存在的字",))
        self.assertFalse(info["ok"])
        self.assertEqual(info["missing_text"], ["不存在的字"])


class FakeEngine:
    """复刻 engines 接口的最小桩，用于 corrupt 期望语义。"""

    def __init__(self, behave: str):
        self.behave = behave

    def convert(self, work_copy, out_pdf, timeout_s=120):
        if self.behave == "error":
            return ConvertResult(ok=False, engine_id="fake", sample=work_copy.name,
                                 error_kind="convert", error_detail="boom")
        out_pdf.write_bytes(b"%PDF-1.4 fake")
        return ConvertResult(ok=True, engine_id="fake", sample=work_copy.name,
                             pdf_path=str(out_pdf),
                             source_sha_before="x", source_sha_after="x")


class TestCorruptExpectation(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.copy = self.root / "corrupt.docx"
        self.copy.write_bytes(b"garbage")
        self.out = self.root / "corrupt.pdf"

    def test_engine_error_counts_as_pass_for_corrupt(self):
        result = _run_engine(FakeEngine("error"), "corrupt", self.copy, self.out, 10)
        self.assertTrue(result.ok)
        self.assertEqual(result.metrics["classified_error"], "convert")

    def test_engine_success_on_corrupt_counts_as_fail(self):
        result = _run_engine(FakeEngine("success"), "corrupt", self.copy, self.out, 10)
        self.assertFalse(result.ok)
        self.assertEqual(result.error_kind, ERR_INVALID_PDF)


if __name__ == "__main__":
    unittest.main()
