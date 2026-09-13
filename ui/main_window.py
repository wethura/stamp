"""Main application window — CustomTkinter CTkFrame inside the root CTk window."""

import customtkinter as ctk

from ui.preview_canvas import PreviewCanvas
from ui.controls_panel import ControlsPanel
from ui.theme import Colors, Fonts, Spacing, load_app_icon


class MainWindow(ctk.CTkFrame):
    """Main application frame placed inside the root CTk window."""

    def __init__(self, parent, controller):
        super().__init__(parent, fg_color=Colors.SURFACE_CANVAS)
        self.controller = controller

        # Configure root window
        parent.title("盖章工具")
        parent.geometry("1180x800")
        parent.minsize(900, 600)
        load_app_icon(parent)

        self._build_ui()
        self.pack(fill="both", expand=True)

    def _build_ui(self):
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # Brand and primary document actions.
        toolbar = ctk.CTkFrame(self, height=88, corner_radius=0,
                               fg_color=Colors.SURFACE_BASE)
        toolbar.grid(row=0, column=0, sticky="ew")
        toolbar.pack_propagate(False)

        seal = ctk.CTkLabel(
            toolbar, text="印", width=42, height=42, corner_radius=10,
            fg_color=Colors.PRIMARY, text_color="white",
            font=(Fonts.FAMILY, 24, "bold"),
        )
        seal.pack(side="left", padx=(24, 12))
        brand = ctk.CTkFrame(toolbar, fg_color="transparent")
        brand.pack(side="left")
        ctk.CTkLabel(brand, text="印章工作台", anchor="w", height=28,
                     font=(Fonts.FAMILY, 20, "bold"),
                     text_color=Colors.TEXT_PRIMARY).pack(anchor="w")
        ctk.CTkLabel(brand, text="让每一份文档，正式落印。", height=22,
                     font=(Fonts.FAMILY, Fonts.SMALL_SIZE),
                     text_color=Colors.TEXT_SECONDARY).pack(anchor="w")

        ctk.CTkButton(
            toolbar, text="导出盖章文档  →", width=156, height=40,
            corner_radius=8, fg_color=Colors.PRIMARY,
            hover_color=Colors.PRIMARY_HOVER, text_color="white",
            font=(Fonts.FAMILY, Fonts.BODY_SIZE, "bold"),
            command=self.controller.export_pdf,
        ).pack(side="right", padx=(12, 24))
        ctk.CTkButton(
            toolbar, text="打开文档", width=112, height=40,
            corner_radius=8, fg_color=Colors.SURFACE_BASE,
            border_width=1, border_color=Colors.BORDER_SUBTLE,
            hover_color=Colors.SURFACE_RAISED, text_color=Colors.TEXT_PRIMARY,
            font=(Fonts.FAMILY, Fonts.BODY_SIZE),
            command=self.controller.open_document,
        ).pack(side="right")

        # ── Content area ───────────────────────────────────────────
        content = ctk.CTkFrame(self, fg_color="transparent")
        content.grid(row=1, column=0, sticky="nsew", padx=20, pady=(18, 12))
        content.grid_columnconfigure(0, weight=1)
        content.grid_columnconfigure(1, weight=0)
        content.grid_rowconfigure(0, weight=1)

        workspace = ctk.CTkFrame(content, fg_color=Colors.SURFACE_CANVAS)
        workspace.grid(row=0, column=0, sticky="nsew", padx=(0, 18))
        workspace.grid_columnconfigure(0, weight=1)
        workspace.grid_rowconfigure(1, weight=1)
        preview_header = ctk.CTkFrame(workspace, fg_color="transparent", height=36)
        preview_header.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        ctk.CTkLabel(preview_header, text="文档预览",
                     font=(Fonts.FAMILY, Fonts.HEADING_SIZE, "bold"),
                     text_color=Colors.TEXT_PRIMARY).pack(side="left")

        # Page navigation — keeps the active page visible in continuous
        # scroll mode, and lets the user step page by page.
        page_nav = ctk.CTkFrame(preview_header, fg_color="transparent")
        page_nav.pack(side="right")
        self._prev_page_btn = ctk.CTkButton(
            page_nav, text="◀", width=28, height=26,
            fg_color=Colors.SURFACE_RAISED, hover_color=Colors.SURFACE_OVERLAY,
            text_color=Colors.TEXT_PRIMARY,
            font=(Fonts.FAMILY, Fonts.SMALL_SIZE), corner_radius=6,
            state="disabled",
            command=lambda: self.preview.scroll_to_page(self.preview.get_active_page() - 1),
        )
        self._prev_page_btn.pack(side="left", padx=(0, Spacing.PAD_XS))
        self._page_label = ctk.CTkLabel(
            page_nav, text="第 – / – 页", width=90,
            font=(Fonts.FAMILY, Fonts.SMALL_SIZE),
            text_color=Colors.TEXT_SECONDARY,
        )
        self._page_label.pack(side="left")
        self._next_page_btn = ctk.CTkButton(
            page_nav, text="▶", width=28, height=26,
            fg_color=Colors.SURFACE_RAISED, hover_color=Colors.SURFACE_OVERLAY,
            text_color=Colors.TEXT_PRIMARY,
            font=(Fonts.FAMILY, Fonts.SMALL_SIZE), corner_radius=6,
            state="disabled",
            command=lambda: self.preview.scroll_to_page(self.preview.get_active_page() + 1),
        )
        self._next_page_btn.pack(side="left", padx=(Spacing.PAD_XS, 0))

        self.preview = PreviewCanvas(
            workspace,
            on_stamp_position_changed=self.controller.on_instance_position_changed,
            on_delete_instance=self.controller.delete_instance,
            on_instance_selected=self.controller.on_instance_selected,
            on_drag_end=self.controller.on_instance_drag_end,
            on_active_page_changed=self._on_preview_page_changed,
            on_page_count_changed=self._update_page_nav,
        )
        self.preview.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 12))

        # Scrollable inspector
        self.controls = ControlsPanel(
            content,
            on_create_instance=self.controller.create_instance_from_template,
        )
        self.controls.grid(row=0, column=1, sticky="nsew")
        self.controls.on_instance_property_changed = self.controller.update_instance_property

        # Allow controls to detect drag-drop onto preview area
        self.controls._drop_target = self.preview.canvas

        # ── Status bar ─────────────────────────────────────────────
        status_frame = ctk.CTkFrame(self, height=32, corner_radius=0, fg_color=Colors.SURFACE_BASE)
        status_frame.grid(row=2, column=0, sticky="ew")
        status_frame.pack_propagate(False)

        # Subtle top border
        status_border = ctk.CTkFrame(status_frame, height=1, fg_color=Colors.BORDER_SUBTLE)
        status_border.place(x=0, rely=0.0, relwidth=1.0)

        self._status_label = ctk.CTkLabel(
            status_frame,
            text="就绪 · 打开文档后，双击右侧印章即可添加",
            font=(Fonts.FAMILY, Fonts.SMALL_SIZE),
            text_color=Colors.TEXT_SECONDARY,
            anchor="w",
        )
        self._status_label.pack(side="left", padx=Spacing.PAD_MD, fill="x", expand=True)

    def _on_preview_page_changed(self, page_index: int):
        self.controller.on_active_page_changed(page_index)
        self._update_page_nav()

    def _update_page_nav(self, *_):
        total = self.preview.page_count
        if total <= 0:
            self._page_label.configure(text="第 – / – 页")
            self._prev_page_btn.configure(state="disabled")
            self._next_page_btn.configure(state="disabled")
            return

        current = min(self.preview.get_active_page(), total - 1)
        self._page_label.configure(text=f"第 {current + 1} / {total} 页")
        self._prev_page_btn.configure(state="normal" if current > 0 else "disabled")
        self._next_page_btn.configure(state="normal" if current < total - 1 else "disabled")

    def set_status(self, message: str):
        self._status_label.configure(text=message)
