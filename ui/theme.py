"""
Centralized theme module for Stamp Tool (CustomTkinter).

Provides visual constants (colors, fonts, spacing) and theme initialization.
Design language: "Mo Yun" (墨韵 Ink & Seal) — clean light theme with
seal-red identity accent, inspired by macOS native app aesthetics.
"""

import os
import sys

import customtkinter as ctk
from PIL import Image, ImageTk


# ── Platform detection ────────────────────────────────────────────────

_IS_MACOS = sys.platform == "darwin"
_IS_WINDOWS = os.name == "nt"


# ── Color Palette ─────────────────────────────────────────────────────


class Colors:
    """Application color palette — light surfaces + seal-red accent."""

    # ── Surface hierarchy (light mode, 5 levels) ────────────────────
    SURFACE_CANVAS = "#EEECE7"       # Level 0 — canvas / warm paper gray
    SURFACE_BASE = "#FFFEFB"         # Level 1 — toolbar, sidebar, status bar
    SURFACE_RAISED = "#F7F5F1"       # Level 2 — cards, input fields
    SURFACE_OVERLAY = "#EBE8E4"      # Level 3 — hover on cards, slider track
    SURFACE_HOVER = "#E0DDD8"        # Level 4 — active / pressed states

    # ── Seal red (印泥红) — primary accent ──────────────────────────
    PRIMARY = "#B63D32"
    PRIMARY_HOVER = "#982F26"
    PRIMARY_DARK = "#9E2F2E"
    PRIMARY_LIGHT = "#E8A5A4"
    PRIMARY_PALE = "#FFFFFF"

    # ── Text ──────────────────────────────────────────────────────────
    TEXT_PRIMARY = "#292925"          # Main text — near black
    TEXT_SECONDARY = "#716E67"        # Labels, descriptions
    TEXT_TERTIARY = "#969188"         # Disabled, hints
    TEXT_ON_DARK = "#292925"          # Alias → TEXT_PRIMARY

    # ── Decorative / semantic ─────────────────────────────────────────
    GOLD = "#A07850"                  # Section headings
    BORDER_SUBTLE = "#E0DDD8"         # 1px dividers between sections
    DANGER = "#E04040"                # Delete / destructive actions
    SUCCESS = "#3E8E5A"               # Success feedback (toast / states)
    ICON_DISABLED = "#C7C3BC"         # Disabled-state icons on buttons

    # ── Selection ────────────────────────────────────────────────────
    ACCENT_SELECTION = "#B63D32"

    # ── Legacy aliases ───────────────────────────────────────────────
    BG_DARK = SURFACE_CANVAS
    BG_CARD = SURFACE_RAISED


# ── Typography ────────────────────────────────────────────────────────


def _detect_cjk_font() -> str:
    """Return the best available CJK font family for the current platform."""
    if _IS_MACOS:
        return "PingFang SC"
    if _IS_WINDOWS:
        return "Microsoft YaHei"
    return "Noto Sans CJK SC"


_CJK_FONT = _detect_cjk_font()


class Fonts:
    """Application typography presets — 4px-aligned size scale."""

    FAMILY = _CJK_FONT
    HEADING_SIZE = 16
    BODY_SIZE = 13
    SMALL_SIZE = 12
    SPLASH_TITLE_SIZE = 32
    SPLASH_SUBTITLE_SIZE = 13
    SPLASH_LOADING_SIZE = 12


# ── Spacing ───────────────────────────────────────────────────────────


class Spacing:
    """Spacing / padding presets — 4px grid system."""

    PAD_XS = 4
    PAD_SM = 8
    PAD_MD = 12
    PAD_LG = 16
    PAD_XL = 24


# ── Layout Constants ──────────────────────────────────────────────────

PANEL_WIDTH = 304


class Buttons:
    """统一控件尺寸 — 全应用同一套高度/圆角，不再逐处手调。"""

    HEIGHT = 40            # 主窗工具栏/侧栏按钮
    HEIGHT_DIALOG = 38     # 对话框按钮
    HEIGHT_SM = 28         # 紧凑按钮（页导航、行内小操作）
    RADIUS = 8             # 按钮圆角
    RADIUS_SM = 6          # 输入框/紧凑按钮圆角
    ICON = 18              # 按钮内图标边长（逻辑像素）
    ICON_SM = 14           # 小按钮图标边长


# ── Theme Initialization ──────────────────────────────────────────────


def init_theme():
    """Initialize CustomTkinter light mode. Call once before creating windows."""
    ctk.set_appearance_mode("light")


def load_app_icon(window):
    """Load and set the application icon on the given window."""
    icon_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), "assets", "icon.png"
    )
    if not os.path.exists(icon_path):
        return None
    try:
        icon_img = Image.open(icon_path)
        icon_photo = ImageTk.PhotoImage(icon_img)
        window.iconphoto(True, icon_photo)
        return icon_photo
    except Exception:
        return None
