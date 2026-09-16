"""word-jxa 引擎防呆开关与自动化路径测试（不依赖已安装的 Word）。

背景（2026-09-17 真机诊断，design.md 决策 7）：Word 空启动停在模态开始
画面会阻塞全部 AppleEvent；JXA 字符串路径 open 弹「找不到文件」。
可靠配方 = LaunchServices 带文档启动 + AppleScript save as。本文件锁定：
探测门禁开关两个方向、-1708 报错翻译、启动失败/文档打不开的超时出口。
"""
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from processing.word_support import engines as engines_mod
from processing.word_support.engines import WordJxaEngine


def _fake_word_bundle(root: Path) -> Path:
    app = root / "Microsoft Word.app"
    (app / "Contents").mkdir(parents=True, exist_ok=True)
    return app


class TestProbeGate(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.app = _fake_word_bundle(Path(self.tmp.name))
        patcher = mock.patch.dict(os.environ,
                                  {engines_mod._WORD_JXA_OVERRIDE_ENV: ""})
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_gate_off_by_default_after_rewrite(self):
        # 自动化路径重写后引擎默认启用；开关只留作未来故障的防呆
        self.assertFalse(engines_mod.WORD_JXA_SAVEAS_BROKEN)

    def test_probe_available_when_gate_off(self):
        with mock.patch.object(WordJxaEngine, "WORD_APP", self.app):
            info = WordJxaEngine().probe()
        self.assertTrue(info.available)
        self.assertEqual(info.detail, str(self.app))

    def test_probe_unavailable_when_gate_on(self):
        with mock.patch.object(WordJxaEngine, "WORD_APP", self.app), \
             mock.patch.object(engines_mod, "WORD_JXA_SAVEAS_BROKEN", True):
            info = WordJxaEngine().probe()
        self.assertFalse(info.available)
        self.assertIn("-1708", info.detail)

    def test_override_env_beats_gate(self):
        with mock.patch.object(WordJxaEngine, "WORD_APP", self.app), \
             mock.patch.object(engines_mod, "WORD_JXA_SAVEAS_BROKEN", True), \
             mock.patch.dict(os.environ,
                             {engines_mod._WORD_JXA_OVERRIDE_ENV: "1"}):
            info = WordJxaEngine().probe()
        self.assertTrue(info.available)

    def test_probe_unavailable_without_bundle(self):
        missing = Path(self.tmp.name) / "absent.app"
        with mock.patch.object(WordJxaEngine, "WORD_APP", missing):
            info = WordJxaEngine().probe()
        self.assertFalse(info.available)
        self.assertIn("未安装", info.detail)


def _engine_with_tmp_stage(tmp: Path) -> WordJxaEngine:
    engine = WordJxaEngine()
    engine._stage_dir = tmp / "stage"
    return engine


class TestConvertFlow(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.engine = _engine_with_tmp_stage(self.root)
        self.work_copy = self.root / "source.docx"
        self.work_copy.write_bytes(b"docx")
        self.out_pdf = self.root / "snapshot.pdf"

    def _patch_env(self, open_ok=True, doc_name="source.docx", save=None):
        """统一打桩：open 子进程、Word 运行态、_osa 序列、sleep。"""
        open_calls = []

        def fake_run(cmd, **kwargs):
            open_calls.append(cmd)
            if not open_ok:
                raise OSError("launch failed")
            return mock.Mock(returncode=0)

        osa_calls = []

        def fake_osa(script, args, timeout_s):
            osa_calls.append(script.strip().splitlines()[1] if script else "")
            if "count of documents" in script:  # 轮询文档名
                return doc_name, None
            if "save as active document" in script:  # 另存
                if isinstance(save, tuple):
                    err = save[1]
                    if err is None:  # 成功：落一个假产物
                        self.engine._stage_dir.mkdir(parents=True,
                                                     exist_ok=True)
                        (self.engine._stage_dir /
                         Path(args[0]).name).write_bytes(b"%PDF-")
                    return save
                return "", None
            return "", None  # close 等尽力而为调用

        patches = [
            mock.patch.object(engines_mod.subprocess, "run", fake_run),
            mock.patch.object(WordJxaEngine, "_word_running",
                              staticmethod(lambda: False)),
            mock.patch.object(WordJxaEngine, "_osa", staticmethod(fake_osa)),
            mock.patch.object(WordJxaEngine, "_dismiss_error_reporter",
                              staticmethod(lambda: "")),
            mock.patch.object(WordJxaEngine, "_best_effort_quit",
                              staticmethod(lambda we_launched: "")),
            mock.patch.object(engines_mod.time, "sleep"),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        return open_calls

    def test_success_produces_pdf_result(self):
        self._patch_env(doc_name="source.docx", save=(None, None))
        result = self.engine.convert(self.work_copy, self.out_pdf,
                                     timeout_s=30)
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["pdf_path"], str(self.out_pdf))
        self.assertTrue(self.out_pdf.exists())

    def test_launch_failure_returns_convert_error(self):
        self._patch_env(open_ok=False)
        result = self.engine.convert(self.work_copy, self.out_pdf,
                                     timeout_s=30)
        self.assertFalse(result["ok"])
        self.assertIn("无法启动 Word", result["error_detail"])

    def test_doc_never_opens_times_out_with_guidance(self):
        self._patch_env(doc_name="")
        result = self.engine.convert(self.work_copy, self.out_pdf,
                                     timeout_s=10)
        self.assertFalse(result["ok"])
        self.assertIn("开始画面", result["error_detail"])

    def test_1708_maps_to_friendly_guidance(self):
        err = 'execution error: "Microsoft Word"遇到一个错误：'
        err += "「active document」不理解「save as」信息。 (-1708)"
        self._patch_env(save=(None, err))
        result = self.engine.convert(self.work_copy, self.out_pdf,
                                     timeout_s=30)
        self.assertFalse(result["ok"])
        self.assertIn("-1708", result["error_detail"])
        self.assertIn("LibreOffice", result["error_detail"])
        self.assertNotIn("不理解", result["error_detail"])

    def test_permission_denied_short_circuits(self):
        """轮询阶段 -1743 立即返回权限错误，不等超时。"""
        def fake_osa(script, args, timeout_s):
            if "count of documents" in script:
                return None, "osascript 不允许辅助访问。 (-1743)"
            return "", None

        patches = [
            mock.patch.object(engines_mod.subprocess, "run",
                              lambda cmd, **kw: mock.Mock(returncode=0)),
            mock.patch.object(WordJxaEngine, "_word_running",
                              staticmethod(lambda: False)),
            mock.patch.object(WordJxaEngine, "_osa", staticmethod(fake_osa)),
            mock.patch.object(WordJxaEngine, "_dismiss_error_reporter",
                              staticmethod(lambda: "")),
            mock.patch.object(WordJxaEngine, "_best_effort_quit",
                              staticmethod(lambda we_launched: "")),
            mock.patch.object(engines_mod.time, "sleep"),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        result = self.engine.convert(self.work_copy, self.out_pdf,
                                     timeout_s=30)
        self.assertFalse(result["ok"])
        self.assertEqual(result["error_kind"], engines_mod.KIND_PERMISSION)
        self.assertIn("自动化权限", result["error_detail"])


if __name__ == "__main__":
    unittest.main()
