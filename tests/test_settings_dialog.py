"""设置对话框的引擎展示行构造测试（纯函数，无 GUI）。"""
import unittest

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


if __name__ == "__main__":
    unittest.main()
