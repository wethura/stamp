from PIL import Image
import io


def load_stamp(path: str) -> Image.Image:
    """Load stamp image as RGBA. Auto-detects white background and removes it."""
    img = Image.open(path).convert("RGBA")
    if _has_white_background(img):
        img = remove_white_background(img)
    return img


def _has_white_background(img: Image.Image) -> bool:
    """Check if any corner pixel is near-white (background detection)."""
    pixels = img.load()
    w, h = img.size
    for sx, sy in [(0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)]:
        r, g, b, a = pixels[sx, sy]
        if r > 225 and g > 225 and b > 225 and a == 255:
            return True
    return False


def remove_white_background(img: Image.Image) -> Image.Image:
    """Remove white/gray background using saturation + brightness thresholds."""
    import numpy as np
    arr = np.array(img.copy(), dtype=float)
    r, g, b, a = arr[:,:,0], arr[:,:,1], arr[:,:,2], arr[:,:,3]
    mx = np.maximum(np.maximum(r, g), b)
    mn = np.minimum(np.minimum(r, g), b)
    saturation = np.where(mx > 0, (mx - mn) / mx, 0)
    brightness = mx / 255.0
    mask = (saturation < 0.35) & (brightness > 0.65) & (a == 255)
    result = arr.astype(np.uint8)
    result[mask] = [255, 255, 255, 0]
    return Image.fromarray(result)


def scale_stamp(img: Image.Image, page_w: int, stamp_size_ratio: float) -> Image.Image:
    """Scale stamp so its width = page_w * stamp_size_ratio."""
    target_w = int(page_w * stamp_size_ratio)
    if target_w < 1:
        target_w = 1
    ratio = target_w / img.width
    target_h = max(1, int(img.height * ratio))
    resample = getattr(Image, "LANCZOS", None) or getattr(Image, "ANTIALIAS")
    return img.resize((target_w, target_h), resample)


def to_png_bytes(img: Image.Image) -> bytes:
    """Serialize PIL Image to PNG bytes."""
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
