"""
Centralized theme module for Stamp Tool (CustomTkinter).

Provides visual constants (colors, fonts, spacing) and theme initialization.
Uses CustomTkinter dark mode with 墨韵 (Ink & Seal) color palette.
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
    """Application color palette — seal-red + ink-black + gold accents."""

    # Seal red (印泥红) — primary accent
    PRIMARY = "#C14443"
    PRIMARY_DARK = "#9E2F2E"
    PRIMARY_LIGHT = "#E8A5A4"
    PRIMARY_PALE = "#F5F0E8"

    # Ink black (墨黑) — backgrounds
    BG_DARK = "#1A1A2E"
    BG_CARD = "#2A2D3E"

    # Text
    TEXT_ON_DARK = "#E8E4DE"
    TEXT_SECONDARY = "#8B8697"

    # Decorative
    GOLD = "#C9A96E"
    DANGER = "#ff6b6b"

    # Selection
    ACCENT_SELECTION = "#C14443"


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
    """Application typography presets."""

    FAMILY = _CJK_FONT
    HEADING_SIZE = 14
    BODY_SIZE = 11
    SMALL_SIZE = 9
    SPLASH_TITLE_SIZE = 32
    SPLASH_SUBTITLE_SIZE = 12
    SPLASH_LOADING_SIZE = 11


# ── Spacing ───────────────────────────────────────────────────────────


class Spacing:
    """Spacing / padding presets (pixels)."""

    PAD_XS = 2
    PAD_SM = 5
    PAD_MD = 10
    PAD_LG = 15
    PAD_XL = 20


# ── Layout Constants ──────────────────────────────────────────────────

PANEL_WIDTH = 280


# ── Theme Initialization ──────────────────────────────────────────────


def init_theme():
    """Initialize CustomTkinter dark mode. Call once before creating windows."""
    ctk.set_appearance_mode("dark")


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
