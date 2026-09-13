"""Document preview canvas — continuous scroll mode with multi-page display and stamp interaction."""

import sys
import tkinter as tk
from typing import List, Optional, Dict, Tuple

from PIL import Image, ImageTk

import customtkinter as ctk

from processing.stamp import apply_opacity, apply_rotation
from processing.stamp_instance import StampInstance
from ui.theme import Colors, Fonts

PAGE_GAP = 12


def build_instance_display_data(
    instances: List[StampInstance],
    template_images: Dict[str, Image.Image],
    disp_w: int,
    disp_h: int
) -> List[tuple]:
    """Build display data (width, height, x, y) for each instance, with rotation/opacity applied.

    Returns list of (stamp_display_w, stamp_display_h, pos_x_px, pos_y_px, processed_img).
    """
    result = []
    for inst in instances:
        img = template_images.get(inst.template_id)
        if img is None:
            continue

        img = img.copy()

        # Scale first (based on original dimensions), then rotate
        stamp_w = max(1, int(disp_w * inst.size_ratio))
        stamp_h = max(1, int(img.height * stamp_w / img.width))
        img = img.resize((stamp_w, stamp_h), Image.LANCZOS)

        if inst.opacity < 1.0:
            img = apply_opacity(img, inst.opacity)
        if inst.rotation != 0:
            img = apply_rotation(img, inst.rotation)

        x = int(inst.pos_x * disp_w)
        y = int(inst.pos_y * disp_h)

        result.append((stamp_w, stamp_h, x, y, img))

    return result


