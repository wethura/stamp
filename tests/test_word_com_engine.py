"""Windows COM 引擎（Word/WPS）测试：假 COM 桩，非 Windows 平台可跑。

真机验证属于 P0.2/P3（见 compatibility.md），此处守护：
- 探测语义（非 Windows 不可用 / 注册表 ProgID 命中）
- 启动独立实例 vs 附着用户实例的进程归属规则
- ExportAsFixedFormat 失败回退 SaveAs2；双失败归类 convert 且清理文档
- 取消时机与迟到结果丢弃
"""
import threading
import unittest
from pathlib import Path
import tempfile

from processing.word_support.engines import WpsComEngine, WordComEngine


class FakeComApp:
    def __init__(self, recorder, export_ok=True, saveas_ok=True):
        self._rec = recorder
        self._export_ok = export_ok
        self._saveas_ok = saveas_ok
        self.Documents = FakeDocuments(recorder, self)
        self.Visible = True
        self.DisplayAlerts = -1

    def Quit(self):
        self._rec.append("quit")


class FakeDocuments:
    def __init__(self, rec, app):
        self._rec = rec
        self._app = app

    def Open(self, path, ReadOnly=False, AddToRecentFiles=True):
        self._rec.append(f"open:{path}:ro={ReadOnly}:recent={AddToRecentFiles}")
        return FakeDoc(self._rec, self._app)


class FakeDoc:
    def __init__(self, rec, app):
        self._rec = rec
        self._app = app

    def ExportAsFixedFormat(self, out, fmt):
        self._rec.append(f"export:{out}:{fmt}")
        if not self._app._export_ok:
            raise RuntimeError("export not supported")
        Path(out).write_bytes(b"%PDF-1.4 fake")

    def SaveAs2(self, out, FileFormat=None):
        self._rec.append(f"saveas2:{out}:{FileFormat}")
        if not self._app._saveas_ok:
            raise RuntimeError("saveas2 failed")
        # 模拟写出 PDF（SaveAs2 成功路径才落盘，export 由桩直接落盘语义代替）
        Path(out).write_bytes(b"%PDF-1.4 fake")

    def Close(self, save):
        self._rec.append(f"close:{save}")


class FakePythoncom:
    def __init__(self, rec):
        self._rec = rec

    def CoInitialize(self):
        self._rec.append("coinit")

    def CoUninitialize(self):
        self._rec.append("couninit")


class FakeClient:
    def __init__(self, rec, active_app=None, export_ok=True, saveas_ok=True):
        self._rec = rec
        self._active = active_app
        self._export_ok = export_ok
        self._saveas_ok = saveas_ok

    def GetActiveObject(self, prog_id):
        self._rec.append(f"getactive:{prog_id}")
        if self._active is None:
            raise RuntimeError("not running")
        return self._active

    def DispatchEx(self, prog_id):
        self._rec.append(f"dispatchex:{prog_id}")
        return FakeComApp(self._rec, self._export_ok, self._saveas_ok)


class ComEngineTestCase(unittest.TestCase):
    def make_engine(self, prog_ids_registered=("Word.Application",), **client_kw):
        engine = WordComEngine()
        rec = []

        engine._is_windows = lambda: True
        engine._registry_has = lambda pid: pid in prog_ids_registered
        engine._load_com_modules = lambda: (FakePythoncom(rec), FakeClient(rec, **client_kw))
        engine._probe_version = lambda pid: "Word.Application.16"
        return engine, rec

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.docx = self.root / "in.docx"
        self.docx.write_bytes(b"pk fake")
        self.pdf = self.root / "out.pdf"

    def test_export_writes_pdf_and_cleans_up_launched_instance(self):
        engine, rec = self.make_engine()
        result = engine.convert(self.docx, self.pdf)
        self.assertTrue(result["ok"], rec)
        self.assertTrue(self.pdf.exists())
        for step in ("coinit", "dispatchex:Word.Application", "close:False", "quit", "couninit"):
            self.assertIn(step, rec, rec)

    def test_attached_running_instance_is_never_quit(self):
        engine, rec = self.make_engine()
        attached = FakeComApp(rec, export_ok=True)
        engine._load_com_modules = lambda: (
            FakePythoncom(rec), FakeClient(rec, active_app=attached))
        result = engine.convert(self.docx, self.pdf)
        self.assertTrue(result["ok"], rec)
        self.assertIn("getactive:Word.Application", rec)
        self.assertNotIn("dispatchex:Word.Application", rec)
        self.assertNotIn("quit", rec, "附着用户实例时绝不能 Quit")
        self.assertIn("close:False", rec)

    def test_export_failure_falls_back_to_saveas2(self):
        engine, rec = self.make_engine(export_ok=False)
        result = engine.convert(self.docx, self.pdf)
        self.assertTrue(result["ok"], rec)
        self.assertTrue(any(r.startswith("saveas2:") for r in rec), rec)

    def test_both_paths_fail_reports_convert_and_closes_doc(self):
        engine, rec = self.make_engine(export_ok=False, saveas_ok=False)
        result = engine.convert(self.docx, self.pdf)
        self.assertFalse(result["ok"])
        self.assertEqual(result["error_kind"], "convert")
        self.assertIn("close:False", rec)
        self.assertIn("quit", rec)

    def test_cancel_before_start(self):
        engine, rec = self.make_engine()
        cancel = threading.Event()
        cancel.set()
        result = engine.convert(self.docx, self.pdf, cancel_event=cancel)
        self.assertFalse(result["ok"])
        self.assertEqual(result["error_kind"], "cancelled")
        self.assertEqual(rec, [], "取消后不得触碰 COM")

    def test_not_registered_reports_engine_missing(self):
        engine, rec = self.make_engine(prog_ids_registered=())
        result = engine.convert(self.docx, self.pdf)
        self.assertFalse(result["ok"])
        self.assertEqual(result["error_kind"], "engine_missing")

    def test_probe_semantics(self):
        engine, _ = self.make_engine()
        info = engine.probe()
        self.assertTrue(info.available)
        self.assertIn("Word.Application", info.detail)

        raw = WordComEngine()  # 非 Windows 真实环境
        info = raw.probe()
        self.assertFalse(info.available)
        self.assertEqual(raw.convert(self.docx, self.pdf)["error_kind"], "engine_missing")

    def test_wps_prog_ids_covered(self):
        engine = WpsComEngine()
        engine._is_windows = lambda: True
        registered = {"kwps.application"}
        engine._registry_has = lambda pid: pid in registered
        engine._probe_version = lambda pid: ""
        info = engine.probe()
        self.assertTrue(info.available)
        self.assertIn("kwps.application", info.detail)


if __name__ == "__main__":
    unittest.main()
