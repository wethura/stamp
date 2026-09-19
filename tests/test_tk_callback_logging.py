"""Tk 回调异常弹窗去重测试。

回归背景：Windows 上滚轮等高频回调每格触发一次异常，旧实现每次都弹
模态错误框，连环弹窗让应用完全无法操作（v0.1.8 + customtkinter 6.0.0
实况）。同一异常只应打扰用户一次，后续仍落日志。
"""
import tkinter as tk
import unittest
from unittest.mock import patch

from main import _install_tk_callback_logging


class TestCallbackDialogDedupe(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        _install_tk_callback_logging(self.root)
        self.report = self.root.report_callback_exception

    def tearDown(self):
        self.root.destroy()

    def test_same_error_shows_dialog_once(self):
        exc = ValueError("boom")
        with patch("tkinter.messagebox.showerror") as dlg:
            self.report(ValueError, exc, None)
            self.report(ValueError, exc, None)
            self.report(ValueError, exc, None)
            self.assertEqual(dlg.call_count, 1)

    def test_different_error_shows_dialog_again(self):
        with patch("tkinter.messagebox.showerror") as dlg:
            self.report(ValueError, "boom", None)
            self.report(KeyError, "other", None)
            self.assertEqual(dlg.call_count, 2)


if __name__ == "__main__":
    unittest.main()
