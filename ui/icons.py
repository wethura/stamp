"""统一线性图标集 — 程序化绘制，替代平台 emoji。

emoji 图标（📂🖨⚙）在各平台渲染成彩色表情，与「墨韵」浅色主题打架；
这里用 Pillow 在 24 单位视窗内以 2 单位线宽绘制，4x 超采样后交给
CTkImage 按 DPI 缩放，任意倍率下都保持同一种「细线圆角」的语言。

用法：get_icon("printer", 18, Colors.TEXT_SECONDARY)
"""

import math
from functools import lru_cache

import customtkinter as ctk
from PIL import Image, ImageDraw

from ui.theme import Colors

_VIEWBOX = 24.0
_RENDER_SCALE = 4      # 超采样倍数：96px 画布，交给 CTkImage 再缩到目标尺寸
_STROKE = 2.0          # 基准线宽（视图单位）


# ── 绘制原语 ──────────────────────────────────────────────────────────


def _line(d, pts, u, color, w, joint="curve"):
    d.line([(x * u, y * u) for x, y in pts], fill=color,
           width=max(1, round(w)), joint=joint)


def _rect(d, box, r, u, color, w):
    d.rounded_rectangle([c * u for c in box], radius=r * u, outline=color,
                        width=max(1, round(w)))


def _circle(d, cx, cy, r, u, color, w):
    d.ellipse([(cx - r) * u, (cy - r) * u, (cx + r) * u, (cy + r) * u],
              outline=color, width=max(1, round(w)))


def _dot(d, cx, cy, r, u, color):
    d.ellipse([(cx - r) * u, (cy - r) * u, (cx + r) * u, (cy + r) * u],
              fill=color)


def _arc_arrow(d, u, color, w, ccw):
    """旋转/刷新图标共用的「圆弧 + 箭头」；ccw 决定箭头切向。"""
    cx = cy = 12.0
    r = 8.2
    d.arc([(cx - r) * u, (cy - r) * u, (cx + r) * u, (cy + r) * u],
          start=300, end=590, fill=color, width=max(1, round(w)))
    theta = math.radians(230)
    px, py = cx + r * math.cos(theta), cy + r * math.sin(theta)
    if ccw:
        tx, ty = math.sin(theta), -math.cos(theta)
    else:
        tx, ty = -math.sin(theta), math.cos(theta)
    nx, ny = math.cos(theta), math.sin(theta)
    tip = (px + 3.4 * tx, py + 3.4 * ty)
    b1 = (px + 2.3 * nx, py + 2.3 * ny)
    b2 = (px - 2.3 * nx, py - 2.3 * ny)
    d.polygon([(tip[0] * u, tip[1] * u),
               (b1[0] * u, b1[1] * u),
               (b2[0] * u, b2[1] * u)], fill=color)


# ── 图标绘制函数（坐标系：24x24 视窗） ────────────────────────────────


def _draw_folder(d, u, c, w):
    _line(d, [(3.2, 19.4), (3.2, 7.4), (8.8, 7.4), (10.8, 5.2),
              (16.2, 5.2), (18.2, 7.4), (20.8, 7.4), (20.8, 19.4),
              (3.2, 19.4)], u, c, w)


def _draw_printer(d, u, c, w):
    _line(d, [(6.8, 8.8), (6.8, 3.6), (17.2, 3.6), (17.2, 8.8)], u, c, w)
    _rect(d, (3.2, 8.8, 20.8, 16.2), 2.2, u, c, w)
    _rect(d, (7.0, 14.2, 17.0, 20.6), 1.4, u, c, w)


def _draw_gear(d, u, c, w):
    cx = cy = 12.0
    _circle(d, cx, cy, 3.1, u, c, w)
    _circle(d, cx, cy, 6.5, u, c, w * 0.9)
    for k in range(8):
        a = math.radians(k * 45)
        _line(d, [(cx + 6.3 * math.cos(a), cy + 6.3 * math.sin(a)),
                  (cx + 9.4 * math.cos(a), cy + 9.4 * math.sin(a))],
              u, c, w * 1.15)


def _draw_plus(d, u, c, w):
    half = 1.15
    d.rounded_rectangle([(12 - half) * u, 5.6 * u, (12 + half) * u, 18.4 * u],
                        radius=half * u, fill=c)
    d.rounded_rectangle([5.6 * u, (12 - half) * u, 18.4 * u, (12 + half) * u],
                        radius=half * u, fill=c)


def _draw_grid(d, u, c, w):
    for x0, y0 in ((3.6, 3.6), (13.4, 3.6), (3.6, 13.4), (13.4, 13.4)):
        _rect(d, (x0, y0, x0 + 7.0, y0 + 7.0), 1.8, u, c, w * 0.9)


def _draw_stamp(d, u, c, w):
    _rect(d, (4.6, 3.4, 16.0, 20.6), 2.0, u, c, w)
    _line(d, [(7.6, 7.8), (13.0, 7.8)], u, c, w * 0.8)
    _line(d, [(7.6, 11.0), (13.0, 11.0)], u, c, w * 0.8)
    _dot(d, 16.4, 16.6, 4.3, u, c)


def _draw_seal(d, u, c, w):
    _circle(d, 12, 12, 8.4, u, c, w)
    _circle(d, 12, 12, 5.0, u, c, w * 0.7)


