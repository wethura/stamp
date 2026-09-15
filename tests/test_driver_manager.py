"""转换组件（自管理 LibreOffice）管理器测试。

全部离线：本地 HTTP 服务桩提供"安装包"，注入 catalog/allowed_hosts；
解包阶段以桩替换（msiexec/hdiutil 流程由平台 CI 与真实下载验收）。
"""
import hashlib
import http.server
import json
import shutil
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from processing.word_support.driver_manager import DriverError, DriverManager
from processing.word_support.engines import SofficeEngine


class _Handler(http.server.BaseHTTPRequestHandler):
    payload = b""
    throttle_s = 0.0

    def do_GET(self):  # noqa: N802
        self.send_response(200)
        self.send_header("Content-Length", str(len(self.payload)))
        self.end_headers()
        for i in range(0, len(self.payload), 65536):
            if self.throttle_s:
                time.sleep(self.throttle_s)
            self.wfile.write(self.payload[i:i + 65536])

    def log_message(self, *a):  # 静默
        pass


class DriverTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="driver-test-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.payload = b"FAKE-INSTALLER-" + bytes(range(256)) * 64
        _Handler.payload = self.payload
        _Handler.throttle_s = 0.0
        self.httpd = http.server.HTTPServer(("127.0.0.1", 0), _Handler)
        self.port = self.httpd.server_port
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.addCleanup(self.httpd.shutdown)

        self.sha = hashlib.sha256(self.payload).hexdigest()
        self.catalog = {
            sys.platform: {
                "kind": "msi" if sys.platform == "win32" else "dmg",
                "url": f"http://127.0.0.1:{self.port}/libreoffice",
                "size_bytes": len(self.payload),
                "sha256": self.sha,
            }
        }

    def _manager(self, **catalog_over):
        entry = dict(self.catalog[sys.platform])
        entry.update(catalog_over)
        return DriverManager(base_dir=str(self.tmp / "drivers"),
                             catalog={sys.platform: entry},
                             allowed_hosts={"127.0.0.1"})

    def _stub_extract(self, manager):
        """把解包替换为：在 staging 里造出 soffice 可执行文件（并履行进度契约）。"""
        def fake_extract(info, archive, staging, progress_cb, cancel_event):
            if progress_cb:
                progress_cb("extract", 0, 0)
            sub = staging / ("program" if info["kind"] == "msi"
                             else "LibreOffice.app/Contents/MacOS")
            sub.mkdir(parents=True)
            exe = sub / ("soffice.exe" if sys.platform == "win32" else "soffice")
            exe.write_bytes(b"#!/bin/sh\n")
            if progress_cb:
                progress_cb("extract", 1, 1)
            return exe

        manager._extract = fake_extract