class PreviewCanvas(ctk.CTkFrame):
    """Document preview with continuous scroll and interactive stamp overlays."""

    def __init__(self, parent,
                 on_stamp_position_changed=None,
                 on_delete_instance=None,
                 on_instance_selected=None,
                 on_drag_end=None,
                 on_active_page_changed=None,
                 on_page_count_changed=None):
        super().__init__(parent, fg_color=Colors.SURFACE_CANVAS)

        self.on_stamp_position_changed = on_stamp_position_changed
        self.on_delete_instance = on_delete_instance
        self.on_instance_selected = on_instance_selected
        self.on_drag_end = on_drag_end
        self.on_active_page_changed = on_active_page_changed
        self.on_page_count_changed = on_page_count_changed

        # Scrollbar
        self._scrollbar = ctk.CTkScrollbar(
            self, orientation="vertical",
            fg_color=Colors.SURFACE_CANVAS,
            button_color=Colors.SURFACE_OVERLAY,
            button_hover_color=Colors.SURFACE_HOVER,
            width=14,
        )
        self._scrollbar.pack(side="right", fill="y")

        # Inner canvas. yscrollincrement=1 makes yview_scroll("units") move
        # by single pixels, so wheel scrolling is smooth instead of jumping
        # in 1/10-window chunks.
        self.canvas = tk.Canvas(
            self, bg=Colors.SURFACE_CANVAS, highlightthickness=0, cursor="crosshair",
            yscrollincrement=1,
            yscrollcommand=self._scrollbar.set,
        )
        self.canvas.pack(side="left", fill="both", expand=True)
        self._scrollbar.configure(command=self._on_scrollbar_move)

        # State
        self._pages: List[Image.Image] = []
        self._all_instances: Dict[int, List[StampInstance]] = {}
        self._template_images: Dict[str, Image.Image] = {}

        # Computed layout per page
        self._page_offsets: List[int] = []
        self._page_display_sizes: List[Tuple[int, int]] = []
        self._page_photos: List[Optional[ImageTk.PhotoImage]] = []
        self._page_display_data: Dict[int, List[tuple]] = {}

        self._selected_instance_id: Optional[str] = None
        self._drag_start: Optional[Tuple[float, float]] = None
        self._dragging_instance_id: Optional[str] = None
        self._drag_start_pos: Tuple[float, float] = (0.0, 0.0)
        self._drag_page_index: int = 0

        self._has_document = False
        self._active_page = 0

        # Canvas event bindings
        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.canvas.bind("<Configure>", self._on_resize)

        # Mouse wheel scrolling — bind on the frame and scrollbar too, so the
        # wheel works anywhere over the preview area, not just over the page.
        for widget in (self, self.canvas, self._scrollbar):
            widget.bind("<MouseWheel>", self._on_mousewheel)
        if sys.platform == "linux":
            for widget in (self, self.canvas, self._scrollbar):
                widget.bind("<Button-4>", lambda e: self._scroll_pixels(-48))
                widget.bind("<Button-5>", lambda e: self._scroll_pixels(48))

        # Keyboard: Delete removes selection; arrows nudge the selected stamp
        # (or scroll when nothing is selected); PgUp/PgDn/Home/End navigate pages.
        self.canvas.bind("<BackSpace>", self._on_backspace)
        self.canvas.bind("<Delete>", self._on_backspace)
        self.canvas.bind("<Up>", lambda e: self._on_arrow_key(0, -1))
        self.canvas.bind("<Down>", lambda e: self._on_arrow_key(0, 1))
        self.canvas.bind("<Left>", lambda e: self._on_arrow_key(-1, 0))
        self.canvas.bind("<Right>", lambda e: self._on_arrow_key(1, 0))
        self.canvas.bind("<Prior>", lambda e: self.scroll_to_page(self._active_page - 1))
        self.canvas.bind("<Next>", lambda e: self.scroll_to_page(self._active_page + 1))
        self.canvas.bind("<Home>", lambda e: self.scroll_to_page(0))
        self.canvas.bind("<End>", lambda e: self.scroll_to_page(self.page_count - 1))

        # Context menu
        self.canvas.bind("<Button-2>", self._on_right_click)
        self.canvas.bind("<Button-3>", self._on_right_click)

        self._context_menu = tk.Menu(self, tearoff=0)
        self._context_menu.add_command(label="删除", command=self._delete_selected)

        # Focus on hover for keyboard events
        self.canvas.bind("<Enter>", lambda e: self.canvas.focus_set())

        # File drop via tkinterdnd2
        self._setup_file_drop()

    # ── Public API ───────────────────────────────────────────────────

    def update_all_pages(self, pages: List[Image.Image],
                         all_instances: Dict[int, List[StampInstance]],
                         template_images: Dict[str, Image.Image]):
        """Refresh the preview with all pages and stamp instances."""
        if not pages:
            return
        self._has_document = True
        self._pages = pages
        self._all_instances = all_instances if all_instances else {}
        self._template_images = template_images if template_images else {}
        self._render()

    def get_active_page(self) -> int:
        """Return the current active page index based on scroll position."""
        return self._active_page

    @property
    def page_count(self) -> int:
        """Number of pages currently shown in the preview."""
        return len(self._pages)

    def scroll_to_page(self, page_index: int):
        """Scroll the view so the given page is at the top of the viewport."""
        if not self._page_offsets:
            return
        idx = max(0, min(len(self._page_offsets) - 1, int(page_index)))
        top_offset = self._page_offsets[idx]
        total = self._page_offsets[-1] + self._page_display_sizes[-1][1]
        if total <= 0:
            return
        self.canvas.yview_moveto(top_offset / total)
        self._update_active_page()

    def reset_view(self):
        """Return to the first page (used when a new document is loaded).

        Goes through _update_active_page so the change is announced to
        listeners (page indicator, controller).
        """
        if self._pages:
            self.canvas.yview_moveto(0)
        self._update_active_page()

    # ── Rendering ────────────────────────────────────────────────────

    def _render(self):
        if not self._pages:
            return

        canvas_w = self.canvas.winfo_width()
        canvas_h = self.canvas.winfo_height()
        if canvas_w < 2 or canvas_h < 2:
            return

        # Compute layout for all pages (fit-to-width)
        self._page_offsets = []
        self._page_display_sizes = []
        self._page_photos = []
        self._page_display_data = {}

        y_offset = 0
        for i, page_img in enumerate(self._pages):
            pw, ph = page_img.size
            scale = canvas_w / pw
            disp_w = canvas_w
            disp_h = max(1, int(ph * scale))

            self._page_offsets.append(y_offset)
            self._page_display_sizes.append((disp_w, disp_h))

            y_offset += disp_h + PAGE_GAP

        total_height = y_offset - PAGE_GAP if self._pages else 0

        # Render each page with stamps composited
        for i, page_img in enumerate(self._pages):
            disp_w, disp_h = self._page_display_sizes[i]
            page_disp = page_img.resize((disp_w, disp_h), Image.LANCZOS).convert("RGBA")

            instances = self._all_instances.get(i, [])
            page_display = []
            for inst in instances:
                img = self._template_images.get(inst.template_id)
                if img is None:
                    page_display.append(None)
                    continue

                img = img.copy()
                stamp_w = max(1, int(disp_w * inst.size_ratio))
                stamp_h = max(1, int(img.height * stamp_w / img.width))
                img = img.resize((stamp_w, stamp_h), Image.LANCZOS)

                if inst.opacity < 1.0:
                    img = apply_opacity(img, inst.opacity)
                if inst.rotation != 0:
                    img = apply_rotation(img, inst.rotation)

                x = int(inst.pos_x * disp_w)
                y = int(inst.pos_y * disp_h)
                x = min(max(0, x), disp_w - stamp_w)
                y = min(max(0, y), disp_h - stamp_h)

                page_disp.paste(img, (x, y), mask=img)
                page_display.append((stamp_w, stamp_h, x, y, inst.instance_id))

            self._page_display_data[i] = page_display
            photo = ImageTk.PhotoImage(page_disp.convert("RGB"))
            self._page_photos.append(photo)

        # Draw to canvas
        self.canvas.delete("all")
        for i, photo in enumerate(self._page_photos):
            if photo is None:
                continue
            self.canvas.create_image(0, self._page_offsets[i], anchor=tk.NW, image=photo)

        self.canvas.configure(scrollregion=(0, 0, canvas_w, total_height))

        # Draw selection border
        if self._selected_instance_id:
            self._draw_selection_border()

        # Notify active page
        self._update_active_page()

        # Notify page count so the page indicator can refresh
        if getattr(self, "_last_page_count", None) != len(self._pages):
            self._last_page_count = len(self._pages)
            if self.on_page_count_changed:
                self.on_page_count_changed(len(self._pages))

    def _render_placeholder(self):
        """Draw hint text when no document is loaded."""
        canvas_w = self.canvas.winfo_width()
        canvas_h = self.canvas.winfo_height()
        if canvas_w < 2 or canvas_h < 2:
            return

        self.canvas.delete("all")
        cx = canvas_w // 2
        cy = canvas_h // 2

        # A paper sheet and seal drawn with vectors stay crisp at any DPI.
        compact = canvas_h < 420
        top = cy - (105 if compact else 145)
        self.canvas.create_rectangle(
            cx - 38, top + 5, cx + 46, top + 109,
            fill=Colors.BORDER_SUBTLE, outline="",
        )
        self.canvas.create_rectangle(
            cx - 44, top, cx + 40, top + 104,
            fill=Colors.SURFACE_BASE, outline=Colors.BORDER_SUBTLE,
        )
        for line in range(3):
            self.canvas.create_line(
                cx - 26, top + 27 + line * 14, cx + 19, top + 27 + line * 14,
                fill=Colors.BORDER_SUBTLE, width=2,
            )
        self.canvas.create_oval(
            cx + 5, top + 66, cx + 51, top + 112,
            fill=Colors.SURFACE_BASE, outline=Colors.PRIMARY, width=2,
        )
        self.canvas.create_text(cx + 28, top + 89, text="印",
                                fill=Colors.PRIMARY, font=(Fonts.FAMILY, 20, "bold"))
        title_y = top + 146
        self.canvas.create_text(
            cx, title_y, text="为文档盖上一枚好印章",
            fill=Colors.TEXT_PRIMARY, font=(Fonts.FAMILY, 22, "bold"),
            width=max(180, canvas_w - 32), justify="center",
        )
        self.canvas.create_text(
            cx, title_y + 39, text="从打开一份文档开始，也可以将文件拖到这里",
            fill=Colors.TEXT_SECONDARY, font=(Fonts.FAMILY, Fonts.BODY_SIZE),
            width=max(180, canvas_w - 40), justify="center",
        )
        self.canvas.create_text(
            cx, title_y + 76, text="PDF   /   图片   /   Excel",
            fill=Colors.TEXT_SECONDARY, font=(Fonts.FAMILY, Fonts.SMALL_SIZE),
        )
        if not compact:
            self.canvas.create_line(cx - 140, title_y + 116, cx + 140, title_y + 116,
                                    fill=Colors.BORDER_SUBTLE)
            self.canvas.create_text(
                cx, title_y + 145, text="01  打开文档     02  添加印章     03  导出保存",
                fill=Colors.TEXT_SECONDARY, font=(Fonts.FAMILY, Fonts.SMALL_SIZE),
            )

    def _draw_selection_border(self):
        for page_idx, display_list in self._page_display_data.items():
            for data in display_list:
                if data is None:
                    continue
                sw, sh, x, y, inst_id = data
                if inst_id == self._selected_instance_id:
                    oy = self._page_offsets[page_idx]
                    self.canvas.create_rectangle(
                        x - 3, oy + y - 3,
                        x + sw + 3, oy + y + sh + 3,
                        outline=Colors.ACCENT_SELECTION, width=2,
                    )
                    return

    # ── Active Page Tracking ─────────────────────────────────────────

    def _update_active_page(self):
        """Determine the active page from the middle of the visible area."""
        if not self._page_offsets:
            return

        try:
            view = self.canvas.yview()
        except tk.TclError:
            return

        canvas_h = self.canvas.winfo_height()
        if canvas_h < 2:
            return

        # Get the scrollregion height
        scrollregion = self.canvas.cget("scrollregion")
        if scrollregion:
            total_height = float(scrollregion.split()[-1])
        else:
            return

        visible_top = view[0] * total_height
        visible_middle = visible_top + canvas_h / 2

        # Find which page the middle of the visible area falls on
        new_active = 0
        for i in range(len(self._page_offsets)):
            offset = self._page_offsets[i]
            _, disp_h = self._page_display_sizes[i]
            page_bottom = offset + disp_h
            if visible_middle >= offset and visible_middle < page_bottom:
                new_active = i
                break
            if i == len(self._page_offsets) - 1:
                new_active = i

        if new_active != self._active_page:
            self._active_page = new_active
            if self.on_active_page_changed:
                self.on_active_page_changed(new_active)

    # ── Coordinate Conversion ────────────────────────────────────────

    def _canvas_to_page_ratio(self, event_x: int, event_y: int) -> Tuple[int, float, float]:
        """Convert canvas event coordinates to (page_index, ratio_x, ratio_y).

        Returns (-1, 0, 0) if the click is not on any page.
        """
        canvas_x = self.canvas.canvasx(event_x)
        canvas_y = self.canvas.canvasy(event_y)

        for i in range(len(self._page_offsets)):
            offset = self._page_offsets[i]
            disp_w, disp_h = self._page_display_sizes[i]
            page_bottom = offset + disp_h

            if canvas_y >= offset and canvas_y < page_bottom:
                local_x = canvas_x
                local_y = canvas_y - offset
                ratio_x = local_x / disp_w if disp_w > 0 else 0
                ratio_y = local_y / disp_h if disp_h > 0 else 0
                return (i, ratio_x, ratio_y)

        return (-1, 0.0, 0.0)

    def _find_instance_at(self, page_index: int, ratio_x: float, ratio_y: float) -> Optional[str]:
        if page_index < 0:
            return None
        display_list = self._page_display_data.get(page_index, [])
        _, disp_h = self._page_display_sizes[page_index]
        disp_w, _ = self._page_display_sizes[page_index]

        for data in display_list:
            if data is None:
                continue
            sw, sh, px, py, inst_id = data

            x1 = px / disp_w
            y1 = py / disp_h
            x2 = x1 + (sw / disp_w)
            y2 = y1 + (sh / disp_h)

            if x1 <= ratio_x <= x2 and y1 <= ratio_y <= y2:
                return inst_id
        return None

    # ── Interaction ──────────────────────────────────────────────────

    def _on_press(self, event):
        self.canvas.focus_set()
        if not self._has_document:
            return

        page_idx, ratio_x, ratio_y = self._canvas_to_page_ratio(event.x, event.y)

        # Update active page on click
        if page_idx >= 0 and page_idx != self._active_page:
            self._active_page = page_idx
            if self.on_active_page_changed:
                self.on_active_page_changed(page_idx)

        instances = self._all_instances.get(page_idx, [])
        if not instances:
            self._selected_instance_id = None
            if self.on_instance_selected:
                self.on_instance_selected(None)
            return

        inst_id = self._find_instance_at(page_idx, ratio_x, ratio_y)

        if inst_id:
            self._selected_instance_id = inst_id
            if self.on_instance_selected:
                self.on_instance_selected(inst_id)

            self._dragging_instance_id = inst_id
            self._drag_page_index = page_idx
            self._drag_start = (ratio_x, ratio_y)
            for inst in instances:
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

        # Use the page where drag started for coordinate mapping
        page_idx = self._drag_page_index
        if page_idx < 0 or page_idx >= len(self._page_offsets):
            return

        # Convert using the drag-start page coordinates
        canvas_x = self.canvas.canvasx(event.x)
        canvas_y = self.canvas.canvasy(event.y)
        offset = self._page_offsets[page_idx]
        disp_w, disp_h = self._page_display_sizes[page_idx]

        local_y = canvas_y - offset
        ratio_x = canvas_x / disp_w if disp_w > 0 else 0
        ratio_y = local_y / disp_h if disp_h > 0 else 0

        dx = ratio_x - self._drag_start[0]
        dy = ratio_y - self._drag_start[1]

        new_x = max(0, min(1, self._drag_start_pos[0] + dx))
        new_y = max(0, min(1, self._drag_start_pos[1] + dy))

        if self.on_stamp_position_changed:
            self.on_stamp_position_changed(self._dragging_instance_id, new_x, new_y)

    def _on_release(self, event):
        was_dragging = self._dragging_instance_id is not None
        self._drag_start = None
        self._dragging_instance_id = None
        self.canvas.config(cursor="crosshair")
        if was_dragging and self.on_drag_end:
            self.on_drag_end()

    def _on_resize(self, event):
        if self._has_document:
            self._render()
        else:
            self._render_placeholder()

    def _on_mousewheel(self, event):
        self._scroll_pixels(self._wheel_pixels(event.delta))

    @staticmethod
    def _wheel_pixels(delta: float) -> int:
        """Convert a platform wheel delta into a pixel scroll amount.

        macOS trackpads emit many small deltas (1-10); Windows mice emit
        multiples of 120 per notch. Clamp to keep momentum bursts sane.
        """
        if sys.platform.startswith("win"):
            return max(-240, min(240, int(-delta * 0.6)))
        return max(-240, min(240, int(-delta * 4)))

    def _scroll_pixels(self, amount: int):
        if amount:
            self.canvas.yview_scroll(amount, "units")
        self._update_active_page()

    def _on_scrollbar_move(self, *args):
        self.canvas.yview(*args)
        self._update_active_page()

    # ── Keyboard ─────────────────────────────────────────────────────

    def _on_arrow_key(self, dx, dy):
        if self._has_document and self._nudge_selected(dx * 0.005, dy * 0.005):
            return "break"
        self._scroll_pixels(dy * 60)
        return "break"

    def _nudge_selected(self, dx, dy) -> bool:
        """Move the selected stamp by (dx, dy) in page ratios. True if handled."""
        if not self._selected_instance_id:
            return False
        for instances in self._all_instances.values():
            for inst in instances:
                if inst.instance_id == self._selected_instance_id:
                    new_x = min(1.0, max(0.0, inst.pos_x + dx))
                    new_y = min(1.0, max(0.0, inst.pos_y + dy))
                    if self.on_stamp_position_changed:
                        self.on_stamp_position_changed(inst.instance_id, new_x, new_y)
                    return True
        return False

    def _on_backspace(self, event):
        self._delete_selected()

    def _on_right_click(self, event):
        page_idx, ratio_x, ratio_y = self._canvas_to_page_ratio(event.x, event.y)
        inst_id = self._find_instance_at(page_idx, ratio_x, ratio_y)
        if inst_id:
            self._selected_instance_id = inst_id
            self._render()
            self._context_menu.tk_popup(event.x_root, event.y_root)

    def _delete_selected(self):
        if self._selected_instance_id and self.on_delete_instance:
            self.on_delete_instance(self._selected_instance_id)

    # ── File Drop ────────────────────────────────────────────────────

    def _setup_file_drop(self):
        """Register canvas for OS-level file drag-drop."""
        try:
            from tkinterdnd2 import DND_FILES
            self.canvas.drop_target_register(DND_FILES)
            self.canvas.dnd_bind("<<Drop>>", self._on_file_drop)
            return
        except (ImportError, tk.TclError):
            pass

        try:
            self.canvas.tk.call('tkdnd::drop_target', 'register', self.canvas._w, 'DND_Files')
            self.canvas.tk.call('bind', self.canvas._w, '<<Drop>>',
                                f'[list {self.canvas._w}._on_tkdnd_drop %D]')
            self.canvas._on_tkdnd_drop = lambda data: self._on_file_drop_raw(data)
        except tk.TclError:
            pass

    def _on_file_drop(self, event):
        """Handle OS file drop onto the canvas."""
        toplevel = self.winfo_toplevel()
        if hasattr(toplevel, 'controller') and hasattr(toplevel.controller, 'on_file_dropped'):
            toplevel.controller.on_file_dropped(event.data)

    def _on_file_drop_raw(self, data: str):
        """Handle OS file drop from raw Tcl tkdnd."""
        toplevel = self.winfo_toplevel()
        if hasattr(toplevel, 'controller') and hasattr(toplevel.controller, 'on_file_dropped'):
            toplevel.controller.on_file_dropped(data)
