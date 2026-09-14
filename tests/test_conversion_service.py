"""ConversionService 状态机测试：偏好记忆/取消/超时/源文件保护/产物校验。

全部使用桩引擎，不依赖已安装的办公软件。
"""
import threading
import time
import unittest
import zipfile
from pathlib import Path
import tempfile

import fitz

from processing.word_support.engines import EngineInfo
from processing.word_support.service import ConversionError, ConversionService


def make_docx(path: Path):
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        z.writestr("word/document.xml", "<document/>")


def make_pdf(path: Path, pages: int = 3):
    with fitz.open() as doc:
        for i in range(pages):
            p = doc.new_page(width=595, height=842)
            p.insert_text((50, 80), f"page {i + 1}")
        doc.save(str(path))


class StubEngine:
    """可编程桩引擎。behave: ok | fail；delay>0 时响应取消事件。"""

    def __init__(self, engine_id="stub", behave="ok", available=True,
                 delay=0.0, pages=3, manual=False):
        self.engine_id = engine_id
        self.name = f"Stub({engine_id})"
        self.behave = behave
        self.available = available
        self.delay = delay
        self.pages = pages
        self.manual = manual
        self.convert_calls = 0

    def probe(self) -> EngineInfo:
        return EngineInfo(
            self.engine_id, self.name, self.available, version="1.0",
            detail="stub", manual_path_only=self.manual,
        )

    def convert(self, work_copy, out_pdf, timeout_s=120.0, cancel_event=None):
        self.convert_calls += 1
        steps = max(int(self.delay / 0.02), 1)
        for _ in range(steps):
            if cancel_event is not None and cancel_event.is_set():
                return {"ok": False, "error_kind": "cancelled", "error_detail": "已取消"}
            time.sleep(0.02)
        if self.behave == "fail":
            return {"ok": False, "error_kind": "convert", "error_detail": "boom"}
        make_pdf(out_pdf, self.pages)
        return {"ok": True, "pdf_path": str(out_pdf)}


def service_with(engines, **kw):
    tmp = tempfile.TemporaryDirectory()
    kw.setdefault("preference_path", str(Path(tmp.name) / "pref.json"))
    svc = ConversionService(engines=engines, **kw)
    return svc, tmp


