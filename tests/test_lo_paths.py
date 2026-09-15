"""LibreOffice 位置解析与引擎优先级测试（探测遗漏 → 手动指定的防线）。

背景：用户机器装有 LibreOffice（每用户安装于 %LOCALAPPDATA%\\Programs），
自动探测曾漏报为「无引擎」。因此：
1. 候选路径必须覆盖每用户安装位置
2. 探测不是真理——用户可手动指定目录，优先级高于一切自动探测
3. 指定目录时宽容解析（安装根/program 目录/.app/父目录/可执行文件）
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from processing.word_support import paths as lo_paths
from processing.word_support.engines import EngineInfo, SofficeEngine
from processing.word_support.service import ConversionService


def make_soffice(dirpath: Path) -> Path:
    """在给定布局下造出 soffice 并返回其路径。"""
    exe = dirpath / ("soffice.exe" if sys.platform == "win32" else "soffice")
    exe.parent.mkdir(parents=True, exist_ok=True)
    exe.write_bytes(b"stub")
    return exe


class TempStoreCase(unittest.TestCase):
    """把手动指定的持久化重定向到临时目录，互不污染。"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="lo-paths-"))
        self.addCleanup(lambda: __import__("shutil").rmtree(self.tmp,
                                                            ignore_errors=True))
        patcher = mock.patch.object(lo_paths, "_store_path",
                                    return_value=self.tmp / "soffice_path.json")
        self.store = patcher.start()
        self.addCleanup(patcher.stop)


class TestValidateTarget(TempStoreCase):
    def setUp(self):
        super().setUp()
        self.root = self.tmp / "layout"

    @unittest.skipIf(sys.platform == "win32", "win 布局由 Windows runner 覆盖")
    def test_windows_install_root_layout(self):
        root = self.root / "win-root"
        exe = make_soffice(root / "program")
        self.assertEqual(lo_paths.validate_soffice_target(root), exe)

    @unittest.skipIf(sys.platform == "win32", "win 布局由 Windows runner 覆盖")
    def test_program_dir_selected_directly(self):
        root = self.root / "win-progdir"
        exe = make_soffice(root)
        self.assertEqual(lo_paths.validate_soffice_target(root), exe)

    @unittest.skipIf(sys.platform != "darwin", "mac 布局由 macOS runner 覆盖")
    def test_mac_app_bundle_layout(self):
        app = self.root / "LibreOffice.app"
        exe = make_soffice(app / "Contents" / "MacOS")
        self.assertEqual(lo_paths.validate_soffice_target(app), exe)

    def test_executable_file_selected_directly(self):
        exe = make_soffice(self.root / "direct")
        self.assertEqual(lo_paths.validate_soffice_target(exe), exe)

    def test_parent_directory_shallow_search(self):
        exe = make_soffice(self.root / "apps" / "LibreOffice" / "program")
        self.assertEqual(lo_paths.validate_soffice_target(self.root / "apps"), exe)

    def test_random_directory_rejected(self):
        (self.root / "empty").mkdir(parents=True)
        self.assertIsNone(lo_paths.validate_soffice_target(self.root / "empty"))

    def test_wrong_executable_rejected(self):
        d = self.root / "notlo"
        d.mkdir(parents=True)
        (d / "some.exe").write_bytes(b"x")
        self.assertIsNone(lo_paths.validate_soffice_target(d / "some.exe"))


class TestManualPersistence(TempStoreCase):
    def test_set_get_clear_roundtrip(self):
        exe = make_soffice(self.tmp / "install" / "program")
        root = self.tmp / "install"
        resolved = lo_paths.set_manual_soffice(root)
        self.assertEqual(resolved, exe)
        self.assertEqual(lo_paths.get_manual_soffice(), exe)
        lo_paths.clear_manual_soffice()
        self.assertIsNone(lo_paths.get_manual_soffice())

    def test_invalid_set_returns_none_and_stores_nothing(self):
        bad = self.tmp / "nowhere"
        bad.mkdir()
        self.assertIsNone(lo_paths.set_manual_soffice(bad))
        self.assertIsNone(lo_paths.get_manual_soffice())

    def test_stale_store_ignored(self):
        self.store().parent.mkdir(parents=True, exist_ok=True)
        self.store().write_text(json.dumps({"soffice": "/gone/soffice"}),
                                encoding="utf-8")
        self.assertIsNone(lo_paths.get_manual_soffice())


