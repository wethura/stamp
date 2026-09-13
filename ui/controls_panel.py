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
                 on_create_instance=None):
        super().__init__(
            parent,
            width=PANEL_WIDTH,
            corner_radius=12,
            border_width=1, border_color=Colors.BORDER_SUBTLE,
            fg_color=Colors.SURFACE_BASE,
            scrollbar_fg_color=Colors.SURFACE_BASE,
            scrollbar_button_color=Colors.SURFACE_RAISED,
            scrollbar_button_hover_color=Colors.SURFACE_OVERLAY,
        )

        self.on_create_instance = on_create_instance

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

    # ═══════════════════════════════════════════════════════════════════
    #  UI Construction
    # ═══════════════════════════════════════════════════════════════════

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)

        row = 0

        # ── Template Library Section ─────────────────────────────────
        self._build_section_heading("01   印章库", row)
        row += 1

        import_btn = ctk.CTkButton(
            self,
            text="＋  导入印章",
            fg_color=Colors.SURFACE_RAISED,
            hover_color=Colors.SURFACE_OVERLAY,
            text_color=Colors.PRIMARY,
            border_width=1, border_color=Colors.BORDER_SUBTLE,
            font=(Fonts.FAMILY, Fonts.BODY_SIZE, "bold"),
            height=40,
            corner_radius=6,
            command=self._import_stamp,
        )
        import_btn.grid(row=row, column=0, padx=Spacing.PAD_LG, pady=(Spacing.PAD_XS, Spacing.PAD_SM), sticky="ew")
        row += 1

        # Scrollable stamp card grid — show one row at a time
        # Space for a complete card row, including its actions.
        self._scroll_frame = ctk.CTkScrollableFrame(
            self, fg_color="transparent", height=202,
        )
        self._scroll_frame.grid(row=row, column=0, padx=Spacing.PAD_LG, pady=(Spacing.PAD_XS, Spacing.PAD_SM), sticky="nsew")
        self._scroll_frame.grid_columnconfigure((0, 1), weight=1)
        row += 1

        # ── Instance Editing Section ─────────────────────────────────
        self._build_separator(row)
        row += 1

        self._build_section_heading("02   印章调整", row)
        row += 1

        self._editing_label = ctk.CTkLabel(
            self,
            text="双击模板添加印章到页面",
            font=(Fonts.FAMILY, Fonts.SMALL_SIZE),
            text_color=Colors.TEXT_SECONDARY,
            fg_color=Colors.SURFACE_RAISED, corner_radius=8,
            height=48, wraplength=260,
        )
        self._editing_label.grid(row=row, column=0, padx=Spacing.PAD_LG, pady=(Spacing.PAD_XS, Spacing.PAD_SM), sticky="ew")
        row += 1

        # Sliders
        self._size_slider, self._size_label = self._add_slider_row(
            row, "印章大小", 5, 80, "%", self._on_size_changed)
        row += 2

        self._opacity_slider, self._opacity_label = self._add_slider_row(
            row, "透明度", 0, 100, "%", self._on_opacity_changed)
        row += 2

        # ── Rotation controls ──────────────────────────────────────────
        self._build_rotation_row(row)
        row += 2

    def _build_section_heading(self, text: str, row: int):
        """Create a section heading with a clear typographic hierarchy."""
        label = ctk.CTkLabel(
            self, text=text,
            font=(Fonts.FAMILY, Fonts.HEADING_SIZE, "bold"),
            text_color=Colors.TEXT_PRIMARY,
        )
        label.grid(row=row, column=0, padx=(Spacing.PAD_MD, Spacing.PAD_SM), pady=(Spacing.PAD_XL, Spacing.PAD_SM), sticky="w")

    def _build_separator(self, row: int):
        """Create a subtle 1px separator between sections."""
        sep = ctk.CTkFrame(self, height=1, fg_color=Colors.BORDER_SUBTLE)
        sep.grid(row=row, column=0, padx=Spacing.PAD_LG, pady=(Spacing.PAD_SM, Spacing.PAD_XS), sticky="ew")

    def _add_slider_row(self, row, label_text, from_val, to_val, unit, callback):
        """Create a labeled slider row. Returns (slider, value_label)."""
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=row, column=0, padx=Spacing.PAD_LG, sticky="ew")
        header.grid_columnconfigure(0, weight=1)

        name_label = ctk.CTkLabel(
            header, text=label_text,
            font=(Fonts.FAMILY, Fonts.SMALL_SIZE),
            text_color=Colors.TEXT_PRIMARY,
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
            button_hover_color=Colors.PRIMARY_HOVER,
            progress_color=Colors.PRIMARY,
            fg_color=Colors.SURFACE_OVERLAY,
            number_of_steps=to_val - from_val,
            command=lambda v, u=unit, vl=val_label, cb=callback: cb(v, u, vl),
        )
        slider.set(from_val)
        slider.grid(row=row + 1, column=0, padx=Spacing.PAD_MD, pady=(Spacing.PAD_XS, Spacing.PAD_SM), sticky="ew")

        return slider, val_label

    def _build_rotation_row(self, row):
        """Create rotation controls: left 90°, input field, right 90°."""
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=row, column=0, padx=Spacing.PAD_LG, sticky="ew")
        header.grid_columnconfigure(1, weight=1)

        label = ctk.CTkLabel(
            header, text="旋转角度",
            font=(Fonts.FAMILY, Fonts.SMALL_SIZE),
            text_color=Colors.TEXT_PRIMARY,
        )
        label.grid(row=0, column=0, sticky="w")

        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.grid(row=row + 1, column=0, padx=Spacing.PAD_LG, pady=(Spacing.PAD_XS, Spacing.PAD_SM), sticky="ew")
        btn_frame.grid_columnconfigure(1, weight=1)

        left_btn = ctk.CTkButton(
            btn_frame, text="◀ 90°", width=50, height=28,
            fg_color=Colors.SURFACE_RAISED, hover_color=Colors.SURFACE_OVERLAY,
            text_color=Colors.TEXT_PRIMARY,
            font=(Fonts.FAMILY, Fonts.SMALL_SIZE), corner_radius=6,
            command=self._rotate_left,
        )
        left_btn.grid(row=0, column=0, padx=(0, Spacing.PAD_XS))

        self._rotation_entry = ctk.CTkEntry(
            btn_frame, width=60, height=28,
            font=(Fonts.FAMILY, Fonts.BODY_SIZE),
            fg_color=Colors.SURFACE_RAISED, text_color=Colors.TEXT_PRIMARY,
            border_width=1, border_color=Colors.SURFACE_OVERLAY,
            corner_radius=6, justify="center",
        )
        self._rotation_entry.insert(0, "0")
        self._rotation_entry.grid(row=0, column=1, sticky="ew")
        self._rotation_entry.bind("<Return>", self._on_rotation_entry)
        self._rotation_entry.bind("<FocusOut>", self._on_rotation_entry)

        right_btn = ctk.CTkButton(
            btn_frame, text="90° ▶", width=50, height=28,
            fg_color=Colors.SURFACE_RAISED, hover_color=Colors.SURFACE_OVERLAY,
            text_color=Colors.TEXT_PRIMARY,
            font=(Fonts.FAMILY, Fonts.SMALL_SIZE), corner_radius=6,
            command=self._rotate_right,
        )
        right_btn.grid(row=0, column=2, padx=(Spacing.PAD_XS, 0))

    def _rotate_left(self):
        if not self._editing_instance_id:
            return
        inst = self._instance_manager.get_instance(self._editing_instance_id)
        if inst is None:
            return
        new_angle = (inst.rotation - 90) % 360
        self._apply_rotation(new_angle)

    def _rotate_right(self):
        if not self._editing_instance_id:
            return
        inst = self._instance_manager.get_instance(self._editing_instance_id)
        if inst is None:
            return
        new_angle = (inst.rotation + 90) % 360
        self._apply_rotation(new_angle)

    def _on_rotation_entry(self, event=None):
        if not self._editing_instance_id:
            return
        text = self._rotation_entry.get().strip().replace("°", "")
        try:
            angle = float(text) % 360
        except ValueError:
            return
        self._apply_rotation(angle)

    def _apply_rotation(self, angle: float):
        """Apply rotation angle to the editing instance."""
        self._rotation_entry.delete(0, "end")
        self._rotation_entry.insert(0, f"{angle:.0f}")
        if self._editing_instance_id and self.on_instance_property_changed:
            self.on_instance_property_changed(self._editing_instance_id, rotation=angle)

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
        if not stamps:
            ctk.CTkLabel(
                self._scroll_frame, text="尚未添加印章\n\n导入一张印章图片，建立你的印章库",
                font=(Fonts.FAMILY, Fonts.SMALL_SIZE),
                text_color=Colors.TEXT_SECONDARY, height=156,
                wraplength=240,
            ).grid(row=0, column=0, columnspan=2, sticky="ew", padx=8)
        for idx, stamp in enumerate(stamps):
            row_idx = idx // 2
            col_idx = idx % 2

            card = StampCard(
                stamp, self._scroll_frame,
                on_double_click=self._on_card_double_click,
                on_delete_requested=self._delete_stamp,
                on_drag_start=self._start_stamp_drag,
            )
            card.grid(row=row_idx, column=col_idx, padx=Spacing.PAD_XS, pady=Spacing.PAD_XS, sticky="nsew")

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
            self._rotation_entry.delete(0, "end")
            self._rotation_entry.insert(0, "0")
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
            text_color=Colors.PRIMARY,
        )

        self._size_slider.set(inst.size_ratio * 100)
        self._size_label.configure(text=f"{inst.size_ratio * 100:.0f}%")

        self._opacity_slider.set(inst.opacity * 100)
        self._opacity_label.configure(text=f"{inst.opacity * 100:.0f}%")

        self._rotation_entry.delete(0, "end")
        self._rotation_entry.insert(0, f"{inst.rotation:.0f}")

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
