"""Image conversion utilities — PIL to tkinter/CustomTkinter image formats."""

from PIL import Image, ImageTk

import customtkinter as ctk


def pil_to_photoimage(pil_image: Image.Image) -> ImageTk.PhotoImage:
    """Convert PIL Image to ImageTk.PhotoImage for tkinter Canvas."""
    if pil_image.mode not in ("RGBA", "RGB"):
        pil_image = pil_image.convert("RGBA")
    return ImageTk.PhotoImage(pil_image)


def pil_to_ctk_image(pil_image: Image.Image, size: tuple) -> ctk.CTkImage:
    """Convert PIL Image to CTkImage for CTk widgets (buttons, labels)."""
    return ctk.CTkImage(light_image=pil_image, dark_image=pil_image, size=size)