class TestCandidates(unittest.TestCase):
    def test_windows_includes_per_user_location(self):
        localappdata = "/Users/x/AppData/Local"
        with mock.patch.dict("os.environ",
                             {"LOCALAPPDATA": localappdata},
                             clear=False), \
                mock.patch.object(sys, "platform", "win32"), \
                mock.patch.object(lo_paths, "_windows_registry_roots",
                                  return_value=[]):
            cands = lo_paths.candidate_paths()
        expected = (Path(localappdata) / "Programs" / "LibreOffice"
                    / "program" / "soffice.exe")
        self.assertIn(expected, cands,
                      "每用户安装是默认形态之一，不得遗漏")

    def test_windows_includes_registry_roots(self):
        root = Path("D:/Custom/LibreOffice")
        with mock.patch.object(sys, "platform", "win32"), \
                mock.patch.object(lo_paths, "_windows_registry_roots",
                                  return_value=[root]), \
                mock.patch.dict("os.environ", {"LOCALAPPDATA": "/x"},
                                clear=False):
            cands = lo_paths.candidate_paths()
        self.assertIn(root / "program" / "soffice.exe", cands,
                      "注册表 InstallLocation 覆盖自定义安装盘")

    def test_darwin_candidates_include_home_applications(self):
        with mock.patch.object(sys, "platform", "darwin"):
            cands = lo_paths.candidate_paths()
        self.assertTrue(any(p == (Path.home() / "Applications" /
                                  "LibreOffice.app/Contents/MacOS/soffice")
                            for p in cands))


class TestEnginePriority(TempStoreCase):
    def _engine(self, with_driver=False):
        from processing.word_support.driver_manager import DriverManager
        driver_mgr = DriverManager(base_dir=str(self.tmp / "drivers"))
        if with_driver:
            sub = driver_mgr.install_dir / (
                "program" if sys.platform == "win32"
                else "LibreOffice.app/Contents/MacOS")
            sub.mkdir(parents=True, exist_ok=True)
            exe = sub / ("soffice.exe" if sys.platform == "win32" else "soffice")
            exe.write_bytes(b"x")
            driver_mgr._marker.parent.mkdir(parents=True, exist_ok=True)
            driver_mgr._marker.write_text(json.dumps(
                {"kind": "libreoffice", "version": "t",
                 "soffice": str(exe)}), encoding="utf-8")
        return SofficeEngine(driver_manager=driver_mgr)

    def test_manual_overrides_system_and_driver(self):
        system_exe = make_soffice(Path("/tmp/fake-system-libo") if False
                                  else self.tmp / "system" / "program")
        manual_exe = make_soffice(self.tmp / "manual" / "program")
        lo_paths.set_manual_soffice(self.tmp / "manual")
        engine = self._engine(with_driver=True)
        with mock.patch.object(lo_paths, "candidate_paths",
                               return_value=[system_exe]):
            found = engine._find_bin()
        self.assertEqual(found, manual_exe)
        self.assertEqual(engine._source, "手动指定")

    def test_env_override_beats_manual(self):
        make_soffice(self.tmp / "manual" / "program")
        lo_paths.set_manual_soffice(self.tmp / "manual")
        env_exe = make_soffice(self.tmp / "env" / "program")
        engine = self._engine()
        with mock.patch.dict("os.environ", {"STAMPTOOL_SOFFICE": str(env_exe)}):
            self.assertEqual(engine._find_bin(), env_exe)
            self.assertEqual(engine._source, "环境覆盖")

    def test_driver_used_when_no_manual(self):
        engine = self._engine(with_driver=True)
        found = engine._find_bin()
        self.assertEqual(engine._source, "内置下载")
        self.assertTrue(found.is_file())

    def test_detection_scan_logged_when_not_found(self):
        engine = self._engine()
        with mock.patch.object(lo_paths, "candidate_paths",
                               return_value=[Path("/nope/soffice"),
                                             Path("/nada/soffice.exe")]), \
                mock.patch("shutil.which", return_value=None), \
                mock.patch.object(lo_paths, "log_detection_scan",
                                  wraps=lo_paths.log_detection_scan) as scan:
            self.assertIsNone(engine._find_bin())
        scan.assert_called_once()
        args = scan.call_args[0]
        self.assertEqual(args[2], "自动探测")
        self.assertIsNone(args[1])

    def test_detection_scan_emits_log_records(self):
        with self.assertLogs("processing.word_support.paths", level="INFO") as logs:
            lo_paths.log_detection_scan([Path("/nope/soffice")], None,
                                        "unit")
        joined = "\n".join(logs.output).replace("\\", "/")
        self.assertIn("/nope/soffice", joined, "扫描路径必须落日志")
        self.assertIn("未命中", joined)


if __name__ == "__main__":
    unittest.main()
