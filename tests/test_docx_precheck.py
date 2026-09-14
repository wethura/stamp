"""DOCX 前置校验测试（A04/A05 防线）。

背景：LibreOffice 会把任意字节流按 Text 滤镜"成功"转换，因此应用层
必须在调用任何引擎前拒绝非 DOCX 文件。
"""
import unittest
import zipfile
from pathlib import Path
import tempfile

from processing.word_support.precheck import DocxPrecheckError, check_docx


def make_valid_docx(path: Path):
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        z.writestr("word/document.xml", "<document/>")


class TestDocxPrecheck(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_valid_docx_passes(self):
        path = self.root / "ok.docx"
        make_valid_docx(path)
        self.assertIsNone(check_docx(str(path)))

    def test_plain_text_rejected_as_corrupt(self):
        path = self.root / "fake.docx"
        path.write_bytes(b"this is not a zip archive")
        with self.assertRaises(DocxPrecheckError) as ctx:
            check_docx(str(path))
        self.assertEqual(ctx.exception.kind, "corrupt")

    def test_zip_without_word_parts_rejected_as_corrupt(self):
        path = self.root / "notword.docx"
        with zipfile.ZipFile(path, "w") as z:
            z.writestr("readme.txt", "a valid zip, but not a docx")
        with self.assertRaises(DocxPrecheckError) as ctx:
            check_docx(str(path))
        self.assertEqual(ctx.exception.kind, "corrupt")

    def test_ole2_magic_rejected_as_encrypted(self):
        path = self.root / "encrypted.docx"
        # 加密的 MS Office 文件是 OLE2/CFB 容器，固定魔数 D0 CF 11 E0
        path.write_bytes(bytes.fromhex("D0CF11E0A1B11AE1") + b"\x00" * 64)
        with self.assertRaises(DocxPrecheckError) as ctx:
            check_docx(str(path))
        self.assertEqual(ctx.exception.kind, "encrypted")

    def test_missing_file_raises_corrupt(self):
        with self.assertRaises(DocxPrecheckError) as ctx:
            check_docx(str(self.root / "ghost.docx"))
        self.assertEqual(ctx.exception.kind, "corrupt")

    def test_error_messages_are_user_facing_chinese(self):
        path = self.root / "fake.docx"
        path.write_bytes(b"garbage")
        with self.assertRaises(DocxPrecheckError) as ctx:
            check_docx(str(path))
        self.assertTrue(ctx.exception.args[0])


if __name__ == "__main__":
    unittest.main()
