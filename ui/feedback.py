"""轻量反馈组件：Tooltip 悬停提示 + Toast 非阻塞通知。

设计约定（墨韵）：
- Tooltip 是安静的一行小字：浅底、1px 边、不抢焦点；悬停约半秒出现，
  移开即消失，按钮销毁时自动清理。
- Toast 只用于「结果告知」（导出成功、组件就绪等），不打断操作流：
  出现在主窗口右下角、可堆叠、悬停停留、可带一个文字动作按钮。
  错误仍走 messagebox —— 需要用户正视的信息不该被自动收走。
"""

import tkinter as tk
import weakref
from typing import Callable, Optional

import customtkinter as ctk

from ui.icons import get_icon
from ui.theme import Buttons, Colors, Fonts

_TOOLTIP_DELAY_MS = 450
_TOOLTIP_HIDE_GRACE_MS = 150
_TOOLTIP_WRAP = 300


class Tooltip:
    """给任意控件挂悬停提示；CTk 复合控件内部的子标签也会被绑上。

    实现纪律（macOS 实测 2026-09-19，两次线上症状同根）：
    - 不创建 Toplevel：aqua 的 override 窗口不归窗口管理器管，映射时
      不会自动取内容尺寸（表现为 200×200pt 黑色方块），且置顶 override
      窗盖住指针时系统会持续合成 Enter/Leave，陷入「显示→盖住指针→
      隐藏→再显示」的无限建窗循环，CPU 打满、界面假死。因此提示是
      宿主窗口内部的子 Frame（place 定位），从根上绕开这两类问题。
    - 落点不得覆盖指针，避免遮住刚悬停的控件本身。
    - 绑定用 WeakSet 去重：否则每次 _enter 都 add="+" 累积脚本，
      回调随悬停次数线性增长，越用越卡。
    """

    def __init__(self, widget, text: str, delay: int = _TOOLTIP_DELAY_MS):
        self._widget = widget
        self._text = text
        self._delay = delay
        self._tip: Optional[tk.Frame] = None
        self._label: Optional[tk.Label] = None
        self._show_id = None
        self._hide_id = None
        # 已绑定的控件（弱引用）：控件销毁自动出列；路径复用的新控件
        # 是新对象，仍会被绑上
        self._bound = weakref.WeakSet()

        self._bind_tree(widget)
        widget.bind("<Destroy>", self._on_widget_destroy, add="+")

    def set_text(self, text: str):
        """更新提示文案（如按钮禁用原因随状态变化）。"""
        self._text = text
        if self._label is not None and self._tip is not None:
            self._label.configure(text=text)

    # ── 事件 ──────────────────────────────────────────────────────

    def _bind_tree(self, root):
        """Enter/Leave 绑到整棵子树：CTkButton 的文本/图片标签是
        后创建的子控件，只绑按钮本身会漏掉标签上的悬停。"""
        for w in [root, *self._walk(root)]:
            if w in self._bound:
                continue
            self._bound.add(w)
            w.bind("<Enter>", self._enter, add="+")
            w.bind("<Leave>", self._leave, add="+")

    @staticmethod
    def _walk(w):
        out = []
        for child in w.winfo_children():
            out.append(child)
            out.extend(Tooltip._walk(child))
        return out

    def _enter(self, _event=None):
        self._cancel_hide()
        # 补绑后来才出现的子控件（WeakSet 去重，绑定不累积）
        self._bind_tree(self._widget)
        if self._show_id is None and self._tip is None:
            self._show_id = self._widget.after(self._delay, self._show)

    def _leave(self, _event=None):
        self._cancel_show()
        if self._hide_id is None and self._tip is not None:
            self._hide_id = self._widget.after(_TOOLTIP_HIDE_GRACE_MS,
                                               self._hide)

    def _on_widget_destroy(self, event):
        if event.widget is self._widget:
            self._cancel_show()
            self._cancel_hide()
            self._hide()

    # ── 显示/隐藏 ─────────────────────────────────────────────────

    def _show(self):
        self._show_id = None
        if self._tip is not None or not self._text:
            return
        w = self._widget
        host = w.winfo_toplevel()

        # 外层 Frame 当 1px 描边，内层 Label 承载文案
        tip = tk.Frame(host, bg=Colors.BORDER_SUBTLE,
                       highlightthickness=0, borderwidth=0)
        self._label = tk.Label(
            tip, text=self._text, justify="left",
            bg=Colors.SURFACE_BASE, fg=Colors.TEXT_PRIMARY,
            font=(Fonts.FAMILY, Fonts.SMALL_SIZE),
            padx=10, pady=5, wraplength=_TOOLTIP_WRAP,
        )
        self._label.pack(padx=1, pady=1)
        self._tip = tip

        tip.update_idletasks()
        tw, th = tip.winfo_reqwidth(), tip.winfo_reqheight()
        # 宿主窗口内部坐标系（place 以宿主为基准）
        in_x = w.winfo_rootx() - host.winfo_rootx()
        in_y = w.winfo_rooty() - host.winfo_rooty()
        x = in_x + (w.winfo_width() - tw) // 2
        y = in_y + w.winfo_height() + 7
        if y + th > host.winfo_height() - 4:
            y = in_y - th - 7
        x = max(4, min(x, host.winfo_width() - tw - 4))

        # 落点不得覆盖指针（指针相对宿主窗口的坐标；-1 表示不在本屏）
        px = w.winfo_pointerx() - host.winfo_rootx()
        py = w.winfo_pointery() - host.winfo_rooty()
        if px >= 0 and py >= 0 and x <= px < x + tw and y <= py < y + th:
            if px + 16 + tw <= host.winfo_width() - 4:
                x = px + 16
            else:
                x = max(4, px - tw - 16)

        tip.place(x=x, y=y, anchor="nw")
        tip.lift()

    def _hide(self):
        self._cancel_hide()
        if self._tip is not None:
            try:
                self._tip.destroy()
            except tk.TclError:
                pass
            self._tip = None
            self._label = None

    def _cancel_show(self):
        if self._show_id is not None:
            try:
                self._widget.after_cancel(self._show_id)
            except tk.TclError:
                pass
            self._show_id = None

    def _cancel_hide(self):
        if self._hide_id is not None:
            try:
                self._widget.after_cancel(self._hide_id)
            except tk.TclError:
                pass
            self._hide_id = None


