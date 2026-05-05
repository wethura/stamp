import tkinter as tk
from PIL import Image, ImageTk
from typing import List, Optional, Dict

from processing.stamp import apply_opacity, apply_rotation
from processing.stamp_instance import StampInstance


def build_instance_display_data(
    instances: List[StampInstance],
    template_images: Dict[str, Image.Image],
    disp_w: int,
    disp_h: int
) -> List[tuple]:
    """Build display data (width, height, x, y) for each instance, with rotation/opactiy applied.

    Returns list of (stamp_display_w, stamp_display_h, pos_x_px, pos_y_px, processed_img).
    """
    result = []
    for inst in instances:
        img = template_images.get(inst.template_id)
        if img is None:
            continue

        img = img.copy()

        # Apply opacity
        if inst.opacity < 1.0:
            img = apply_opacity(img, inst.opacity)

        # Apply rotation
        if inst.rotation != 0:
            img = apply_rotation(img, inst.rotation)

        # Scale to display size
        stamp_w = max(1, int(disp_w * inst.size_ratio))
        stamp_h = max(1, int(img.height * stamp_w / img.width))
        img = img.resize((stamp_w, stamp_h), Image.LANCZOS)

        # After rotation, the bounding box may have expanded
        x = int(inst.pos_x * disp_w)
        y = int(inst.pos_y * disp_h)

        result.append((stamp_w, stamp_h, x, y, img))

    return result


