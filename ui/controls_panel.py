import tkinter as tk
from tkinter import ttk


class ControlsPanel(tk.Frame):
    def __init__(self, parent,
                 on_pages_changed=None,
                 on_size_changed=None,
                 on_preview_page_changed=None,
                 **kwargs):
        super().__init__(parent, **kwargs)
        self.on_pages_changed = on_pages_changed
        self.on_size_changed = on_size_changed
        self.on_preview_page_changed = on_preview_page_changed

        self._page_vars = []
        self._page_count = 0
        self._current_preview = 0

        self._build_ui()

    def _build_ui(self):
        # Stamp size slider
        size_frame = tk.LabelFrame(self, text="章大小", padx=5, pady=5)
        size_frame.pack(fill=tk.X, padx=5, pady=5)

        self._size_var = tk.DoubleVar(value=20.0)
        self._size_label = tk.Label(size_frame, text="20%")
        self._size_label.pack(side=tk.RIGHT)

        slider = ttk.Scale(size_frame, from_=5, to=80, orient=tk.HORIZONTAL,
                           variable=self._size_var, command=self._on_size_changed)
        slider.pack(fill=tk.X, side=tk.LEFT, expand=True)

        # Preview page navigation
        nav_frame = tk.LabelFrame(self, text="预览页", padx=5, pady=5)
        nav_frame.pack(fill=tk.X, padx=5, pady=5)

        self._prev_btn = tk.Button(nav_frame, text="<", width=3, command=self._prev_page)
        self._prev_btn.pack(side=tk.LEFT)

        self._page_label = tk.Label(nav_frame, text="- / -", width=8)
        self._page_label.pack(side=tk.LEFT, expand=True)

        self._next_btn = tk.Button(nav_frame, text=">", width=3, command=self._next_page)
        self._next_btn.pack(side=tk.LEFT)

        # Page checkboxes
        pages_frame = tk.LabelFrame(self, text="盖章页码", padx=5, pady=5)
        pages_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        scroll = tk.Scrollbar(pages_frame)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)

        self._pages_canvas = tk.Canvas(pages_frame, yscrollcommand=scroll.set)
        self._pages_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.config(command=self._pages_canvas.yview)

        self._pages_inner = tk.Frame(self._pages_canvas)
        self._pages_canvas.create_window((0, 0), window=self._pages_inner, anchor=tk.NW)
        self._pages_inner.bind("<Configure>",
            lambda e: self._pages_canvas.configure(
                scrollregion=self._pages_canvas.bbox("all")))

    def set_pages(self, count: int):
        """Rebuild page checkbox list."""
        for w in self._pages_inner.winfo_children():
            w.destroy()
        self._page_vars = []
        self._page_count = count
        self._current_preview = 0

        for i in range(count):
            var = tk.BooleanVar(value=True)
            cb = tk.Checkbutton(self._pages_inner, text=f"第 {i+1} 页",
                                variable=var, command=self._on_pages_changed)
            cb.pack(anchor=tk.W)
            self._page_vars.append(var)

        self._update_nav_label()

    def get_selected_pages(self) -> set:
        return {i for i, v in enumerate(self._page_vars) if v.get()}

    def get_size_ratio(self) -> float:
        return self._size_var.get() / 100.0

    def _on_size_changed(self, val):
        pct = float(val)
        self._size_label.config(text=f"{pct:.0f}%")
        if self.on_size_changed:
            self.on_size_changed(pct / 100.0)

    def _on_pages_changed(self):
        if self.on_pages_changed:
            self.on_pages_changed(self.get_selected_pages())

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
            self._page_label.config(text="- / -")
        else:
            self._page_label.config(text=f"{self._current_preview + 1} / {self._page_count}")
