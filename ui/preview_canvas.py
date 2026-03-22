import tkinter as tk
from PIL import Image, ImageTk
from typing import List, Optional, Callable


class PreviewCanvas(tk.Frame):
    def __init__(self, parent, on_stamp_position_changed=None, on_editing_stamp_changed=None, **kwargs):
        super().__init__(parent, **kwargs)
        self.on_stamp_position_changed = on_stamp_position_changed
        self.on_editing_stamp_changed = on_editing_stamp_changed

        self.canvas = tk.Canvas(self, bg="#2b2b2b", cursor="crosshair")
        self.canvas.pack(fill=tk.BOTH, expand=True)

        self._photo = None
        self._preview_size = (800, 600)
        self._offset = (0, 0)

        # 渲染参数
        self._last_page_img = None
        self._last_stamps: List = []  # 待盖章的章列表

        # 拖拽状态
        self._drag_start = None
        self._dragging_stamp_id: Optional[str] = None
        self._drag_start_pos = (0, 0)

        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.canvas.bind("<Configure>", self._on_resize)

    def update_preview(self, page_img: Image.Image, stamps: List):
        """更新预览"""
        if page_img is None:
            return
        self._last_page_img = page_img
        self._last_stamps = stamps if stamps else []
        self._render()

    def _render(self):
        page_img = self._last_page_img
        if page_img is None:
            return

        stamps = self._last_stamps
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

        # 绘制所有待盖章的章
        for stamp_sel in stamps:
            stamp_img = stamp_sel.stamp_img
            size_ratio = stamp_sel.size_ratio
            pos_x = stamp_sel.pos_x
            pos_y = stamp_sel.pos_y

            stamp_w = max(1, int(disp_w * size_ratio))
            stamp_h = max(1, int(stamp_img.height * stamp_w / stamp_img.width))
            stamp_disp = stamp_img.resize((stamp_w, stamp_h), Image.LANCZOS)

            x = int(pos_x * disp_w)
            y = int(pos_y * disp_h)
            x = min(max(0, x), disp_w - stamp_w)
            y = min(max(0, y), disp_h - stamp_h)

            page_disp.paste(stamp_disp, (x, y), mask=stamp_disp)

        offset_x = (canvas_w - disp_w) // 2
        offset_y = (canvas_h - disp_h) // 2
        self._offset = (offset_x, offset_y)

        self._photo = ImageTk.PhotoImage(page_disp.convert("RGB"))
        self.canvas.delete("all")
        self.canvas.create_image(offset_x, offset_y, anchor=tk.NW, image=self._photo)

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

    def _find_stamp_at(self, ratio_x: float, ratio_y: float) -> Optional[str]:
        """查找指定位置的章"""
        dw, dh = self._preview_size
        for stamp_sel in self._last_stamps:
            stamp_img = stamp_sel.stamp_img
            size_ratio = stamp_sel.size_ratio
            stamp_w = int(dw * size_ratio)
            stamp_h = int(stamp_img.height * stamp_w / stamp_img.width)

            x1 = stamp_sel.pos_x
            y1 = stamp_sel.pos_y
            x2 = x1 + (stamp_w / dw)
            y2 = y1 + (stamp_h / dh)

            if x1 <= ratio_x <= x2 and y1 <= ratio_y <= y2:
                return stamp_sel.stamp_id
        return None

    def _on_press(self, event):
        """鼠标按下"""
        if not self._last_stamps:
            return

        ratio_x, ratio_y = self._canvas_to_ratio(event.x, event.y)
        stamp_id = self._find_stamp_at(ratio_x, ratio_y)

        if stamp_id:
            # 设置为正在编辑的章
            if self.on_editing_stamp_changed:
                self.on_editing_stamp_changed(stamp_id)

            self._dragging_stamp_id = stamp_id
            self._drag_start = (ratio_x, ratio_y)
            # 记录该章的起始位置
            for s in self._last_stamps:
                if s.stamp_id == stamp_id:
                    self._drag_start_pos = (s.pos_x, s.pos_y)
                    break
            self.canvas.config(cursor="fleur")

    def _on_drag(self, event):
        """鼠标拖拽"""
        if self._drag_start is None or self._dragging_stamp_id is None:
            return

        ratio_x, ratio_y = self._canvas_to_ratio(event.x, event.y)
        dx = ratio_x - self._drag_start[0]
        dy = ratio_y - self._drag_start[1]

        # 计算新位置
        new_x = self._drag_start_pos[0] + dx
        new_y = self._drag_start_pos[1] + dy

        # 边界检查
        new_x = max(0, min(1, new_x))
        new_y = max(0, min(1, new_y))

        if self.on_stamp_position_changed:
            self.on_stamp_position_changed(self._dragging_stamp_id, new_x, new_y)

    def _on_release(self, event):
        """鼠标释放"""
        self._drag_start = None
        self._dragging_stamp_id = None
        self.canvas.config(cursor="crosshair")
