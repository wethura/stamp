"""设置对话框的引擎展示行构造测试（纯函数 + 下载按钮回调 GUI 回归）。"""
import unittest
from unittest.mock import MagicMock, patch

from processing.word_support.engines import EngineInfo
from ui.settings_dialog import AUTO_OPTION, _auto_status, build_engine_rows


def info(engine_id, name, available=True, version="", manual=False):
    return EngineInfo(engine_id, name, available, version=version,
                      detail="", manual_path_only=manual)


class TestBuildEngineRows(unittest.TestCase):
    def test_all_installed_typical_mac(self):
        rows = build_engine_rows([
            info("soffice", "LibreOffice", version="LibreOffice 26.2.5.2 abc"),
            info("word-jxa", "Microsoft Word", version="16.112.4"),
            info("wps", "WPS Office", version="12.1.28492", manual=True),
        ])
        by_id = {row[0].engine_id: row for row in rows}
        self.assertTrue(by_id["soffice"][1])
        self.assertEqual(by_id["soffice"][2], "已安装 · 26.2.5.2")
        self.assertTrue(by_id["word-jxa"][1])
        self.assertEqual(by_id["word-jxa"][2], "已安装 · 16.112.4")
        # WPS：已安装但仅手动路径 → 不可选，状态说明手动出口
        self.assertFalse(by_id["wps"][1])
        self.assertIn("暂不支持自动转换", by_id["wps"][2])
        self.assertIn("已安装", by_id["wps"][2])

    def test_missing_engine_sorted_last_and_unselectable(self):
        rows = build_engine_rows([
            info("word-jxa", "Microsoft Word", available=False),
            info("soffice", "LibreOffice"),
        ])
        self.assertEqual(rows[-1][0].engine_id, "word-jxa")
        self.assertFalse(rows[-1][1])
        self.assertEqual(rows[-1][2], "未安装")
        self.assertTrue(rows[0][1])

    def test_version_without_tokens_falls_back(self):
        rows = build_engine_rows([info("soffice", "LibreOffice", version="")])
        self.assertEqual(rows[0][2], "已安装")

    def test_auto_status_lists_usable_engines_in_order(self):
        rows = build_engine_rows([
            info("word-jxa", "Microsoft Word"),
            info("soffice", "LibreOffice"),
            info("wps", "WPS Office", manual=True),
        ])
        status = _auto_status(rows)
        self.assertIn("LibreOffice", status)
        self.assertIn("Microsoft Word", status)
        self.assertNotIn("WPS", status)
        self.assertEqual(AUTO_OPTION, "auto")


class TestDriverActionCallback(unittest.TestCase):
    """回归（2026-09-18 用户实机）：下载成功后 run_driver_install 以
    on_done(True) 回调，设置页的 refresh() 闭包不收参数 → TypeError。
    需要显示环境；无显示跳过。共享单例根，不自建（Windows 多 CTk
    根会原生崩溃，见 tests/gui_support.py）。
    """

    @staticmethod
    def _find_button(widget, needle: str):
        for child in widget.winfo_children():
            try:
                text = str(child.cget("text"))
            except Exception:  # noqa: BLE001
                text = ""
            if needle in text:
                return child
            found = TestDriverActionCallback._find_button(child, needle)
            if found is not None:
                return found
        return None

    def test_download_on_done_receives_installed_flag(self):
        from tests.gui_support import shared_ctk_root
        shared_ctk_root()  # 无显示环境 → SkipTest

        service = MagicMock()
        service.probe_all.return_value = {
            "soffice": EngineInfo("soffice", "LibreOffice (无界面)",
                                  available=False),
        }
        service.current_preference.return_value = None

        driver_cls = MagicMock()
        driver_cls.return_value.status.return_value = {"installed": False}
        driver_cls.return_value.catalog_info.return_value = {
            "version": "26.2.6", "kind": "msi", "size_bytes": 1,
            "size_mb": 1, "url": "https://download.documentfoundation.org/x",
        }
        results = {}

        def fake_run(parent, on_done=None):
            results["parent_ok"] = parent is not None
            on_done(True)  # 契约：installed 以一个位置参数回传

        with patch("processing.word_support.driver_manager.DriverManager",
                   driver_cls), \
             patch("ui.driver_dialogs.run_driver_install", fake_run):
            from ui.settings_dialog import SettingsDialog
            dialog = SettingsDialog(shared_ctk_root(), service)
            try:
                button = self._find_button(dialog, "下载组件")
                self.assertIsNotNone(button, "未安装时应显示「下载组件」按钮")
                button.invoke()
                # 走到这里说明 on_done(True) 未抛 TypeError 且行已重建
                self.assertTrue(results.get("parent_ok"))
                self.assertGreaterEqual(
                    service.probe_all.call_count, 2,
                    "安装完成后应重新探测引擎")
            finally:
                try:
                    dialog.destroy()
                except Exception:  # noqa: BLE001
                    pass


if __name__ == "__main__":
    unittest.main()