class TestInstallFlow(DriverTestCase):
    def test_happy_path_installs_and_marks(self):
        mgr = self._manager()
        self._stub_extract(mgr)
        progress = []
        status = mgr.install(progress_cb=lambda p, d, t: progress.append((p, d, t)))

        self.assertTrue(status["installed"])
        self.assertEqual(status["version"], mgr.catalog_info()["version"])
        self.assertTrue(Path(status["soffice"]).exists())
        self.assertEqual(status["soffice"], str(mgr.managed_soffice_path()))
        # 校验/解包阶段出现在进度回调里
        phases = {p for p, _, _ in progress}
        self.assertIn("download", phases)
        self.assertIn("verify", phases)
        self.assertIn("extract", phases)
        # 下载临时文件与 staging 均清理
        self.assertFalse((mgr.base_dir / "downloads" / "libreoffice.msi").exists()
                         or (mgr.base_dir / "downloads" / "libreoffice.dmg").exists())
        leftovers = [p for p in mgr.base_dir.rglob("lo-stage-*")]
        self.assertEqual(leftovers, [])
        # 标记文件记录了校验哈希与许可
        marker = json.loads((mgr.install_dir / "driver.json").read_text("utf-8"))
        self.assertEqual(marker["sha256"], self.sha)
        self.assertIn("MPL-2.0", marker["license"])

    def test_checksum_mismatch_aborts_and_cleans(self):
        mgr = self._manager(sha256="0" * 64)
        self._stub_extract(mgr)
        with self.assertRaises(DriverError) as ctx:
            mgr.install()
        self.assertEqual(ctx.exception.kind, "checksum")
        self.assertFalse(mgr.install_dir.exists(), "校验失败不得留下安装")
        self.assertEqual(list(mgr.base_dir.glob("downloads/*")), [],
                         "损坏的下载文件必须删除")

    def test_size_mismatch_precheck(self):
        mgr = self._manager(size_bytes=len(self.payload) + 999)
        self._stub_extract(mgr)
        with self.assertRaises(DriverError) as ctx:
            mgr.install()
        self.assertEqual(ctx.exception.kind, "checksum")

    def test_disallowed_host_rejected(self):
        entry = dict(self.catalog[sys.platform])
        entry["url"] = "http://evil.example.com/libreoffice"
        mgr = DriverManager(base_dir=str(self.tmp / "d2"),
                            catalog={sys.platform: entry},
                            allowed_hosts={"127.0.0.1"})
        with self.assertRaises(DriverError) as ctx:
            mgr.install()
        self.assertEqual(ctx.exception.kind, "network")

    def test_https_enforced(self):
        entry = dict(self.catalog[sys.platform])
        entry["url"] = "http://download.documentfoundation.org/x"
        mgr = DriverManager(base_dir=str(self.tmp / "d3"),
                            catalog={sys.platform: entry},
                            allowed_hosts={"download.documentfoundation.org"})
        with self.assertRaises(DriverError) as ctx:
            mgr.install()
        self.assertEqual(ctx.exception.kind, "network")

    def test_cancel_mid_download(self):
        _Handler.throttle_s = 0.02
        mgr = self._manager()
        self._stub_extract(mgr)
        cancel = threading.Event()

        def cb(phase, done, total):
            if done > len(self.payload) // 3:
                cancel.set()

        with self.assertRaises(DriverError) as ctx:
            mgr.install(progress_cb=cb, cancel_event=cancel)
        self.assertEqual(ctx.exception.kind, "cancelled")
        self.assertFalse(mgr.install_dir.exists(), "取消不得留下半成品")

    def test_disk_space_guard(self):
        mgr = self._manager()
        self._stub_extract(mgr)
        with mock.patch("processing.word_support.driver_manager."
                        "shutil.disk_usage") as du:
            du.return_value = mock.Mock(free=len(self.payload))  # 远小于 2×
            with self.assertRaises(DriverError) as ctx:
                mgr.install()
        self.assertEqual(ctx.exception.kind, "disk")

    def test_uninstall_removes_everything(self):
        mgr = self._manager()
        self._stub_extract(mgr)
        mgr.install()
        self.assertTrue(mgr.status()["installed"])
        mgr.uninstall()
        self.assertFalse(mgr.status()["installed"])
        self.assertFalse(mgr.install_dir.exists())


class TestStatusAndEngineIntegration(DriverTestCase):
    def test_marker_with_stale_path_falls_back_to_layout_search(self):
        mgr = self._manager()
        sub = mgr.install_dir / ("program" if sys.platform == "win32"
                                 else "LibreOffice.app/Contents/MacOS")
        sub.mkdir(parents=True)
        exe = sub / ("soffice.exe" if sys.platform == "win32" else "soffice")
        exe.write_bytes(b"x")
        mgr._marker.parent.mkdir(parents=True, exist_ok=True)
        mgr._marker.write_text(json.dumps({
            "kind": "libreoffice", "version": "test",
            "soffice": "/gone/soffice"}), encoding="utf-8")
        self.assertEqual(mgr.managed_soffice_path(), exe)

    def test_engine_prefers_managed_driver_over_system(self):
        mgr = self._manager()
        sub = mgr.install_dir / ("program" if sys.platform == "win32"
                                 else "LibreOffice.app/Contents/MacOS")
        sub.mkdir(parents=True)
        exe = sub / ("soffice.exe" if sys.platform == "win32" else "soffice")
        exe.write_bytes(b"x")
        (mgr.install_dir / "driver.json").write_text(json.dumps(
            {"kind": "libreoffice", "version": "t",
             "soffice": str(exe)}), encoding="utf-8")

        engine = SofficeEngine(driver_manager=mgr)
        found = engine._find_bin()
        self.assertEqual(found, exe)

        probe = engine.probe()
        self.assertTrue(probe.available)
        self.assertIn("内置下载", probe.detail)

    def test_engine_env_override_wins(self):
        mgr = self._manager()
        fake = self.tmp / "custom-soffice"
        fake.write_bytes(b"x")
        engine = SofficeEngine(driver_manager=mgr)
        with mock.patch.dict("os.environ", {"STAMPTOOL_SOFFICE": str(fake)}):
            self.assertEqual(engine._find_bin(), fake)

    def test_platform_supported_matches_catalog(self):
        mgr = self._manager()
        self.assertTrue(mgr.platform_supported())
        empty = DriverManager(base_dir=str(self.tmp / "d9"), catalog={})
        self.assertFalse(empty.platform_supported())
        self.assertEqual(empty.catalog_info(), {})


if __name__ == "__main__":
    unittest.main()