class PreviewCanvas(tk.Frame):
    def __init__(self, parent,
                 on_stamp_position_changed=None,
                 on_delete_instance=None,
                 on_instance_selected=None,
                 **kwargs):
        super().__init__(parent, **kwargs)
        self.on_stamp_position_changed = on_stamp_position_changed
        self.on_delete_instance = on_delete_instance
        self.on_instance_selected = on_instance_selected

        self.canvas = tk.Canvas(self, bg="#2b2b2b", cursor="crosshair")
        self.canvas.pack(fill=tk.BOTH, expand=True)

        self._photo = None
        self._preview_size = (800, 600)
        self._offset = (0, 0)

        self._last_page_img = None
        self._last_instances: List[StampInstance] = []
        self._template_images: Dict[str, Image.Image] = {}
        self._display_data: List[tuple] = []

        self._selected_instance_id: Optional[str] = None
        self._drag_start = None
        self._dragging_instance_id: Optional[str] = None
        self._drag_start_pos = (0, 0)

        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.canvas.bind("<Configure>", self._on_resize)

        # Backspace delete
        self.canvas.bind("<BackSpace>", self._on_backspace)
        self.canvas.bind("<Delete>", self._on_backspace)

        # Right-click context menu
        self.canvas.bind("<Button-2>", self._on_right_click)
        self.canvas.bind("<Button-3>", self._on_right_click)

        self._context_menu = tk.Menu(self, tearoff=0)
        self._context_menu.add_command(label="删除", command=self._delete_selected)

        # For focus
        self.canvas.bind("<Enter>", lambda e: self.canvas.focus_set())

    def update_preview(self, page_img: Image.Image, instances: List[StampInstance],
                       template_images: Dict[str, Image.Image]):
        if page_img is None:
            return
        self._last_page_img = page_img
        self._last_instances = instances if instances else []
        self._template_images = template_images if template_images else {}
        self._render()

    def _render(self):
        page_img = self._last_page_img
        if page_img is None:
            return

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

        # Build display data for all instances
        self._display_data = []
        for inst in self._last_instances:
            img = self._template_images.get(inst.template_id)
            if img is None:
                self._display_data.append(None)
                continue

            img = img.copy()

            if inst.opacity < 1.0:
                img = apply_opacity(img, inst.opacity)
            if inst.rotation != 0:
                img = apply_rotation(img, inst.rotation)

            stamp_w = max(1, int(disp_w * inst.size_ratio))
            stamp_h = max(1, int(img.height * stamp_w / img.width))
            img = img.resize((stamp_w, stamp_h), Image.LANCZOS)

            x = int(inst.pos_x * disp_w)
            y = int(inst.pos_y * disp_h)
            x = min(max(0, x), disp_w - stamp_w)
            y = min(max(0, y), disp_h - stamp_h)

            page_disp.paste(img, (x, y), mask=img)
            self._display_data.append((stamp_w, stamp_h, x, y, inst.instance_id))

        offset_x = (canvas_w - disp_w) // 2
        offset_y = (canvas_h - disp_h) // 2
        self._offset = (offset_x, offset_y)

        self._photo = ImageTk.PhotoImage(page_disp.convert("RGB"))
        self.canvas.delete("all")
        self.canvas.create_image(offset_x, offset_y, anchor=tk.NW, image=self._photo)

        # Draw selection border for selected instance
        if self._selected_instance_id:
            self._draw_selection_border()

    def _draw_selection_border(self):
        for data in self._display_data:
            if data is None:
                continue
            sw, sh, x, y, inst_id = data
            if inst_id == self._selected_instance_id:
                ox, oy = self._offset
                self.canvas.create_rectangle(
                    ox + x - 2, oy + y - 2,
                    ox + x + sw + 2, oy + y + sh + 2,
                    outline="#00aaff", width=2
                )
                break

    def _on_resize(self, event):
        self._render()

    def _canvas_to_ratio(self, cx: int, cy: int) -> tuple:
        ox, oy = self._offset
        dw, dh = self._preview_size
        px = cx - ox
        py = cy - oy
        ratio_x = px / dw if dw > 0 else 0
        ratio_y = py / dh if dh > 0 else 0
        return (ratio_x, ratio_y)

    def _find_instance_at(self, ratio_x: float, ratio_y: float) -> Optional[str]:
        dw, dh = self._preview_size
        for data in self._display_data:
            if data is None:
                continue
            sw, sh, px, py, inst_id = data

            x1 = px / dw
            y1 = py / dh
            x2 = x1 + (sw / dw)
            y2 = y1 + (sh / dh)

            if x1 <= ratio_x <= x2 and y1 <= ratio_y <= y2:
                return inst_id
        return None

    def _on_press(self, event):
        if not self._last_instances:
            return

        ratio_x, ratio_y = self._canvas_to_ratio(event.x, event.y)
        inst_id = self._find_instance_at(ratio_x, ratio_y)

        if inst_id:
            self._selected_instance_id = inst_id
            if self.on_instance_selected:
                self.on_instance_selected(inst_id)

            self._dragging_instance_id = inst_id
            self._drag_start = (ratio_x, ratio_y)
            for inst in self._last_instances:
                if inst.instance_id == inst_id:
                    self._drag_start_pos = (inst.pos_x, inst.pos_y)
                    break
            self.canvas.config(cursor="fleur")
            self._render()
        else:
            self._selected_instance_id = None
            if self.on_instance_selected:
                self.on_instance_selected(None)
            self._render()

    def _on_drag(self, event):
        if self._drag_start is None or self._dragging_instance_id is None:
            return

        ratio_x, ratio_y = self._canvas_to_ratio(event.x, event.y)
        dx = ratio_x - self._drag_start[0]
        dy = ratio_y - self._drag_start[1]

        new_x = max(0, min(1, self._drag_start_pos[0] + dx))
        new_y = max(0, min(1, self._drag_start_pos[1] + dy))

        if self.on_stamp_position_changed:
            self.on_stamp_position_changed(self._dragging_instance_id, new_x, new_y)

    def _on_release(self, event):
        self._drag_start = None
        self._dragging_instance_id = None
        self.canvas.config(cursor="crosshair")

    def _on_backspace(self, event):
        self._delete_selected()

    def _on_right_click(self, event):
        ratio_x, ratio_y = self._canvas_to_ratio(event.x, event.y)
        inst_id = self._find_instance_at(ratio_x, ratio_y)
        if inst_id:
            self._selected_instance_id = inst_id
            self._render()
            self._context_menu.tk_popup(event.x_root, event.y_root)

    def _delete_selected(self):
        if self._selected_instance_id and self.on_delete_instance:
            self.on_delete_instance(self._selected_instance_id)
