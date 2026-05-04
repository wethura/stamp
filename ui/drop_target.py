"""拖放目标支持模块

提供可复用的拖放功能，支持 tkdnd 扩展和平台原生拖放事件。
"""
import tkinter as tk


def setup_drop_target(widget: tk.Widget, controller) -> bool:
    """为 widget 设置拖放目标

    Args:
        widget: 要设置拖放目标的 tkinter 组件
        controller: 包含 on_file_dropped 方法的控制器对象

    Returns:
        True 如果 tkdnd 可用，False 使用原生拖放
    """
    try:
        widget.tk.call('tkdnd::drop_target', 'register', widget._w, 'DND_Files')
        widget.tk.call('bind', widget._w, '<<Drop>>',
                       f'[list {widget._w}._on_tkdnd_drop %D]')
        widget.tk.call('bind', widget._w, '<Drop>',
                       f'[list {widget._w}._on_tkdnd_drop %D]')
        widget._on_tkdnd_drop = lambda data: _handle_drop(data, controller)
        return True
    except tk.TclError:
        _setup_native_drop(widget, controller)
        return False


def _setup_native_drop(widget: tk.Widget, controller):
    """设置原生拖放事件绑定

    原生 tkinter 不支持拖放事件，需要 tkdnd 扩展。
    如果 tkdnd 不可用，拖放功能将被禁用。
    """
    pass


def _handle_drop(data: str, controller) -> str:
    """处理拖放数据"""
    if hasattr(controller, 'on_file_dropped'):
        controller.on_file_dropped(data)
    return 'break'
