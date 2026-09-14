"""DOCX 前置校验。

P0 实测教训（见 .project/plans/word-support/design.md）：LibreOffice 会把
任意字节流按 Text 滤镜"成功"转换，不能依赖引擎报错——进入任何引擎前，
先在应用层校验文件结构。
"""
import zipfile
from pathlib import Path

from .errors import ConversionError

# OLE2/CFB 容器魔数：加密的 MS Office 文档与 .doc/.xls 老格式都是它
_OLE2_MAGIC = bytes.fromhex("D0CF11E0A1B11AE1")

_REQUIRED_PARTS = ("[Content_Types].xml", "word/document.xml")


class DocxPrecheckError(ValueError):
    """前置校验拒绝。kind: 'corrupt' | 'encrypted'。"""

    def __init__(self, kind: str, message: str):
        self.kind = kind
        super().__init__(message)


def check_docx(path: str) -> None:
    """校验文件是结构完整的 DOCX；不合法抛出 DocxPrecheckError。"""
    file_path = Path(path)
    if not file_path.is_file():
        raise DocxPrecheckError("corrupt", "文件不存在或无法读取")

    head = file_path.open("rb").read(8)
    if head.startswith(_OLE2_MAGIC):
        raise DocxPrecheckError(
            "encrypted",
            "该文件已加密或是旧版 Office 格式。请在 Word/WPS 中打开并另存为 "
            ".docx（或导出 PDF）后再试。",
        )

    try:
        with zipfile.ZipFile(file_path) as archive:
            names = set(archive.namelist())
    except zipfile.BadZipFile:
        raise DocxPrecheckError(
            "corrupt", "文件已损坏或不是有效的 Word 文档。请重新保存后再试。"
        )

    missing = [part for part in _REQUIRED_PARTS if part not in names]
    if missing:
        raise DocxPrecheckError(
            "corrupt", "文件已损坏或不是有效的 Word 文档。请重新保存后再试。"
        )
