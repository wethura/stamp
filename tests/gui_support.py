"""GUI 测试的共享基础设施。

Windows 上同进程内反复创建/销毁 CTk 根窗口会触发原生崩溃
（2026-09-18 实测：全套件顺序创建的第 5 个 CTk 根使 CI 直接
退出、无任何 FAIL/ERROR 输出，崩点落在无关的后续测试里）。
轻量对话框测试一律复用本模块的惰性单例根；test_gui_smoke /
test_gui_word_flow 需要独占根（且其 PhotoImage 隐式绑定
tkinter._default_root），它们自建根时须显式接管默认根身份，
销毁后本模块的共享根会自动补位为默认根。全套件顺序创建的
CTk 根数保持 3（经验证安全）。根窗口屏幕外映射、进程退出时
随解释器回收。
"""
import unittest

_root = None


def shared_ctk_root():
    """进程内唯一的共享 CTk 根；无显示环境抛 SkipTest。

    CTkFont()/StringVar() 等无 master 的控件会隐式使用
    tkinter._default_root——共享根在没有别的根持有默认身份时
    自动补位，保证对话框测试可构造控件。
    """
    global _root
    if _root is None:
        try:
            import tkinter as tk

            import customtkinter as ctk
            _root = ctk.CTk()
            # 映射到屏幕外：winfo 尺寸/渲染依赖真实映射，又不闪屏打扰
            _root.geometry("600x400+4000+4000")
            _root.update()
        except Exception:
            _root = None
            raise unittest.SkipTest("无可用显示环境")
    import tkinter as tk
    if tk._default_root is None:
        tk._default_root = _root
    return _root
