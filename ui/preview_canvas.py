import tkinter as tk
from PIL import Image, ImageTk


class PreviewCanvas(tk.Frame):
    def __init__(self, parent, on_position_change=None, **kwargs):
        super().__init__(parent, **kwargs)
        self.on_position_change = on_position_change

        self.canvas = tk.Canvas(self, bg="#2b2b2b", cursor="crosshair")
        self.canvas.pack(fill=tk.BOTH, expand=True)

        self._photo = None
        self._drag_start = None
        self._preview_size = (800, 600)
        self._offset = (0, 0)

        # Cache last render params for resize redraw
        self._last_page_img = None
        self._last_stamp_img = None
        self._last_pos_ratio = (0.7, 0.7)
        self._last_size_ratio = 0.2

        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.canvas.bind("<Configure>", self._on_resize)

    def update_preview(self, page_img: Image.Image, stamp_img: Image.Image,
                       pos_ratio: tuple, size_ratio: float):
        """Composite stamp onto page and display."""
        if page_img is None:
            return
        self._last_page_img = page_img
        self._last_stamp_img = stamp_img
        self._last_pos_ratio = pos_ratio
        self._last_size_ratio = size_ratio
        self._render()

    def _render(self):
        page_img = self._last_page_img
        if page_img is None:
            return

        stamp_img = self._last_stamp_img
        pos_ratio = self._last_pos_ratio
        size_ratio = self._last_size_ratio

        canvas_w = self.canvas.winfo_width()
        canvas_h = self.canvas.winfo_height()
        if canvas_w < 2 or canvas_h < 2:
            return

        pw, ph = page_img.size
        scale = min(canvas_w / pw, canvas_h / ph)
        disp_w = max(1, int(pw * scale))
        disp_h = max(1, int(ph * scale))
        self._preview_size = (disp_w, disp_h)

        page_disp = page_img.resize((disp_w, disp_h), Image.LANCZOS).convert("RGBA")

        if stamp_img is not None:
            stamp_w = max(1, int(disp_w * size_ratio))
            stamp_h = max(1, int(stamp_img.height * stamp_w / stamp_img.width))
            stamp_disp = stamp_img.resize((stamp_w, stamp_h), Image.LANCZOS)
            x = int(pos_ratio[0] * disp_w)
            y = int(pos_ratio[1] * disp_h)
            page_disp.paste(stamp_disp, (x, y), mask=stamp_disp)

        offset_x = (canvas_w - disp_w) // 2
        offset_y = (canvas_h - disp_h) // 2
        self._offset = (offset_x, offset_y)

        self._photo = ImageTk.PhotoImage(page_disp.convert("RGB"))
        self.canvas.delete("all")
        self.canvas.create_image(offset_x, offset_y, anchor=tk.NW, image=self._photo)

    def _on_resize(self, event):
        self._render()

    def _canvas_to_ratio(self, cx, cy):
        ox, oy = self._offset
        dw, dh = self._preview_size
        return (cx - ox) / dw, (cy - oy) / dh

    def _on_press(self, event):
        self._drag_start = (event.x, event.y)

    def _on_drag(self, event):
        if self._drag_start and self.on_position_change:
            x, y = self._canvas_to_ratio(event.x, event.y)
            self.on_position_change(x, y)

    def _on_release(self, event):
        self._drag_start = None
