"""Main application window — CustomTkinter CTkFrame inside the root CTk window."""

import tkinter as tk

import customtkinter as ctk

from ui.preview_canvas import PreviewCanvas
from ui.controls_panel import ControlsPanel
from ui.theme import Colors, Fonts, Spacing, PANEL_WIDTH, load_app_icon


class MainWindow(ctk.CTkFrame):
    """Main application frame placed inside the root CTk window."""

    def __init__(self, parent, controller):
        super().__init__(parent, fg_color="transparent")
        self.controller = controller

        # Configure root window
        parent.title("盖章工具")
        parent.geometry("1100x750")
        parent.minsize(800, 500)
        load_app_icon(parent)

        self._build_ui()
        self.pack(fill="both", expand=True)

    def _build_ui(self):
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # ── Toolbar ────────────────────────────────────────────────
        toolbar = ctk.CTkFrame(self, height=44, fg_color=Colors.BG_DARK)
        toolbar.grid(row=0, column=0, sticky="ew")
        toolbar.grid_propagate(False)

        # Gold bottom border
        border = ctk.CTkFrame(toolbar, height=2, fg_color=Colors.GOLD)
        border.place(x=0, rely=1.0, relwidth=1.0, y=0)

        btn_open = ctk.CTkButton(
            toolbar,
            text="打开文档",
            fg_color="transparent",
            hover_color="#2A1520",
            text_color=Colors.TEXT_ON_DARK,
            font=(Fonts.FAMILY, Fonts.BODY_SIZE),
            command=self.controller.open_document,
        )
        btn_open.pack(side="left", padx=(12, 4), pady=6)

        btn_export = ctk.CTkButton(
            toolbar,
            text="导出盖章文档",
            fg_color="transparent",
            hover_color="#2A1520",
            text_color=Colors.TEXT_ON_DARK,
            font=(Fonts.FAMILY, Fonts.BODY_SIZE),
            command=self.controller.export_pdf,
        )
        btn_export.pack(side="left", padx=4, pady=6)

        # ── Content area ───────────────────────────────────────────
        content = ctk.CTkFrame(self, fg_color="transparent")
        content.grid(row=1, column=0, sticky="nsew")
        content.grid_columnconfigure(0, weight=1)
        content.grid_columnconfigure(1, weight=0)
        content.grid_rowconfigure(0, weight=1)

        # Preview
        self.preview = PreviewCanvas(
            content,
            on_stamp_position_changed=self.controller.on_instance_position_changed,
            on_delete_instance=self.controller.delete_instance,
            on_instance_selected=self.controller.on_instance_selected,
            on_drag_end=self.controller.on_instance_drag_end,
        )
        self.preview.grid(row=0, column=0, sticky="nsew")

        # Controls
        self.controls = ControlsPanel(
            content,
            on_preview_page_changed=self.controller.on_preview_page_change,
            on_create_instance=self.controller.create_instance_from_template,
        )
        self.controls.grid(row=0, column=1, sticky="nsew")
        self.controls.on_instance_property_changed = self.controller.update_instance_property

        # Allow controls to detect drag-drop onto preview area
        self.controls._drop_target = self.preview.canvas

        # ── Status bar ─────────────────────────────────────────────
        status_frame = ctk.CTkFrame(self, height=24, fg_color=Colors.BG_DARK)
        status_frame.grid(row=2, column=0, sticky="ew")
        status_frame.grid_propagate(False)

        # Gold top border
        status_border = ctk.CTkFrame(status_frame, height=1, fg_color=Colors.GOLD)
        status_border.place(x=0, rely=0.0, relwidth=1.0)

        self._status_label = ctk.CTkLabel(
            status_frame,
            text="就绪",
            font=(Fonts.FAMILY, 10),
            text_color=Colors.TEXT_SECONDARY,
            anchor="w",
        )
        self._status_label.pack(side="left", padx=10, fill="x", expand=True)

    def set_status(self, message: str):
        self._status_label.configure(text=message)
