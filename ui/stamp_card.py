"""Individual stamp template card widget with 墨韵 theme."""

import tkinter as tk

import customtkinter as ctk
from PIL import ImageTk

from ui.theme import Colors, Fonts, Spacing


class StampCard(ctk.CTkFrame):
    """A single stamp template card with thumbnail, name, and drag support."""

    def __init__(self, stamp, parent=None,
                 on_double_click=None,
                 on_drag_start=None):
        super().__init__(parent, width=108, height=132, corner_radius=10,
                         fg_color=Colors.SURFACE_RAISED,
                         border_width=1, border_color=Colors.SURFACE_OVERLAY)
        self.grid_propagate(False)
        self.pack_propagate(False)

        self._stamp = stamp
        self._stamp_id = stamp.id
        self._on_double_click = on_double_click
        self._on_drag_start = on_drag_start
        self._drag_start_pos = None

        self._build_ui()

        # Hover effect
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)

    def _build_ui(self):
        # Thumbnail — use tk.Label with PhotoImage (reliable across platforms)
        img = self._stamp.get_image().copy()
        img.thumbnail((90, 90))
        self._thumb_pil = img
        self._thumb_photo = ImageTk.PhotoImage(img)

        self._thumb_label = tk.Label(self, image=self._thumb_photo, bg=Colors.SURFACE_RAISED,
                                     width=90, height=90, padx=0, pady=0,
                                     cursor="hand2", borderwidth=0)
        self._thumb_label.pack(pady=(Spacing.PAD_SM, Spacing.PAD_XS))

        # Name
        name = self._stamp.name
        display_name = name if len(name) <= 8 else name[:7] + "…"
        name_label = ctk.CTkLabel(
            self, text=display_name,
            font=(Fonts.FAMILY, Fonts.SMALL_SIZE),
            text_color=Colors.TEXT_PRIMARY,
            height=20,
        )
        name_label.pack(pady=(0, Spacing.PAD_SM))

        # Bind interactions to all child widgets
        for widget in (self, self._thumb_label, name_label):
            widget.bind("<Double-Button-1>", self._on_double_click_event)
            widget.bind("<ButtonPress-1>", self._on_press)
            widget.bind("<B1-Motion>", self._on_motion)
            widget.bind("<ButtonRelease-1>", self._on_release)

    @property
    def stamp_id(self) -> str:
        return self._stamp_id

    def _on_enter(self, event):
        self.configure(fg_color=Colors.SURFACE_OVERLAY, border_color=Colors.SURFACE_HOVER)
        self._thumb_label.configure(bg=Colors.SURFACE_OVERLAY)

    def _on_leave(self, event):
        self.configure(fg_color=Colors.SURFACE_RAISED, border_color=Colors.SURFACE_OVERLAY)
        self._thumb_label.configure(bg=Colors.SURFACE_RAISED)

    def _on_double_click_event(self, event):
        if self._on_double_click:
            self._on_double_click(self._stamp_id)

    def _on_press(self, event):
        self._drag_start_pos = (event.x_root, event.y_root)

    def _on_motion(self, event):
        if self._drag_start_pos is None:
            return
        dx = event.x_root - self._drag_start_pos[0]
        dy = event.y_root - self._drag_start_pos[1]
        if abs(dx) + abs(dy) < 10:
            return

        # Start floating drag
        if self._on_drag_start:
            self._on_drag_start(event, self._stamp_id, self._thumb_pil)
        self._drag_start_pos = None

    def _on_release(self, event):
        self._drag_start_pos = None
