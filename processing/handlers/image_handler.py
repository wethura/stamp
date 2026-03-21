"""图片文档处理器"""
from PIL import Image
from typing import Set, Tuple, Optional
import fitz

from processing.base import DocumentHandler
from processing.stamp import scale_stamp, to_png_bytes


# 支持的图片扩展名
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".tif", ".webp"}


class ImageHandler(DocumentHandler):
    """图片文档处理器

    将图片作为单页文档处理，导出时转换为 PDF。
    """

    def __init__(self):
        self._img: Optional[Image.Image] = None
        self._path: Optional[str] = None

    @classmethod
    def extensions(cls) -> Set[str]:
        return IMAGE_EXTENSIONS

    @classmethod
    def can_handle(cls, path: str) -> bool:
        import os
        ext = os.path.splitext(path)[1].lower()
        return ext in IMAGE_EXTENSIONS

    @classmethod
    def display_name(cls) -> str:
        return "图片文件"

    def load(self, path: str) -> None:
        try:
            self._img = Image.open(path).convert("RGB")
            self._path = path
        except Exception as e:
            raise RuntimeError(f"无法加载图片: {e}")

    def page_count(self) -> int:
        # 图片始终只有一页
        return 1 if self._img is not None else 0

    def render_page(self, index: int, preview_width: int = 1600) -> Image.Image:
        if self._img is None:
            raise RuntimeError("图片未加载")
        if index != 0:
            raise IndexError(f"图片只有一页，索引 {index} 无效")

        # 缩放到目标宽度
        img = self._img
        scale = preview_width / img.width
        new_h = int(img.height * scale)
        resample = getattr(Image, "LANCZOS", None) or getattr(Image, "ANTIALIAS")
        return img.resize((preview_width, new_h), resample)

    def get_page_size(self, index: int) -> Tuple[float, float]:
        if self._img is None:
            raise RuntimeError("图片未加载")
        return (float(self._img.width), float(self._img.height))

    def export_with_stamp(
        self,
        output_path: str,
        stamp_img: Image.Image,
        position_ratio: Tuple[float, float],
        stamp_size_ratio: float,
        selected_pages: Set[int]
    ) -> None:
        if self._img is None or self._path is None:
            raise RuntimeError("图片未加载")

        x_ratio, y_ratio = position_ratio
        img_w, img_h = self._img.size

        # 创建新的 PDF，以图片尺寸为页面尺寸
        out_doc = fitz.open()
        page = out_doc.new_page(width=img_w, height=img_h)
        img_rect = fitz.Rect(0, 0, img_w, img_h)

        # 插入原图
        page.insert_image(img_rect, filename=self._path)

        # 如果选中了第 0 页（唯一的一页），添加印章
        if 0 in selected_pages:
            scaled = scale_stamp(stamp_img, img_w, stamp_size_ratio)
            sw, sh = scaled.size
            x = x_ratio * img_w
            y = y_ratio * img_h
            stamp_rect = fitz.Rect(x, y, x + sw, y + sh)
            page.insert_image(stamp_rect, stream=to_png_bytes(scaled), overlay=True)

        out_doc.save(output_path)
        out_doc.close()

    def default_output_extension(self) -> str:
        # 图片导出为 PDF
        return '.pdf'

    def close(self) -> None:
        if self._img is not None:
            self._img.close()
            self._img = None
        self._path = None
