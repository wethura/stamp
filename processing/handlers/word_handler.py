"""Word（DOCX）文档处理器：前置校验 → 本地引擎转换 PDF 快照 → 委托 PDFHandler。

预览、盖章与导出全部基于同一份快照；原始 .docx 不被修改。
"""
import shutil
import tempfile
from pathlib import Path
from typing import Set, Tuple

from PIL import Image

from processing.base import DocumentHandler
from processing.handlers.pdf_handler import PDFHandler
from processing.word_support.service import ConversionService, get_shared_service


class WordHandler(DocumentHandler):
    """DOCX 输入、PDF 输出的处理器（spec：可编辑 DOCX 输出不在范围）。"""

    def __init__(self, service: ConversionService = None):
        # 默认共享单例：与设置对话框共用探测缓存与引擎偏好
        self.service = service or get_shared_service()
        self._pdf: PDFHandler = None
        self._workspace: str = None
        self._source: str = None
        # GUI 可在 load 前指定引擎（引擎选择对话框 / 偏好记忆）
        self.engine_id: str = None
        self.cancel_event = None
        self.last_engine_info = None

    # ── 类级元数据 ───────────────────────────────────────────────────

    @classmethod
    def extensions(cls) -> Set[str]:
        return {".docx", ".DOCX"}

    @classmethod
    def can_handle(cls, path: str) -> bool:
        return Path(path).suffix.lower() == ".docx"

    @classmethod
    def display_name(cls) -> str:
        return "Word 文档"

    # ── 生命周期 ─────────────────────────────────────────────────────

    def load(self, path: str):
        engine = None
        if self.engine_id:
            engine = self.service.probe_all().get(self.engine_id)
        outcome = self.service.convert(
            path, Path(self._ensure_workspace()),
            engine=engine, cancel_event=self.cancel_event,
        )
        self.last_engine_info = engine or self.service.pick_engine()
        self._source = path
        self._pdf = PDFHandler()
        self._pdf.load(outcome.snapshot_path)

    def close(self):
        if self._pdf is not None:
            self._pdf.close()
            self._pdf = None
        if self._workspace is not None:
            shutil.rmtree(self._workspace, ignore_errors=True)
            self._workspace = None

    # ── 快照委托 ─────────────────────────────────────────────────────

    def page_count(self) -> int:
        return self._pdf.page_count()

    def render_page(self, index: int, preview_width: int = 1600) -> Image.Image:
        return self._pdf.render_page(index, preview_width)

    def get_page_size(self, index: int) -> Tuple[float, float]:
        return self._pdf.get_page_size(index)

    def export_with_stamp(self, output_path: str, stamp_img: Image.Image,
                          position_ratio: Tuple[float, float],
                          stamp_size_ratio: float, selected_pages: Set[int],
                          rotation: float = 0.0):
        self._pdf.export_with_stamp(
            output_path=output_path, stamp_img=stamp_img,
            position_ratio=position_ratio,
            stamp_size_ratio=stamp_size_ratio,
            selected_pages=selected_pages, rotation=rotation,
        )

    def default_output_extension(self) -> str:
        return ".pdf"

    # ── 内部 ─────────────────────────────────────────────────────────

    def _ensure_workspace(self) -> str:
        if self._workspace is None:
            self._workspace = tempfile.mkdtemp(prefix="stamp-word-")
        return self._workspace
