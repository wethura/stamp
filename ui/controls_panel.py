import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
from PIL import Image, ImageTk
from typing import Optional, List, Callable
from dataclasses import dataclass

from processing.stamp import load_stamp
from processing.stamp_manager import StampData


@dataclass
class StampSelection:
    """选中的章信息"""
    stamp_id: str
    stamp_img: Image.Image
    size_ratio: float
    pos_x: float
    pos_y: float


class ControlsPanel(tk.Frame):
    def __init__(self, parent,
                 on_pages_changed=None,
                 on_preview_page_changed=None,
                 on_stamp_selection_changed=None,
                 on_editing_stamp_changed=None,
                 **kwargs):
        super().__init__(parent, **kwargs)
        self.on_pages_changed = on_pages_changed
        self.on_preview_page_changed = on_preview_page_changed
        self.on_stamp_selection_changed = on_stamp_selection_changed
        self.on_editing_stamp_changed = on_editing_stamp_changed

        self._page_vars = []
        self._page_count = 0
        self._current_preview = 0

        # 章相关
        self._stamps: List[StampData] = []
        self._stamp_previews: dict = {}  # stamp_id -> PhotoImage
        self._stamp_manager = None

        # 两种独立的状态：
        # 1. 待盖章的章（选中后会盖到文档上）
        self._selected_stamp_ids: set = set()
        # 2. 正在编辑的章（用于调整位置和大小）
        self._editing_stamp_id: Optional[str] = None

        self._build_ui()

    def set_stamp_manager(self, manager):
        """设置章管理器"""
        self._stamp_manager = manager
        self._refresh_stamp_list()

    def _build_ui(self):
        # === 章管理区域 ===
        stamp_frame = tk.LabelFrame(self, text="章管理", padx=5, pady=5)
        stamp_frame.pack(fill=tk.X, padx=5, pady=5)

        # 导入按钮
        btn_frame = tk.Frame(stamp_frame)
        btn_frame.pack(fill=tk.X, pady=2)
        tk.Button(btn_frame, text="导入新章", command=self._import_stamp).pack(
            side=tk.LEFT, expand=True, fill=tk.X, padx=1)

        # 章预览列表区域
        list_frame = tk.Frame(stamp_frame)
        list_frame.pack(fill=tk.BOTH, expand=True, pady=5)

        scroll = tk.Scrollbar(list_frame)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)

        self._stamp_canvas = tk.Canvas(list_frame, height=150, yscrollcommand=scroll.set)
        self._stamp_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.config(command=self._stamp_canvas.yview)

        self._stamp_inner = tk.Frame(self._stamp_canvas)
        self._stamp_canvas.create_window((0, 0), window=self._stamp_inner, anchor=tk.NW)
        self._stamp_inner.bind("<Configure>",
            lambda e: self._stamp_canvas.configure(scrollregion=self._stamp_canvas.bbox("all")))

        # === 编辑中的章设置 ===
        self._edit_frame = tk.LabelFrame(self, text="编辑章", padx=5, pady=5)
        self._edit_frame.pack(fill=tk.X, padx=5, pady=5)

        self._editing_label = tk.Label(self._edit_frame, text="点击预览区域的章进行编辑", fg="gray")
        self._editing_label.pack(fill=tk.X)

        # 章大小滑块
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

        # === 预览页导航 ===
        nav_frame = tk.LabelFrame(self, text="预览页", padx=5, pady=5)
        nav_frame.pack(fill=tk.X, padx=5, pady=5)

        self._prev_btn = tk.Button(nav_frame, text="<", width=3, command=self._prev_page)
        self._prev_btn.pack(side=tk.LEFT)

        self._page_label = tk.Label(nav_frame, text="- / -", width=8)
        self._page_label.pack(side=tk.LEFT, expand=True)

        self._next_btn = tk.Button(nav_frame, text=">", width=3, command=self._next_page)
        self._next_btn.pack(side=tk.LEFT)

        # === 盖章页码 ===
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

    # === 章管理方法 ===

    def _import_stamp(self):
        """导入新章"""
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
            stamp = self._stamp_manager.add_stamp(name, img, 0.2, 0.7, 0.7)
            # 自动选中该章用于盖章
            self._selected_stamp_ids.add(stamp.id)
            # 自动设置为编辑状态
            self._editing_stamp_id = stamp.id
            self._refresh_stamp_list()
            self._notify_stamp_selection_changed()
            self._notify_editing_stamp_changed()

    def _refresh_stamp_list(self):
        """刷新章列表显示"""
        for w in self._stamp_inner.winfo_children():
            w.destroy()
        self._stamp_previews.clear()
        self._selected_dots = {}

        if not self._stamp_manager:
            return

        self._stamps = self._stamp_manager.list_stamps()

        for stamp in self._stamps:
            self._add_stamp_item(stamp)

        self._update_edit_controls()

    def _add_stamp_item(self, stamp: StampData):
        """添加单个章项到列表"""
        container = tk.Frame(self._stamp_inner, relief=tk.RIDGE, bd=1, cursor="hand2")
        container.pack(fill=tk.X, pady=2, padx=2)

        # 生成缩略图
        img = stamp.get_image()
        thumb_size = 40
        img.thumbnail((thumb_size, thumb_size), Image.LANCZOS)
        photo = ImageTk.PhotoImage(img)
        self._stamp_previews[stamp.id] = photo

        # 顶部：缩略图 + 删除按钮
        top_frame = tk.Frame(container, cursor="hand2")
        top_frame.pack(fill=tk.X, padx=2, pady=2)

        lbl_img = tk.Label(top_frame, image=photo, cursor="hand2")
        lbl_img.pack(side=tk.LEFT, padx=2)

        btn_del = tk.Label(top_frame, text="✕", fg="red", cursor="hand2", font=("Arial", 10))
        btn_del.pack(side=tk.RIGHT, padx=2)
        btn_del.bind("<Button-1>", lambda e, sid=stamp.id: self._delete_stamp(sid))

        # 底部：名称 + 选中状态标记
        name_frame = tk.Frame(container, cursor="hand2")
        name_frame.pack(fill=tk.X, padx=2, pady=(0, 2))

        lbl_name = tk.Label(name_frame, text=stamp.name, font=("Arial", 9), cursor="hand2")
        lbl_name.pack(side=tk.LEFT)

        # 选中状态标记（绿色=已选中用于盖章）
        selected_dot = tk.Label(name_frame, text="○", fg="gray", font=("Arial", 12), cursor="hand2")
        selected_dot.pack(side=tk.RIGHT)

        self._selected_dots[stamp.id] = selected_dot
        self._update_stamp_dot(stamp.id)

        # 点击整个容器任意位置切换选中状态（除了删除按钮）
        def toggle_selection(e, sid=stamp.id):
            if sid in self._selected_stamp_ids:
                self._selected_stamp_ids.discard(sid)
            else:
                self._selected_stamp_ids.add(sid)
            self._update_all_dots()
            self._notify_stamp_selection_changed()

        container.bind("<Button-1>", toggle_selection)
        top_frame.bind("<Button-1>", toggle_selection)
        lbl_img.bind("<Button-1>", toggle_selection)
        name_frame.bind("<Button-1>", toggle_selection)
        lbl_name.bind("<Button-1>", toggle_selection)
        selected_dot.bind("<Button-1>", toggle_selection)

    def _update_stamp_dot(self, stamp_id: str):
        """更新单个章的选中标记"""
        if stamp_id in self._selected_dots:
            if stamp_id in self._selected_stamp_ids:
                self._selected_dots[stamp_id].config(text="●", fg="green")
            else:
                self._selected_dots[stamp_id].config(text="○", fg="gray")

    def _update_all_dots(self):
        """更新所有章的选中标记"""
        for sid in self._selected_dots:
            self._update_stamp_dot(sid)

    def _delete_stamp(self, stamp_id: str):
        """删除章"""
        if self._stamp_manager:
            self._stamp_manager.delete_stamp(stamp_id)
            self._selected_stamp_ids.discard(stamp_id)
            if self._editing_stamp_id == stamp_id:
                self._editing_stamp_id = None
            self._refresh_stamp_list()
            self._notify_stamp_selection_changed()
            self._notify_editing_stamp_changed()

    def set_editing_stamp(self, stamp_id: str):
        """设置正在编辑的章（由预览区域点击触发）"""
        self._editing_stamp_id = stamp_id
        self._update_edit_controls()
        # 不需要通知，因为这是由预览区域点击触发的，避免循环

    def _update_edit_controls(self):
        """更新编辑控制面板"""
        if not self._editing_stamp_id or not self._stamp_manager:
            self._editing_label.config(text="点击预览区域的章进行编辑", fg="gray")
            self._size_slider.config(state='disabled')
            return

        stamp = self._stamp_manager.get_stamp(self._editing_stamp_id)
        if stamp:
            self._editing_label.config(text=f"正在编辑「{stamp.name}」", fg="black")
            self._size_var.set(stamp.size_ratio * 100)
            self._size_label.config(text=f"{stamp.size_ratio * 100:.0f}%")
            self._size_slider.config(state='normal')

    def _on_size_changed(self, val):
        pct = float(val)
        self._size_label.config(text=f"{pct:.0f}%")
        if self._stamp_manager and self._editing_stamp_id:
            self._stamp_manager.update_stamp(self._editing_stamp_id, size_ratio=pct / 100.0)
            # 更新选中章的数据，通知预览刷新
            self._notify_stamp_selection_changed()

    def _notify_stamp_selection_changed(self):
        """通知待盖章的章变化"""
        if self.on_stamp_selection_changed:
            self.on_stamp_selection_changed(self.get_selected_stamps())

    def _notify_editing_stamp_changed(self):
        """通知编辑中的章变化"""
        if self.on_editing_stamp_changed:
            self.on_editing_stamp_changed(self._editing_stamp_id)

    def get_selected_stamps(self) -> List[StampSelection]:
        """获取所有待盖章的章"""
        result = []
        for stamp in self._stamps:
            if stamp.id in self._selected_stamp_ids:
                result.append(StampSelection(
                    stamp_id=stamp.id,
                    stamp_img=stamp.get_image(),
                    size_ratio=stamp.size_ratio,
                    pos_x=stamp.pos_x,
                    pos_y=stamp.pos_y
                ))
        return result

    def get_editing_stamp(self) -> Optional[StampSelection]:
        """获取正在编辑的章"""
        if not self._editing_stamp_id or not self._stamp_manager:
            return None
        stamp = self._stamp_manager.get_stamp(self._editing_stamp_id)
        if stamp:
            return StampSelection(
                stamp_id=stamp.id,
                stamp_img=stamp.get_image(),
                size_ratio=stamp.size_ratio,
                pos_x=stamp.pos_x,
                pos_y=stamp.pos_y
            )
        return None

    # === 页码管理方法 ===

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
