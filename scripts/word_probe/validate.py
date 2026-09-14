"""PDF 产物校验：可打开、页数、页面尺寸、文字层保留、首屏渲染件。"""

import fitz
from PIL import Image
from pathlib import Path
from typing import Optional


def validate_pdf(pdf_path: Path, expect_pages: Optional[int] = None,
                 must_contain: tuple = ()) -> dict:
    """校验转换产物，返回机器可读结果；抛出时由调用方归类为 invalid_pdf。"""
    info = {"page_count": 0, "page_sizes_pt": [], "missing_text": [],
            "text_layer_preserved": False, "render_png": None}

    doc = fitz.open(str(pdf_path))
    try:
        info["page_count"] = doc.page_count
        info["page_sizes_pt"] = [
            [round(page.rect.width, 2), round(page.rect.height, 2)]
            for page in doc
        ]

        full_text = ""
        for page in doc:
            full_text += page.get_text()
        info["text_layer_preserved"] = len(full_text.strip()) > 0
        for marker in must_contain:
            if marker not in full_text:
                info["missing_text"].append(marker)

        png_path = pdf_path.with_suffix(".first.png")
        pix = doc[0].get_pixmap(dpi=72)
        pix.save(str(png_path))
        # 确认渲染件可用
        Image.open(str(png_path)).verify()
        info["render_png"] = png_path.as_posix()
        info["ok"] = (
            doc.page_count > 0
            and (expect_pages is None or doc.page_count == expect_pages)
            and not info["missing_text"]
        )
        if expect_pages is not None and doc.page_count != expect_pages:
            info["detail"] = f"页数不符：期望 {expect_pages}，实际 {doc.page_count}"
    finally:
        doc.close()
    return info
