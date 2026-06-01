"""Right-side controls panel — stamp library, instance editing, page navigation."""

from tkinter import filedialog, messagebox, simpledialog
from typing import Optional

import customtkinter as ctk

from processing.stamp import load_stamp
from processing.stamp_manager import StampData
from processing.stamp_instance import StampInstanceManager
from ui.stamp_card import StampCard
from ui.theme import Colors, Fonts, Spacing, PANEL_WIDTH


class ControlsPanel(ctk.CTkScrollableFrame):
    """Right-side panel with stamp template library, instance editing sliders, and page navigation."""

    on_instance_property_changed = None

    def __init__(self, parent,
                 on_preview_page_changed=None,
                 on_create_instance=None):
        super().__init__(
            parent,
            width=PANEL_WIDTH,
            fg_color=Colors.BG_DARK,
            scrollbar_fg_color=Colors.BG_DARK,
            scrollbar_button_color=Colors.BG_CARD,
            scrollbar_button_hover_color="#3A3D4E",
        )

        self.on_preview_page_changed = on_preview_page_changed
        self.on_create_instance = on_create_instance

        self._page_count = 0
        self._current_preview = 0
        self._stamp_manager = None
        self._instance_manager: Optional[StampInstanceManager] = None
        self._editing_instance_id: Optional[str] = None

        self._build_ui()

    # ═══════════════════════════════════════════════════════════════════
    #  Public API
    # ═══════════════════════════════════════════════════════════════════

    def set_stamp_manager(self, manager):
        self._stamp_manager = manager
        self._refresh_stamp_list()

    def set_instance_manager(self, manager: StampInstanceManager):
        self._instance_manager = manager
        self._editing_instance_id = None
        self._update_edit_controls()

    def set_editing_instance(self, instance_id: Optional[str]):
        self._editing_instance_id = instance_id
        self._update_edit_controls()

    def set_pages(self, count: int):
        self._page_count = count
        self._current_preview = 0
        self._update_nav_label()

    # ═══════════════════════════════════════════════════════════════════
    #  UI Construction
    # ═══════════════════════════════════════════════════════════════════

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)

        row = 0

        # ── Template Library Section ─────────────────────────────────
        self._build_section_heading("章模板库", row)
        row += 1

        import_btn = ctk.CTkButton(
            self,
            text="＋ 导入新章",
            fg_color=Colors.PRIMARY,
            hover_color=Colors.PRIMARY_DARK,
            text_color=Colors.PRIMARY_PALE,
            font=(Fonts.FAMILY, Fonts.BODY_SIZE, "bold"),
            height=32,
            corner_radius=6,
            command=self._import_stamp,
        )
        import_btn.grid(row=row, column=0, padx=8, pady=(4, 6), sticky="ew")
        row += 1

        # Scrollable stamp card grid
        self._scroll_frame = ctk.CTkScrollableFrame(
            self, fg_color="transparent", height=220,
        )
        self._scroll_frame.grid(row=row, column=0, padx=6, pady=(4, 6), sticky="nsew")
        self._scroll_frame.grid_columnconfigure((0, 1), weight=1)
        row += 1

        # ── Instance Editing Section ─────────────────────────────────
        self._build_separator(row)
        row += 1

        self._build_section_heading("编辑章", row)
        row += 1

        self._editing_label = ctk.CTkLabel(
            self,
            text="双击模板添加印章到页面",
            font=(Fonts.FAMILY, Fonts.BODY_SIZE),
            text_color=Colors.TEXT_SECONDARY,
        )
        self._editing_label.grid(row=row, column=0, padx=8, pady=(2, 4), sticky="ew")
        row += 1

        # Sliders
        self._size_slider, self._size_label = self._add_slider_row(
            row, "大  小", 5, 80, "%", self._on_size_changed)
        row += 2

        self._opacity_slider, self._opacity_label = self._add_slider_row(
            row, "透明度", 0, 100, "%", self._on_opacity_changed)
        row += 2

        self._rotation_slider, self._rotation_label = self._add_slider_row(
            row, "旋  转", 0, 360, "°", self._on_rotation_changed)
        row += 2

        # ── Page Navigation ──────────────────────────────────────────
        self._build_separator(row)
        row += 1

        self._build_section_heading("预览页", row)
        row += 1

        nav_frame = ctk.CTkFrame(self, fg_color="transparent")
        nav_frame.grid(row=row, column=0, padx=8, pady=(4, 12), sticky="ew")
        nav_frame.grid_columnconfigure(1, weight=1)

        prev_btn = ctk.CTkButton(
            nav_frame, text="◀", width=36, height=30,
            fg_color=Colors.BG_CARD, hover_color="#33374A",
            text_color=Colors.TEXT_ON_DARK,
            font=("", 14), corner_radius=6,
            command=self._prev_page,
        )
        prev_btn.grid(row=0, column=0, padx=(0, 4))

        self._page_label = ctk.CTkLabel(
            nav_frame, text="- / -",
            font=(Fonts.FAMILY, Fonts.HEADING_SIZE),
            text_color=Colors.TEXT_ON_DARK,
        )
        self._page_label.grid(row=0, column=1, sticky="ew")

        next_btn = ctk.CTkButton(
            nav_frame, text="▶", width=36, height=30,
            fg_color=Colors.BG_CARD, hover_color="#33374A",
            text_color=Colors.TEXT_ON_DARK,
            font=("", 14), corner_radius=6,
            command=self._next_page,
        )
        next_btn.grid(row=0, column=2, padx=(4, 0))

    def _build_section_heading(self, text: str, row: int):
        """Create a compact section heading with gold left accent."""
        label = ctk.CTkLabel(
            self, text=text,
            font=(Fonts.FAMILY, Fonts.HEADING_SIZE, "bold"),
            text_color=Colors.GOLD,
        )
        label.grid(row=row, column=0, padx=(14, 8), pady=(6, 2), sticky="w")

    def _build_separator(self, row: int):
        """Create a thin gold separator line between sections."""
        sep = ctk.CTkFrame(self, height=1, fg_color=Colors.GOLD)
        sep.grid(row=row, column=0, padx=16, pady=(6, 2), sticky="ew")

    def _add_slider_row(self, row, label_text, from_val, to_val, unit, callback):
        """Create a labeled slider row. Returns (slider, value_label)."""
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=row, column=0, padx=8, sticky="ew")
        header.grid_columnconfigure(0, weight=1)

        name_label = ctk.CTkLabel(
            header, text=label_text,
            font=(Fonts.FAMILY, Fonts.SMALL_SIZE),
            text_color=Colors.TEXT_ON_DARK,
        )
        name_label.grid(row=0, column=0, sticky="w")

        val_label = ctk.CTkLabel(
            header, text=f"{from_val}{unit}",
            font=(Fonts.FAMILY, Fonts.SMALL_SIZE),
            text_color=Colors.TEXT_SECONDARY,
        )
        val_label.grid(row=0, column=1, sticky="e")

        slider = ctk.CTkSlider(
            self, from_=from_val, to=to_val,
            height=16, corner_radius=4,
            button_color=Colors.PRIMARY,
            button_hover_color=Colors.PRIMARY_DARK,
            progress_color=Colors.PRIMARY,
            fg_color=Colors.GOLD,
            number_of_steps=to_val - from_val,
            command=lambda v, u=unit, vl=val_label, cb=callback: cb(v, u, vl),
        )
        slider.set(from_val)
        slider.grid(row=row + 1, column=0, padx=12, pady=(2, 8), sticky="ew")

        return slider, val_label

    # ═══════════════════════════════════════════════════════════════════
    #  Stamp Library
    # ═══════════════════════════════════════════════════════════════════

    def _import_stamp(self):
        path = filedialog.askopenfilename(
            title="选择章图片",
            filetypes=[("图片文件", "*.jpg *.jpeg *.png *.bmp *.tiff *.tif *.webp")]
        )
        if not path:
            return

        try:
            img = load_stamp(path)
        except Exception as e:
            messagebox.showerror("加载失败", f"无法加载图片: {e}")
            return

        name = simpledialog.askstring("章名称", "请输入章的名称:", initialvalue="新章")
        if not name:
            name = "未命名章"

        if self._stamp_manager:
            self._stamp_manager.add_stamp(name, img)
            self._refresh_stamp_list()

    def _refresh_stamp_list(self):
        for child in self._scroll_frame.winfo_children():
            child.destroy()

        if not self._stamp_manager:
            return

        stamps = self._stamp_manager.list_stamps()
        for idx, stamp in enumerate(stamps):
            row_idx = idx // 2
            col_idx = idx % 2

            card = StampCard(
                stamp, self._scroll_frame,
                on_double_click=self._on_card_double_click,
                on_delete_requested=self._delete_stamp,
                on_drag_start=self._start_stamp_drag,
            )
            card.grid(row=row_idx, column=col_idx, padx=4, pady=4, sticky="nsew")

        self._update_edit_controls()

    def _on_card_double_click(self, stamp_id: str):
        if self.on_create_instance:
            self.on_create_instance(stamp_id)

    def _delete_stamp(self, stamp_id: str):
        if not self._stamp_manager:
            return

        stamp = self._stamp_manager.get_stamp(stamp_id)
        stamp_name = stamp.name if stamp else "该章"

        if not messagebox.askyesno("确认删除", f"确定要删除「{stamp_name}」吗？"):
            return

        self._stamp_manager.delete_stamp(stamp_id)
        if self._editing_instance_id and self._instance_manager:
            inst = self._instance_manager.get_instance(self._editing_instance_id)
            if inst and inst.template_id == stamp_id:
                self._editing_instance_id = None
        self._refresh_stamp_list()

    def _start_stamp_drag(self, event, template_id: str, thumb_img):
        """Start floating drag from stamp card."""
        import tkinter as tk

        self._drag_template_id = template_id
        self._drag_window = tk.Toplevel(self)
        self._drag_window.overrideredirect(True)
        self._drag_window.attributes("-alpha", 0.7)

        from PIL import ImageTk
        photo = ImageTk.PhotoImage(thumb_img)
        lbl = tk.Label(self._drag_window, image=photo)
        lbl.pack()
        self._drag_photo_ref = photo

        self._drag_window.geometry(f"+{event.x_root + 10}+{event.y_root + 10}")

        root = self.winfo_toplevel()
        self._drag_motion_binding = root.bind("<B1-Motion>", self._on_stamp_drag_motion)
        self._drag_release_binding = root.bind("<ButtonRelease-1>", self._on_stamp_drag_release)

    def _on_stamp_drag_motion(self, event):
        if hasattr(self, '_drag_window') and self._drag_window.winfo_exists():
            self._drag_window.geometry(f"+{event.x_root + 10}+{event.y_root + 10}")

    def _on_stamp_drag_release(self, event):
        import tkinter as tk

        root = self.winfo_toplevel()
        if hasattr(self, '_drag_motion_binding'):
            root.unbind("<B1-Motion>", self._drag_motion_binding)
        if hasattr(self, '_drag_release_binding'):
            root.unbind("<ButtonRelease-1>", self._drag_release_binding)

        if hasattr(self, '_drag_window') and self._drag_window.winfo_exists():
            self._drag_window.destroy()

        template_id = getattr(self, '_drag_template_id', None)
        if template_id is None:
            return

        target = getattr(self, '_drop_target', None)
        if target is None:
            return

        try:
            tx = target.winfo_rootx()
            ty = target.winfo_rooty()
            tw = target.winfo_width()
            th = target.winfo_height()

            if (tx <= event.x_root <= tx + tw and ty <= event.y_root <= ty + th):
                if self.on_create_instance:
                    self.on_create_instance(template_id)
        except tk.TclError:
            pass

    # ═══════════════════════════════════════════════════════════════════
    #  Instance Editing
    # ═══════════════════════════════════════════════════════════════════

    def _update_edit_controls(self):
        if not self._editing_instance_id or not self._instance_manager:
            self._editing_label.configure(text="双击模板添加印章到页面", text_color=Colors.TEXT_SECONDARY)
            self._size_slider.set(20)
            self._size_label.configure(text="20%")
            self._opacity_slider.set(68)
            self._opacity_label.configure(text="68%")
            self._rotation_slider.set(0)
            self._rotation_label.configure(text="0°")
            return

        inst = self._instance_manager.get_instance(self._editing_instance_id)
        if inst is None:
            self._editing_instance_id = None
            self._update_edit_controls()
            return

        template_name = "未知"
        if self._stamp_manager:
            tmpl = self._stamp_manager.get_stamp(inst.template_id)
            if tmpl:
                template_name = tmpl.name

        self._editing_label.configure(
            text=f"「{template_name}」 第 {inst.page_index + 1} 页",
            text_color=Colors.PRIMARY_LIGHT,
        )

        self._size_slider.set(inst.size_ratio * 100)
        self._size_label.configure(text=f"{inst.size_ratio * 100:.0f}%")

        self._opacity_slider.set(inst.opacity * 100)
        self._opacity_label.configure(text=f"{inst.opacity * 100:.0f}%")

        self._rotation_slider.set(inst.rotation)
        self._rotation_label.configure(text=f"{inst.rotation:.0f}°")

    def _on_size_changed(self, value, unit, label):
        pct = float(value)
        label.configure(text=f"{pct:.0f}{unit}")
        if self._editing_instance_id and self.on_instance_property_changed:
            self.on_instance_property_changed(self._editing_instance_id, size_ratio=pct / 100.0)

    def _on_opacity_changed(self, value, unit, label):
        pct = float(value)
        label.configure(text=f"{pct:.0f}{unit}")
        if self._editing_instance_id and self.on_instance_property_changed:
            self.on_instance_property_changed(self._editing_instance_id, opacity=pct / 100.0)

    def _on_rotation_changed(self, value, unit, label):
        deg = float(value)
        label.configure(text=f"{deg:.0f}{unit}")
        if self._editing_instance_id and self.on_instance_property_changed:
            self.on_instance_property_changed(self._editing_instance_id, rotation=deg)

    # ═══════════════════════════════════════════════════════════════════
    #  Page Navigation
    # ═══════════════════════════════════════════════════════════════════

    def _prev_page(self):
        if self._page_count > 0:
            self._current_preview = (self._current_preview - 1) % self._page_count
            self._update_nav_label()
            if self.on_preview_page_changed:
                self.on_preview_page_changed(self._current_preview)

    def _next_page(self):
        if self._page_count > 0:
            self._current_preview = (self._current_preview + 1) % self._page_count
            self._update_nav_label()
            if self.on_preview_page_changed:
                self.on_preview_page_changed(self._current_preview)

    def _update_nav_label(self):
        if self._page_count == 0:
            self._page_label.configure(text="- / -")
        else:
            self._page_label.configure(text=f"{self._current_preview + 1}  /  {self._page_count}")
