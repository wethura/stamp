import fitz
from PIL import Image
import io


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".tif", ".webp"}


def is_image_input(path: str) -> bool:
    import os
    ext = os.path.splitext(path)[1].lower()
    return ext in IMAGE_EXTENSIONS


def load_document(path: str):
    """Load PDF or image. Returns (fitz.Document | None, list[PIL.Image])."""
    if is_image_input(path):
        try:
            img = Image.open(path).convert("RGB")
            return None, [img]
        except Exception as e:
            raise RuntimeError(f"无法加载图片: {e}")
    else:
        try:
            doc = fitz.open(path)
            if doc.is_encrypted:
                raise RuntimeError("该 PDF 已加密，无法打开")
            pages = [render_page(doc, i) for i in range(len(doc))]
            return doc, pages
        except fitz.FileDataError as e:
            raise RuntimeError(f"PDF 文件损坏或无效: {e}")
        except RuntimeError:
            raise
        except Exception as e:
            raise RuntimeError(f"无法加载文档: {e}")


def render_page(doc: fitz.Document, page_index: int, width: int = 800) -> Image.Image:
    """Render a PDF page to PIL Image at given width."""
    page = doc[page_index]
    scale = width / page.rect.width
    mat = fitz.Matrix(scale, scale)
    pix = page.get_pixmap(matrix=mat, alpha=False)
    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
    return img
