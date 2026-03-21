"""PDF 文档处理器"""
import fitz
from PIL import Image
from typing import Set, Tuple, Optional
import io

from processing.base import DocumentHandler
from processing.stamp import scale_stamp, to_png_bytes


class PDFHandler(DocumentHandler):
    """PDF 文档处理器"""

    def __init__(self):
        self._doc: Optional[fitz.Document] = None
        self._path: Optional[str] = None

    @classmethod
    def extensions(cls) -> Set[str]:
        return {'.pdf', '.PDF'}

    @classmethod
    def can_handle(cls, path: str) -> bool:
        return path.lower().endswith('.pdf')

    @classmethod
    def display_name(cls) -> str:
        return "PDF 文档"

    def load(self, path: str) -> None:
        try:
            self._doc = fitz.open(path)
            if self._doc.is_encrypted:
                self._doc.close()
                self._doc = None
                raise RuntimeError("该 PDF 已加密，无法打开")
            self._path = path
        except fitz.FileDataError as e:
            raise RuntimeError(f"PDF 文件损坏或无效: {e}")
        except RuntimeError:
            raise
        except Exception as e:
            raise RuntimeError(f"无法加载文档: {e}")

    def page_count(self) -> int:
        if self._doc is None:
            return 0
        return len(self._doc)

    def render_page(self, index: int, preview_width: int = 1600) -> Image.Image:
        if self._doc is None:
            raise RuntimeError("文档未加载")

        page = self._doc[index]
        scale = preview_width / page.rect.width
        mat = fitz.Matrix(scale, scale)
        pix = page.get_pixmap(matrix=mat, alpha=False)
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        return img

    def get_page_size(self, index: int) -> Tuple[float, float]:
        if self._doc is None:
            raise RuntimeError("文档未加载")

        page = self._doc[index]
        return (page.rect.width, page.rect.height)

    def export_with_stamp(
        self,
        output_path: str,
        stamp_img: Image.Image,
        position_ratio: Tuple[float, float],
        stamp_size_ratio: float,
        selected_pages: Set[int]
    ) -> None:
        if self._doc is None:
            raise RuntimeError("文档未加载")

        x_ratio, y_ratio = position_ratio

        # 创建新文档并复制所有页面
        out_doc = fitz.open()
        out_doc.insert_pdf(self._doc)

        # 在选中页面添加印章
        for page_idx in selected_pages:
            if page_idx < 0 or page_idx >= len(out_doc):
                continue

            page = out_doc[page_idx]
            pw = page.rect.width
            ph = page.rect.height

            scaled = scale_stamp(stamp_img, int(pw), stamp_size_ratio)
            sw, sh = scaled.size
            x = x_ratio * pw
            y = y_ratio * ph
            stamp_rect = fitz.Rect(x, y, x + sw, y + sh)
            page.insert_image(stamp_rect, stream=to_png_bytes(scaled), overlay=True)

        out_doc.save(output_path)
        out_doc.close()

    def default_output_extension(self) -> str:
        return '.pdf'

    def close(self) -> None:
        if self._doc is not None:
            self._doc.close()
            self._doc = None
        self._path = None
