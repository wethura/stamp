"""
Centralized theme module for Stamp Tool (CustomTkinter).

Provides visual constants (colors, fonts, spacing) and theme initialization.
Design language: "Mo Yun" (墨韵 Ink & Seal) — inspired by Linear / Raycast
layered-surface dark-mode aesthetic with seal-red identity accent.
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
    """Application color palette — layered surfaces + seal-red accent + gold trim."""

    # ── Surface hierarchy (dark mode, 5 levels) ───────────────────────
    # Deepest background → lightest raised element.
    SURFACE_CANVAS = "#0D0F14"       # Level 0 — main canvas / deepest void
    SURFACE_BASE = "#141720"         # Level 1 — toolbar, sidebar, status bar
    SURFACE_RAISED = "#1C1F2E"       # Level 2 — cards, input fields
    SURFACE_OVERLAY = "#252838"      # Level 3 — dropdowns, hover on raised
    SURFACE_HOVER = "#2E3148"        # Level 4 — hover on overlay-level items

    # ── Seal red (印泥红) — primary accent, used sparingly ───────────
    PRIMARY = "#C14443"
    PRIMARY_HOVER = "#D45554"
    PRIMARY_DARK = "#9E2F2E"
    PRIMARY_LIGHT = "#E8A5A4"
    PRIMARY_PALE = "#F5F0E8"

    # ── Text ──────────────────────────────────────────────────────────
    TEXT_PRIMARY = "#F0EDE6"          # Main text — warm white
    TEXT_SECONDARY = "#8B8FA3"        # Labels, descriptions
    TEXT_TERTIARY = "#5C6070"         # Disabled, hints
    TEXT_ON_DARK = "#E8E4DE"          # Legacy alias → TEXT_PRIMARY

    # ── Decorative / semantic ─────────────────────────────────────────
    GOLD = "#C9A96E"                  # Section headings, accent trim
    BORDER_SUBTLE = "#1E2130"         # 1px dividers between sections
    DANGER = "#ff6b6b"                # Delete / destructive actions

    # ── Selection ────────────────────────────────────────────────────
    ACCENT_SELECTION = "#C14443"

    # ── Legacy aliases (backward compat, will migrate gradually) ─────
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
    HEADING_SIZE = 14
    BODY_SIZE = 12
    SMALL_SIZE = 10
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