class TestEnginePicking(unittest.TestCase):
    def test_none_available_returns_none(self):
        svc, tmp = service_with([StubEngine("a", available=False)])
        self.addCleanup(tmp.cleanup)
        self.assertIsNone(svc.pick_engine())

    def test_manual_only_engines_are_not_pickable(self):
        svc, tmp = service_with([StubEngine("wps", manual=True)])
        self.addCleanup(tmp.cleanup)
        self.assertIsNone(svc.pick_engine())
        infos = svc.available_engines()
        self.assertEqual(infos, [])

    def test_first_auto_engine_used_by_default(self):
        engines = [StubEngine("a"), StubEngine("b")]
        svc, tmp = service_with(engines)
        self.addCleanup(tmp.cleanup)
        self.assertEqual(svc.pick_engine().engine_id, "a")

    def test_preference_respected_while_available(self):
        engines = [StubEngine("a"), StubEngine("b")]
        svc, tmp = service_with(engines)
        self.addCleanup(tmp.cleanup)
        svc.save_preference("b")
        self.assertEqual(svc.pick_engine().engine_id, "b")

    def test_preference_for_gone_engine_falls_back(self):
        engines = [StubEngine("a", available=False), StubEngine("b")]
        svc, tmp = service_with(engines)
        self.addCleanup(tmp.cleanup)
        svc.save_preference("a")
        self.assertEqual(svc.pick_engine().engine_id, "b")

    def test_preference_persisted_to_file(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        pref = Path(tmp.name) / "pref.json"
        svc = ConversionService(engines=[StubEngine("a"), StubEngine("b")],
                                preference_path=str(pref))
        svc.save_preference("b")
        svc2 = ConversionService(engines=[StubEngine("a"), StubEngine("b")],
                                 preference_path=str(pref))
        self.assertEqual(svc2.pick_engine().engine_id, "b")


class TestConversion(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / "in.docx"
        make_docx(self.source)
        self.work_dir = self.root / "work"

    def _service(self, engine):
        pref = self.root / "pref.json"
        return ConversionService(engines=[engine], preference_path=str(pref))

    def test_successful_conversion_copies_and_validates(self):
        svc = self._service(StubEngine("a", pages=4))
        outcome = svc.convert(self.source, self.work_dir)
        self.assertTrue(outcome.ok)
        self.assertEqual(outcome.page_count, 4)
        snapshot = Path(outcome.snapshot_path)
        self.assertTrue(snapshot.exists())

    def test_source_file_never_modified(self):
        before = self.source.read_bytes()
        svc = self._service(StubEngine("a"))
        svc.convert(self.source, self.work_dir)
        self.assertEqual(self.source.read_bytes(), before)

    def test_engine_failure_raises_classified_error(self):
        svc = self._service(StubEngine("a", behave="fail"))
        with self.assertRaises(ConversionError) as ctx:
            svc.convert(self.source, self.work_dir)
        self.assertEqual(ctx.exception.kind, "convert")

    def test_timeout_raises_classified_error(self):
        # 引擎耗时须明显超过 timeout+0.5s 的迟到判定阈值，
        # 否则受平台 sleep 粒度影响在阈值边界抖动（Windows 曾复现）
        svc = self._service(StubEngine("a", delay=1.5))
        with self.assertRaises(ConversionError) as ctx:
            svc.convert(self.source, self.work_dir, timeout_s=0.3)
        self.assertEqual(ctx.exception.kind, "timeout")

    def test_cancel_before_start_raises_cancelled(self):
        svc = self._service(StubEngine("a", delay=5.0))
        cancel = threading.Event()
        cancel.set()
        with self.assertRaises(ConversionError) as ctx:
            svc.convert(self.source, self.work_dir, cancel_event=cancel)
        self.assertEqual(ctx.exception.kind, "cancelled")

    def test_cancel_during_conversion_raises_cancelled(self):
        svc = self._service(StubEngine("a", delay=5.0))
        cancel = threading.Event()
        timer = threading.Timer(0.2, cancel.set)
        timer.start()
        self.addCleanup(timer.cancel)
        with self.assertRaises(ConversionError) as ctx:
            svc.convert(self.source, self.work_dir, cancel_event=cancel)
        self.assertEqual(ctx.exception.kind, "cancelled")

    def test_corrupt_source_rejected_before_engine_called(self):
        self.source.write_bytes(b"garbage")
        engine = StubEngine("a")
        svc = self._service(engine)
        with self.assertRaises(ConversionError) as ctx:
            svc.convert(self.source, self.work_dir)
        self.assertEqual(ctx.exception.kind, "precheck")
        self.assertEqual(engine.convert_calls, 0, "前置校验失败不得调用引擎")

    def test_work_dir_cleaned_after_success(self):
        svc = self._service(StubEngine("a"))
        svc.convert(self.source, self.work_dir)
        leftovers = [p.name for p in self.work_dir.rglob("*") if p.is_file()]
        self.assertEqual(leftovers, ["snapshot.pdf"],
                         "工作副本应清理，目录中只留快照")


if __name__ == "__main__":
    unittest.main()


class TestPreferenceAutoBehavior(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / "in.docx"
        make_docx(self.source)

    def _service(self, engines):
        return ConversionService(
            engines=engines,
            preference_path=str(self.root / "pref.json"))

    def test_clear_preference_falls_back_to_first_available(self):
        svc = self._service([StubEngine("a"), StubEngine("b")])
        svc.save_preference("b")
        self.assertEqual(svc.pick_engine().engine_id, "b")
        svc.clear_preference()
        self.assertIsNone(svc.current_preference())
        self.assertEqual(svc.pick_engine().engine_id, "a")

    def test_current_preference_reflects_saved_value(self):
        svc = self._service([StubEngine("a"), StubEngine("b")])
        self.assertIsNone(svc.current_preference())
        svc.save_preference("a")
        self.assertEqual(svc.current_preference(), "a")

    def test_empty_preference_treated_as_auto(self):
        pref = self.root / "pref.json"
        pref.write_text('{"engine_id": ""}', encoding="utf-8")
        svc = self._service([StubEngine("a"), StubEngine("b")])
        self.assertIsNone(svc.current_preference())
        self.assertEqual(svc.pick_engine().engine_id, "a")

    def test_shared_service_singleton(self):
        from processing.word_support import service as svc_module
        first = svc_module.get_shared_service()
        second = svc_module.get_shared_service()
        self.assertIs(first, second)
        # 单例与 WordHandler 默认服务一致（设置与加载共用偏好）
        from processing.handlers.word_handler import WordHandler
        self.assertIs(WordHandler().service, first)
