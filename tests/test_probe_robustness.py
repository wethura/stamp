"""探测健壮性与启动性能测试。

用户报告（Windows 打包版）：打开 Word 文档时「检查转换能力很慢」并闪退。
根因：探测同步跑在 UI 线程（soffice --version 可阻塞数十秒），且
`import winreg` 在 try 之外——打包版缺失该模块时 ImportError 逃逸，
无控制台窗口的 exe 直接闪退，用户看不到任何原因。

这里锁住三点：探测绝不外抛、单个引擎失败不影响他人、启动不触发探测。
"""
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

from processing.word_support.engines import (
    ComEngineBase,
    SofficeEngine,
    WordComEngine,
    WpsComEngine,
    WpsManualEngine,
)
from processing.word_support.service import ConversionService, get_shared_service
from processing.word_support.engines import EngineInfo


class ExplodingEngine:
    """probe 无论如何都抛异常的引擎（模拟缺模块 / 注册表异常）。"""

    engine_id = "exploding"
    NAME = "Exploding"

    def probe(self):
        raise ImportError("simulated missing winreg")

    def convert(self, *a, **k):  # pragma: no cover
        raise AssertionError("not used")


class HealthyEngine:
    engine_id = "healthy"
    NAME = "Healthy"

    def probe(self):
        return EngineInfo("healthy", "Healthy", True, version="1.0")

    def convert(self, *a, **k):  # pragma: no cover
        raise AssertionError("not used")


class TestProbeNeverRaises(unittest.TestCase):
    def test_probe_all_isolates_engine_exceptions(self):
        service = ConversionService(engines=[ExplodingEngine(), HealthyEngine()])
        infos = service.probe_all()
        self.assertFalse(infos["exploding"].available,
                         "异常引擎必须降级为不可用而非外抛")
        self.assertIn("探测失败", infos["exploding"].detail)
        self.assertTrue(infos["healthy"].available, "其他引擎不受影响")
        self.assertEqual([i.engine_id for i in service.available_engines()], ["healthy"])

    def test_pick_engine_survives_all_exploding(self):
        service = ConversionService(engines=[ExplodingEngine()])
        self.assertIsNone(service.pick_engine(),
                          "全部探测失败时应返回 None 而非崩溃")

    def test_com_probe_survives_missing_winreg(self):
        engine = WordComEngine()
        engine._is_windows = lambda: True
        with mock.patch.dict(sys.modules, {"winreg": None}):
            info = engine.probe()  # 关键：不得抛异常
        self.assertFalse(info.available)
        # 诊断必须能自我说明：不能把「读不到注册表」误报成「未安装」
        self.assertIn("注册表", info.detail)

    def test_com_registry_helpers_degrade_without_winreg(self):
        engine = WordComEngine()
        with mock.patch.dict(sys.modules, {"winreg": None}):
            self.assertFalse(engine._registry_has("Word.Application"))
            self.assertEqual(engine._probe_version("Word.Application"), "")
            self.assertIsNone(engine._first_registered())

    def test_wps_com_probe_survives_missing_winreg(self):
        engine = WpsComEngine()
        engine._is_windows = lambda: True
        with mock.patch.dict(sys.modules, {"winreg": None}):
            info = engine.probe()
        self.assertFalse(info.available)


class TestProbeSpeed(unittest.TestCase):
    def test_soffice_probe_timeout_is_short(self):
        self.assertLessEqual(SofficeEngine.PROBE_TIMEOUT_S, 10.0,
                             "探测超时必须短，否则界面「检查转换引擎」会长时间卡住")

    def test_soffice_probe_degrades_when_version_times_out(self):
        engine = SofficeEngine()
        engine._bin = Path("/nonexistent/soffice")  # 跳过路径查找
        with mock.patch("subprocess.run",
                        side_effect=subprocess.TimeoutExpired("soffice", 8)):
            info = engine.probe()  # 不得抛异常
        # 可执行文件存在即可用（转换阶段还有完整校验），版本为空
        self.assertTrue(info.available)
        self.assertEqual(info.version, "")

    def test_probe_result_is_cached(self):
        calls = []

        class CountingEngine:
            engine_id = "counting"
            NAME = "Counting"

            def probe(self):
                calls.append(1)
                return EngineInfo("counting", "Counting", True)

        service = ConversionService(engines=[CountingEngine()])
        service.probe_all()
        service.probe_all()
        service.available_engines()
        self.assertEqual(len(calls), 1, "重复查询不得重复探测（启动/打开要快）")
        service.probe_all(refresh=True)
        self.assertEqual(len(calls), 2, "显式 refresh 才重新探测")


class TestStartupStaysFast(unittest.TestCase):
    def test_startup_does_not_probe_engines(self):
        """启动路径不得触发探测——用户报告的「前期检查很慢」防线。"""
        from main import create_app_controller

        service = get_shared_service()
        service._probe_cache = None  # 重置缓存以便观测
        create_app_controller()
        self.assertIsNone(service._probe_cache,
                          "构造控制器时不应探测转换引擎")

    def test_engines_module_import_does_not_probe(self):
        """导入引擎模块本身也不能探测（否则启动即变慢）。"""
        for name in list(sys.modules):
            if name.startswith("processing.word_support"):
                del sys.modules[name]
        with mock.patch.object(ComEngineBase, "probe",
                               side_effect=AssertionError("导入时不应探测")):
            import importlib

            import processing.word_support.engines as engines_module
            importlib.reload(engines_module)


if __name__ == "__main__":
    unittest.main()
