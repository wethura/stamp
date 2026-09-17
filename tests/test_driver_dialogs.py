"""下载组件对话框的构造/交互回归（需要显示环境；无显示整类跳过）。

守护 v0.1.8 的崩溃回归：DriverProgressDialog 构造时引用了不存在的
_on_cancel，进度窗口一打开就 AttributeError，下载从未真正开始。
"""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tests.gui_support import shared_ctk_root
from ui.driver_dialogs import DriverConfirmDialog, DriverProgressDialog

INFO = {
    "version": "26.2.6",
    "kind": "msi",
    "size_bytes": 2048,
    "size_mb": 2,
    "url": "https://download.documentfoundation.org/x.msi",
}


class TestDriverDialogs(unittest.TestCase):
    # 共享单例根：Windows 上同进程第 5 个 CTk 根会原生崩溃，
    # 不得在本文件自建根窗口（tests/gui_support.py）
    def _safe_destroy(self, dialog):
        try:
            if dialog.winfo_exists():
                dialog.destroy()
        except Exception:  # noqa: BLE001
            pass

    # ── 进度窗口 ─────────────────────────────────────────────────────

    def test_progress_dialog_constructs_updates_and_cancels(self):
        # 回归：构造即崩（AttributeError: _on_cancel）
        cancel_calls = []
        dialog = DriverProgressDialog(shared_ctk_root(), 2048,
                                      on_cancel=lambda: cancel_calls.append(True))
        try:
            self.assertTrue(dialog.winfo_exists())
            self.assertFalse(dialog.cancelled)
            dialog.update_progress("download", 1024, 2048)
            self.assertIn("50%", dialog._detail.cget("text"))
            dialog.update_progress("verify", 0, 1)
            dialog.update_progress("extract", 0, 0)
            self.assertIn("解包", dialog._label.cget("text"))
            # 点取消：置位标志并触发回调（工作线程据此停止下载）
            dialog._cancel.invoke()
            self.assertTrue(dialog.cancelled)
            self.assertEqual(len(cancel_calls), 1)
        finally:
            self._safe_destroy(dialog)

    # ── 确认窗口（含安装位置选择） ────────────────────────────────────

    def test_confirm_defaults_to_default_dir_and_ok(self):
        with tempfile.TemporaryDirectory() as td:
            default_dir = str(Path(td) / "libreoffice")
            dialog = DriverConfirmDialog(shared_ctk_root(), INFO, default_dir)
            try:
                self.assertEqual(dialog._path.get(), default_dir)
                dialog._ok()
                self.assertTrue(dialog.confirmed)
                self.assertEqual(dialog.target_dir, default_dir)
            finally:
                self._safe_destroy(dialog)

    def test_confirm_accepts_custom_empty_dir(self):
        with tempfile.TemporaryDirectory() as td:
            custom = Path(td) / "D盘目录"
            custom.mkdir()
            dialog = DriverConfirmDialog(shared_ctk_root(), INFO, default_dir=td)
            try:
                dialog._path.delete(0, "end")
                dialog._path.insert(0, str(custom))
                dialog._ok()
                self.assertTrue(dialog.confirmed)
                self.assertEqual(dialog.target_dir, str(custom))
            finally:
                self._safe_destroy(dialog)

    def test_confirm_rejects_non_empty_dir_and_stays_open(self):
        with tempfile.TemporaryDirectory() as td:
            busy = Path(td) / "busy"
            busy.mkdir()
            (busy / "用户文件.txt").write_text("x", encoding="utf-8")
            dialog = DriverConfirmDialog(shared_ctk_root(), INFO, default_dir=td)
            try:
                dialog._path.delete(0, "end")
                dialog._path.insert(0, str(busy))
                with patch("ui.driver_dialogs.messagebox.showwarning") as warn:
                    dialog._ok()
                warn.assert_called_once()
                self.assertFalse(dialog.confirmed)
                self.assertTrue(dialog.winfo_exists(), "拒绝时保持打开等修改")
            finally:
                self._safe_destroy(dialog)

    def test_confirm_rejects_relative_and_empty_path(self):
        dialog = DriverConfirmDialog(shared_ctk_root(), INFO,
                                    default_dir="/nowhere/lo")
        try:
            for bad in ("", "relative/path"):
                dialog._path.delete(0, "end")
                if bad:
                    dialog._path.insert(0, bad)
                with patch("ui.driver_dialogs.messagebox.showwarning") as warn:
                    dialog._ok()
                warn.assert_called_once()
                self.assertFalse(dialog.confirmed)
                self.assertTrue(dialog.winfo_exists())
        finally:
            self._safe_destroy(dialog)

    def test_confirm_cancel_yields_not_confirmed(self):
        dialog = DriverConfirmDialog(shared_ctk_root(), INFO,
                                    default_dir="/nowhere/lo")
        dialog._cancel()
        self.assertFalse(dialog.confirmed)


if __name__ == "__main__":
    unittest.main()
