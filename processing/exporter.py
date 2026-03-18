import fitz
from PIL import Image
from processing.stamp import scale_stamp, to_png_bytes
from processing.document import render_page, is_image_input


def export_pdf(
    src_path: str,
    is_image: bool,
    stamp_img: Image.Image,
    position_ratio: tuple,
    stamp_size_ratio: float,
    selected_pages: set,
    output_path: str,
):
    """Export document with stamp overlaid on selected pages."""
    x_ratio, y_ratio = position_ratio

    if is_image:
        # Create a new PDF with the image as the first page
        src_img = Image.open(src_path)
        img_w, img_h = src_img.size

        out_doc = fitz.open()
        page = out_doc.new_page(width=img_w, height=img_h)
        img_rect = fitz.Rect(0, 0, img_w, img_h)
        page.insert_image(img_rect, filename=src_path)

        # Stamp on page 0 (only page)
        scaled = scale_stamp(stamp_img, img_w, stamp_size_ratio)
        sw, sh = scaled.size
        x = x_ratio * img_w
        y = y_ratio * img_h
        stamp_rect = fitz.Rect(x, y, x + sw, y + sh)
        page.insert_image(stamp_rect, stream=to_png_bytes(scaled), overlay=True)

        out_doc.save(output_path)
        out_doc.close()
    else:
        src_doc = fitz.open(src_path)
        out_doc = fitz.open()
        out_doc.insert_pdf(src_doc)

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
        src_doc.close()