# ── Toast ─────────────────────────────────────────────────────────────

_KIND_STYLE = {
    "success": ("check-circle", lambda: Colors.SUCCESS),
    "error": ("alert-circle", lambda: Colors.DANGER),
    "info": ("info-circle", lambda: Colors.PRIMARY),
}

_TOAST_MARGIN_X = 24
_TOAST_BOTTOM_MARGIN = 48     # 避开状态栏
_TOAST_GAP = 10


class _ToastCard(ctk.CTkFrame):
    """单条通知卡片：图标 + 文案 +（可选）动作按钮 + 关闭。"""

    def __init__(self, master, message: str, kind: str,
                 action_text: Optional[str], on_action: Optional[Callable],
                 on_dismiss: Callable):
        super().__init__(master, corner_radius=10,
                         fg_color=Colors.SURFACE_BASE,
                         border_width=1, border_color=Colors.BORDER_SUBTLE)
        self._on_action = on_action
        self._on_dismiss = on_dismiss
        self._dismiss_id = None

        icon_name, color_fn = _KIND_STYLE[kind]
        ctk.CTkLabel(self, text="", image=get_icon(icon_name, 18, color_fn())
                     ).pack(side="left", padx=(12, 8), pady=12)
        ctk.CTkLabel(
            self, text=message, justify="left", wraplength=320,
            font=(Fonts.FAMILY, Fonts.BODY_SIZE),
            text_color=Colors.TEXT_PRIMARY,
        ).pack(side="left", padx=(0, 6))
        if action_text:
            ctk.CTkButton(
                self, text=action_text, height=26,
                corner_radius=Buttons.RADIUS_SM, fg_color="transparent",
                hover_color=Colors.SURFACE_RAISED, text_color=Colors.PRIMARY,
                font=(Fonts.FAMILY, Fonts.SMALL_SIZE),
                command=self._run_action,
            ).pack(side="left", padx=(2, 2))
        close = ctk.CTkLabel(
            self, text="", image=get_icon("x", 12, Colors.TEXT_TERTIARY),
            cursor="hand2",
        )
        close.pack(side="left", padx=(6, 10))
        close.bind("<Button-1>", lambda e: self.dismiss())

        # 悬停停留：移开后再给一小段存续时间
        self.bind("<Enter>", lambda e: self._cancel_dismiss(), add="+")
        self.bind("<Leave>", lambda e: self._schedule_dismiss(1600), add="+")

    def _run_action(self):
        if self._on_action is not None:
            try:
                self._on_action()
            except Exception:  # noqa: BLE001  动作失败不该留下悬死的通知
                import logging
                logging.getLogger(__name__).exception("Toast 动作执行失败")
        self.dismiss()

    def _schedule_dismiss(self, ms: int):
        self._cancel_dismiss()
        self._dismiss_id = self.after(ms, self.dismiss)

    def _cancel_dismiss(self):
        if self._dismiss_id is not None:
            try:
                self.after_cancel(self._dismiss_id)
            except tk.TclError:
                pass
            self._dismiss_id = None

    def dismiss(self):
        self._cancel_dismiss()
        try:
            self.destroy()
        except tk.TclError:
            pass
        self._on_dismiss(self)


class ToastManager:
    """在主窗口右下角堆叠通知；新通知靠底，旧通知上移。"""

    def __init__(self):
        self._stack = []

    def show(self, parent, message: str, kind: str = "success",
             action_text: Optional[str] = None,
             on_action: Optional[Callable] = None,
             duration_ms: int = 4200):
        card = _ToastCard(parent, message, kind, action_text, on_action,
                          on_dismiss=self._remove)
        self._stack.append(card)
        card.update_idletasks()
        self._relayout()
        card._schedule_dismiss(duration_ms)
        return card

    def _remove(self, card):
        if card in self._stack:
            self._stack.remove(card)
        self._relayout()

    def _relayout(self):
        offset = _TOAST_BOTTOM_MARGIN
        for card in reversed(self._stack):
            try:
                height = card.winfo_reqheight()
            except tk.TclError:
                continue
            card.place(rely=1.0, relx=1.0, anchor="se",
                       x=-_TOAST_MARGIN_X, y=-offset)
            offset += height + _TOAST_GAP

    @property
    def active_count(self) -> int:
        return len(self._stack)


def show_toast(parent, message: str, kind: str = "success",
               action_text: Optional[str] = None,
               on_action: Optional[Callable] = None,
               duration_ms: int = 4200) -> _ToastCard:
    """在 parent 所在主窗口右下角弹出非阻塞通知（仅主线程调用）。"""
    root = parent.winfo_toplevel()
    manager = getattr(root, "_toast_manager", None)
    if manager is None:
        manager = ToastManager()
        root._toast_manager = manager
    return manager.show(parent, message, kind, action_text, on_action,
                        duration_ms)