def _draw_rotate_ccw(d, u, c, w):
    _arc_arrow(d, u, c, w, ccw=True)


def _draw_rotate_cw(d, u, c, w):
    _arc_arrow(d, u, c, w, ccw=False)


def _draw_refresh(d, u, c, w):
    cx = cy = 12.0
    r = 8.2
    d.arc([(cx - r) * u, (cy - r) * u, (cx + r) * u, (cy + r) * u],
          start=300, end=590, fill=c, width=max(1, round(w)))
    for deg in (300, 230):
        theta = math.radians(deg)
        px, py = cx + r * math.cos(theta), cy + r * math.sin(theta)
        tx, ty = -math.sin(theta), math.cos(theta)
        nx, ny = math.cos(theta), math.sin(theta)
        tip = (px + 3.4 * tx, py + 3.4 * ty)
        b1 = (px + 2.3 * nx, py + 2.3 * ny)
        b2 = (px - 2.3 * nx, py - 2.3 * ny)
        d.polygon([(tip[0] * u, tip[1] * u),
                   (b1[0] * u, b1[1] * u),
                   (b2[0] * u, b2[1] * u)], fill=c)


def _chevron(left):
    def draw(d, u, c, w):
        x_a, x_b = (14.6, 9.4) if left else (9.4, 14.6)
        _line(d, [(x_a, 6.0), (x_b, 12.0), (x_a, 18.0)], u, c, w * 1.15)
    return draw


def _draw_trash(d, u, c, w):
    _line(d, [(5.4, 6.4), (18.6, 6.4)], u, c, w)
    _line(d, [(9.4, 6.4), (9.4, 4.2), (14.6, 4.2), (14.6, 6.4)], u, c, w)
    _rect(d, (6.8, 6.4, 17.2, 20.4), 1.8, u, c, w)
    _line(d, [(10.3, 10.2), (10.3, 16.6)], u, c, w * 0.8)
    _line(d, [(13.7, 10.2), (13.7, 16.6)], u, c, w * 0.8)


def _draw_check_circle(d, u, c, w):
    _circle(d, 12, 12, 8.6, u, c, w)
    _line(d, [(7.6, 12.4), (10.5, 15.3), (16.4, 9.4)], u, c, w * 1.1)


def _draw_alert_circle(d, u, c, w):
    _circle(d, 12, 12, 8.6, u, c, w)
    _line(d, [(12, 7.6), (12, 13.0)], u, c, w)
    _dot(d, 12, 16.3, 1.05, u, c)


def _draw_info_circle(d, u, c, w):
    _circle(d, 12, 12, 8.6, u, c, w)
    _dot(d, 12, 8.1, 1.05, u, c)
    _line(d, [(12, 11.2), (12, 16.5)], u, c, w)


def _draw_image(d, u, c, w):
    _rect(d, (3.6, 5.0, 20.4, 19.4), 2.0, u, c, w)
    _dot(d, 8.6, 9.8, 1.5, u, c)
    _line(d, [(6.4, 16.8), (10.6, 12.6), (13.4, 15.4),
              (16.0, 12.8), (18.2, 15.0)], u, c, w * 0.8)


def _draw_x(d, u, c, w):
    _line(d, [(9.4, 9.4), (14.6, 14.6)], u, c, w * 0.9)
    _line(d, [(14.6, 9.4), (9.4, 14.6)], u, c, w * 0.9)


_DRAWERS = {
    "folder": _draw_folder,
    "printer": _draw_printer,
    "gear": _draw_gear,
    "plus": _draw_plus,
    "grid": _draw_grid,
    "stamp": _draw_stamp,
    "seal": _draw_seal,
    "rotate-ccw": _draw_rotate_ccw,
    "rotate-cw": _draw_rotate_cw,
    "refresh": _draw_refresh,
    "chevron-left": _chevron(True),
    "chevron-right": _chevron(False),
    "trash": _draw_trash,
    "check-circle": _draw_check_circle,
    "alert-circle": _draw_alert_circle,
    "info-circle": _draw_info_circle,
    "image": _draw_image,
    "x": _draw_x,
}

AVAILABLE = tuple(sorted(_DRAWERS))


# ── 对外接口 ──────────────────────────────────────────────────────────


@lru_cache(maxsize=128)
def _render(name: str, color: str) -> Image.Image:
    size = int(_VIEWBOX * _RENDER_SCALE)
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    _DRAWERS[name](draw, _RENDER_SCALE, color, _STROKE * _RENDER_SCALE)
    return img


def get_icon(name: str, px: int = 20, color: str = None) -> ctk.CTkImage:
    """按名称取图标。

    注意：每次返回新建的 CTkImage —— 它内部的 PhotoImage 绑定创建时
    所在的 Tk 解释器，跨根窗口复用同一实例会拿到已销毁的 pyimage
    （测试里根窗口反复建销，实测必炸）。PIL 绘制结果经 _render 缓存，
    重复取图的开销只剩一次 PhotoImage 缩放。
    """
    if name not in _DRAWERS:
        raise KeyError(f"未知图标: {name}（可选: {', '.join(AVAILABLE)}）")
    color = color or Colors.TEXT_SECONDARY
    pil = _render(name, color)
    return ctk.CTkImage(light_image=pil, dark_image=pil, size=(px, px))
