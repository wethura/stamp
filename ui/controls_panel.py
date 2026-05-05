import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
from PIL import Image, ImageTk
from typing import Optional, List, Callable

from processing.stamp import load_stamp
from processing.stamp_manager import StampData
from processing.stamp_instance import StampInstance, StampInstanceManager


class ControlsPanel(tk.Frame):
    def __init__(self, parent,
                 on_pages_changed=None,
                 on_preview_page_changed=None,
                 on_create_instance=None,
                 **kwargs):
        super().__init__(parent, **kwargs)
        self.on_pages_changed = on_pages_changed
        self.on_preview_page_changed = on_preview_page_changed
        self.on_create_instance = on_create_instance

        self._page_vars = []
        self._page_count = 0
        self._current_preview = 0

        # Template library
        self._stamps: List[StampData] = []
        self._stamp_previews: dict = {}
        self._stamp_manager = None

        # Instance editing
        self._instance_manager: Optional[StampInstanceManager] = None
        self._editing_instance_id: Optional[str] = None

        self._build_ui()

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

    def _build_ui(self):
        # === Template Library ===
        stamp_frame = tk.LabelFrame(self, text="章模板库（双击添加到当前页）", padx=5, pady=5)
        stamp_frame.pack(fill=tk.X, padx=5, pady=5)

        btn_frame = tk.Frame(stamp_frame)
        btn_frame.pack(fill=tk.X, pady=2)
        tk.Button(btn_frame, text="导入新章", command=self._import_stamp).pack(
            side=tk.LEFT, expand=True, fill=tk.X, padx=1)

        list_frame = tk.Frame(stamp_frame)
        list_frame.pack(fill=tk.BOTH, expand=True, pady=5)

        scroll = tk.Scrollbar(list_frame)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)

        self._stamp_canvas = tk.Canvas(list_frame, height=170, yscrollcommand=scroll.set)
        self._stamp_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.config(command=self._stamp_canvas.yview)

        self._stamp_inner = tk.Frame(self._stamp_canvas)
        self._stamp_canvas.create_window((0, 0), window=self._stamp_inner, anchor=tk.NW)
        self._stamp_inner.bind("<Configure>",
            lambda e: self._stamp_canvas.configure(scrollregion=self._stamp_canvas.bbox("all")))

        # === Instance Editing ===
        self._edit_frame = tk.LabelFrame(self, text="编辑章", padx=5, pady=5)
        self._edit_frame.pack(fill=tk.X, padx=5, pady=5)

        self._editing_label = tk.Label(self._edit_frame, text="双击模板添加印章到页面", fg="gray")
        self._editing_label.pack(fill=tk.X)

        # Size slider
        size_frame = tk.Frame(self._edit_frame)
        size_frame.pack(fill=tk.X, pady=2)
        tk.Label(size_frame, text="大小:").pack(side=tk.LEFT)
        self._size_label = tk.Label(size_frame, text="20%", width=5)
        self._size_label.pack(side=tk.RIGHT)
        self._size_var = tk.DoubleVar(value=20.0)
        self._size_slider = ttk.Scale(size_frame, from_=5, to=80, orient=tk.HORIZONTAL,
                                       variable=self._size_var, command=self._on_size_changed)
        self._size_slider.pack(fill=tk.X, side=tk.LEFT, expand=True, padx=5)
        self._size_slider.config(state='disabled')

        # Opacity slider
        opacity_frame = tk.Frame(self._edit_frame)
        opacity_frame.pack(fill=tk.X, pady=2)
        tk.Label(opacity_frame, text="透明度:").pack(side=tk.LEFT)
        self._opacity_label = tk.Label(opacity_frame, text="100%", width=5)
        self._opacity_label.pack(side=tk.RIGHT)
        self._opacity_var = tk.DoubleVar(value=100.0)
        self._opacity_slider = ttk.Scale(opacity_frame, from_=0, to=100, orient=tk.HORIZONTAL,
                                          variable=self._opacity_var, command=self._on_opacity_changed)
        self._opacity_slider.pack(fill=tk.X, side=tk.LEFT, expand=True, padx=5)
        self._opacity_slider.config(state='disabled')

        # Rotation slider
        rotation_frame = tk.Frame(self._edit_frame)
        rotation_frame.pack(fill=tk.X, pady=2)
        tk.Label(rotation_frame, text="旋转:").pack(side=tk.LEFT)
        self._rotation_label = tk.Label(rotation_frame, text="0°", width=5)
        self._rotation_label.pack(side=tk.RIGHT)
        self._rotation_var = tk.DoubleVar(value=0.0)
        self._rotation_slider = ttk.Scale(rotation_frame, from_=0, to=360, orient=tk.HORIZONTAL,
                                           variable=self._rotation_var, command=self._on_rotation_changed)
        self._rotation_slider.pack(fill=tk.X, side=tk.LEFT, expand=True, padx=5)
        self._rotation_slider.config(state='disabled')

        # === Page Navigation ===
        nav_frame = tk.LabelFrame(self, text="预览页", padx=5, pady=5)
        nav_frame.pack(fill=tk.X, padx=5, pady=5)

        self._prev_btn = tk.Button(nav_frame, text="<", width=3, command=self._prev_page)
        self._prev_btn.pack(side=tk.LEFT)

        self._page_label = tk.Label(nav_frame, text="- / -", width=8)
        self._page_label.pack(side=tk.LEFT, expand=True)

        self._next_btn = tk.Button(nav_frame, text=">", width=3, command=self._next_page)
        self._next_btn.pack(side=tk.LEFT)

        # === Stamp Pages ===
        pages_frame = tk.LabelFrame(self, text="盖章页码", padx=5, pady=5)
        pages_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        scroll2 = tk.Scrollbar(pages_frame)
        scroll2.pack(side=tk.RIGHT, fill=tk.Y)

        self._pages_canvas = tk.Canvas(pages_frame, yscrollcommand=scroll2.set)
        self._pages_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll2.config(command=self._pages_canvas.yview)

        self._pages_inner = tk.Frame(self._pages_canvas)
        self._pages_canvas.create_window((0, 0), window=self._pages_inner, anchor=tk.NW)
        self._pages_inner.bind("<Configure>",
            lambda e: self._pages_canvas.configure(scrollregion=self._pages_canvas.bbox("all")))

    # === Template Library Methods ===

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
        for w in self._stamp_inner.winfo_children():
            w.destroy()
        self._stamp_previews.clear()

        if not self._stamp_manager:
            return

        self._stamps = self._stamp_manager.list_stamps()

        for idx, stamp in enumerate(self._stamps):
            row = idx // 2
            col = idx % 2
            self._add_stamp_item(stamp, row, col)

        self._update_edit_controls()

    def _add_stamp_item(self, stamp: StampData, row: int, col: int):
        container = tk.Frame(self._stamp_inner, relief=tk.RIDGE, bd=1, cursor="hand2")
        container.grid(row=row, column=col, padx=3, pady=3, sticky="nsew")
        self._stamp_inner.columnconfigure(col, weight=1)

        img = stamp.get_image()
        thumb_size = 100
        img.thumbnail((thumb_size, thumb_size), Image.LANCZOS)
        photo = ImageTk.PhotoImage(img)
        self._stamp_previews[stamp.id] = photo

        lbl_img = tk.Label(container, image=photo, cursor="hand2")
        lbl_img.pack(padx=5, pady=(5, 2))

        lbl_name = tk.Label(container, text=stamp.name, font=("Arial", 9), cursor="hand2")
        lbl_name.pack()

        # Delete template button
        btn_del = tk.Label(container, text="删除", fg="red", cursor="hand2",
                           font=("Arial", 9, "underline"))
        btn_del.pack(fill=tk.X, padx=2, pady=(0, 2))
        btn_del.bind("<Button-1>", lambda e, sid=stamp.id: self._delete_stamp(sid))

        # Double-click to create instance
        def on_double_click(e, sid=stamp.id):
            self._on_stamp_double_click(sid)

        container.bind("<Double-Button-1>", on_double_click)
        lbl_img.bind("<Double-Button-1>", on_double_click)
        lbl_name.bind("<Double-Button-1>", on_double_click)

    def _on_stamp_double_click(self, template_id: str):
        """Handle double-click on template - create instance"""
        if self.on_create_instance:
            self.on_create_instance(template_id)

    def _delete_stamp(self, stamp_id: str):
        if not self._stamp_manager:
            return

        stamp = self._stamp_manager.get_stamp(stamp_id)
        stamp_name = stamp.name if stamp else "该章"

        if not messagebox.askyesno("确认删除", f"确定要删除「{stamp_name}」吗？"):
            return

        self._stamp_manager.delete_stamp(stamp_id)
        if self._editing_instance_id:
            # Check if editing instance belongs to deleted template
            if self._instance_manager:
                inst = self._instance_manager.get_instance(self._editing_instance_id)
                if inst and inst.template_id == stamp_id:
                    self._editing_instance_id = None
        self._refresh_stamp_list()

    # === Instance Editing Methods ===

    def _update_edit_controls(self):
        if not self._editing_instance_id or not self._instance_manager:
            self._editing_label.config(text="双击模板添加印章到页面", fg="gray")
            self._size_slider.config(state='disabled')
            self._size_var.set(20.0)
            self._size_label.config(text="20%")
            self._opacity_slider.config(state='disabled')
            self._opacity_var.set(100.0)
            self._opacity_label.config(text="100%")
            self._rotation_slider.config(state='disabled')
            self._rotation_var.set(0.0)
            self._rotation_label.config(text="0°")
            return

        inst = self._instance_manager.get_instance(self._editing_instance_id)
        if inst is None:
            self._editing_instance_id = None
            self._update_edit_controls()
            return

        # Resolve template name
        template_name = "未知"
        if self._stamp_manager:
            tmpl = self._stamp_manager.get_stamp(inst.template_id)
            if tmpl:
                template_name = tmpl.name

        self._editing_label.config(
            text=f"编辑「{template_name}」- 第{inst.page_index + 1}页",
            fg="black"
        )

        self._size_var.set(inst.size_ratio * 100)
        self._size_label.config(text=f"{inst.size_ratio * 100:.0f}%")
        self._size_slider.config(state='normal')

        self._opacity_var.set(inst.opacity * 100)
        self._opacity_label.config(text=f"{inst.opacity * 100:.0f}%")
        self._opacity_slider.config(state='normal')

        self._rotation_var.set(inst.rotation)
        self._rotation_label.config(text=f"{inst.rotation:.0f}°")
        self._rotation_slider.config(state='normal')

    def _on_size_changed(self, val):
        pct = float(val)
        self._size_label.config(text=f"{pct:.0f}%")
        if self._editing_instance_id and self.on_instance_property_changed:
            self.on_instance_property_changed(self._editing_instance_id, size_ratio=pct / 100.0)

    def _on_opacity_changed(self, val):
        pct = float(val)
        self._opacity_label.config(text=f"{pct:.0f}%")
        if self._editing_instance_id and self.on_instance_property_changed:
            self.on_instance_property_changed(self._editing_instance_id, opacity=pct / 100.0)

    def _on_rotation_changed(self, val):
        deg = float(val)
        self._rotation_label.config(text=f"{deg:.0f}°")
        if self._editing_instance_id and self.on_instance_property_changed:
            self.on_instance_property_changed(self._editing_instance_id, rotation=deg)

    # Callback property for instance property changes
    on_instance_property_changed = None

    # === Page Navigation Methods ===

    def set_pages(self, count: int):
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
