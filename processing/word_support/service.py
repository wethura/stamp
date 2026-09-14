"""Word 转换服务：引擎探测缓存、偏好记忆、前置校验、转换与产物校验。

冻结契约见 .project/plans/word-support/design.md（P1.1 v1）。
"""
import hashlib
import json
import os
import shutil
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

import fitz

from .engines import DEFAULT_ENGINES, EngineInfo
from .errors import (
    KIND_CANCELLED,
    KIND_CONVERT,
    KIND_ENGINE_MISSING,
    KIND_INVALID_PDF,
    KIND_MANUAL_PATH_ONLY,
    KIND_PRECHECK,
    KIND_SOURCE_CHANGED,
    KIND_TIMEOUT,
    ConversionError,
)
from .precheck import DocxPrecheckError, check_docx

DEFAULT_PREFERENCE_PATH = os.path.join(
    os.path.expanduser("~"), ".stamp_tool", "word_engine.json")


@dataclass
class ConversionOutcome:
    ok: bool
    snapshot_path: str
    engine_id: str
    elapsed_s: float
    page_count: int


def _sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


class ConversionService:
    """可注入引擎列表与偏好存储；线程安全性：convert 可在后台线程调用。"""

    def __init__(self, engines=None, preference_path: str = None,
                 timeout_s: float = 120.0):
        self._engines = list(engines) if engines is not None else list(DEFAULT_ENGINES)
        self.preference_path = preference_path or DEFAULT_PREFERENCE_PATH
        self.timeout_s = timeout_s
        self._probe_cache: Dict[str, EngineInfo] = None
        self._pref_lock = threading.Lock()

    # ── 探测 ─────────────────────────────────────────────────────────

    def probe_all(self, refresh: bool = False) -> Dict[str, EngineInfo]:
        if self._probe_cache is None or refresh:
            self._probe_cache = {
                engine.engine_id: engine.probe() for engine in self._engines
            }
        return dict(self._probe_cache)

    def available_engines(self, refresh: bool = False) -> List[EngineInfo]:
        """可自动转换的引擎（排除不可用与仅手动路径的）。"""
        infos = self.probe_all(refresh)
        return [info for info in infos.values()
                if info.available and not info.manual_path_only]

    def _engine_by_id(self, engine_id: str):
        for engine in self._engines:
            if engine.engine_id == engine_id:
                return engine
        raise ConversionError(KIND_ENGINE_MISSING, f"未知引擎: {engine_id}")

    # ── 偏好记忆 ─────────────────────────────────────────────────────

    def _load_preference(self) -> Optional[str]:
        try:
            with open(self.preference_path, "r", encoding="utf-8") as f:
                engine_id = json.load(f).get("engine_id")
            return engine_id if isinstance(engine_id, str) and engine_id else None
        except (OSError, ValueError):
            return None

    def current_preference(self) -> Optional[str]:
        """用户保存的首选引擎 id；None 表示「自动」。"""
        return self._load_preference()

    def save_preference(self, engine_id: str):
        with self._pref_lock:
            try:
                os.makedirs(os.path.dirname(self.preference_path), exist_ok=True)
                tmp = self.preference_path + ".tmp"
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump({"engine_id": engine_id}, f)
                os.replace(tmp, self.preference_path)
            except OSError:
                pass  # 偏好记忆失败不阻断转换

    def clear_preference(self):
        """恢复「自动」：按检测顺序使用第一个可用引擎。"""
        with self._pref_lock:
            try:
                os.remove(self.preference_path)
            except OSError:
                pass

    def pick_engine(self, refresh: bool = False) -> Optional[EngineInfo]:
        infos = {info.engine_id: info for info in self.available_engines(refresh)}
        if not infos:
            return None
        preferred = self._load_preference()
        if preferred and preferred in infos:
            return infos[preferred]
        return next(iter(infos.values()))

    # ── 转换 ─────────────────────────────────────────────────────────

    def convert(self, source: str, work_dir: Path, engine: EngineInfo = None,
                cancel_event: threading.Event = None,
                timeout_s: float = None) -> ConversionOutcome:
        """转换 DOCX → PDF 快照。失败抛 ConversionError；源文件保证零修改。"""
        source_path = Path(source)
        if cancel_event is not None and cancel_event.is_set():
            raise ConversionError(KIND_CANCELLED, "已取消")

        if engine is None:
            engine = self.pick_engine()
        if engine is None or not engine.available:
            manual = [i for i in self.probe_all().values()
                      if i.available and i.manual_path_only]
            if manual:
                raise ConversionError(
                    KIND_MANUAL_PATH_ONLY,
                    "已检测到 WPS，当前版本暂不能自动转换。"
                    "请在 WPS 中导出 PDF 后拖入本工具。")
            raise ConversionError(
                KIND_ENGINE_MISSING,
                "未找到可用的 Word 转换引擎。请安装 LibreOffice，"
                "或在 Word/WPS 中将文件导出为 PDF 后拖入本工具。")
        engine_obj = self._engine_by_id(engine.engine_id)

        try:
            check_docx(str(source_path))
        except DocxPrecheckError as exc:
            raise ConversionError(KIND_PRECHECK, str(exc))

        work_dir = Path(work_dir)
        work_dir.mkdir(parents=True, exist_ok=True)
        work_copy = work_dir / f"source{source_path.suffix.lower()}"
        shutil.copy2(source_path, work_copy)
        sha_before = _sha256_of(source_path)

        out_pdf = work_dir / "snapshot.pdf"
        started = time.monotonic()
        result = engine_obj.convert(work_copy, out_pdf,
                                    timeout_s=timeout_s or self.timeout_s,
                                    cancel_event=cancel_event)
        elapsed = time.monotonic() - started

        if cancel_event is not None and cancel_event.is_set():
            raise ConversionError(KIND_CANCELLED, "已取消")
        if not result.get("ok"):
            raise ConversionError(result.get("error_kind") or KIND_CONVERT,
                                  result.get("error_detail") or "转换失败")
        effective_timeout = timeout_s or self.timeout_s
        if elapsed > effective_timeout + 0.5:
            # 引擎未按时限返回（迟到结果按 A06 丢弃）
            raise ConversionError(KIND_TIMEOUT,
                                  f"转换超过 {int(effective_timeout)} 秒")

        snapshot = Path(result["pdf_path"])
        try:
            with fitz.open(str(snapshot)) as doc:
                page_count = doc.page_count
            if page_count < 1:
                raise ValueError("empty")
        except Exception:  # noqa: BLE001
            raise ConversionError(KIND_INVALID_PDF, "转换产物无法作为 PDF 打开")

        if _sha256_of(source_path) != sha_before:
            raise ConversionError(KIND_SOURCE_CHANGED, "源文件在转换过程中被修改")

        work_copy.unlink(missing_ok=True)
        return ConversionOutcome(ok=True, snapshot_path=str(snapshot),
                                 engine_id=engine.engine_id,
                                 elapsed_s=round(elapsed, 2),
                                 page_count=page_count)


# 进程级共享实例：设置对话框与每次新建的 WordHandler 共用探测缓存与偏好，
# 避免“设置里改了引擎、下次打开文档仍用旧的”这类不一致。
_SHARED_SERVICE: Optional["ConversionService"] = None


def get_shared_service() -> "ConversionService":
    global _SHARED_SERVICE
    if _SHARED_SERVICE is None:
        _SHARED_SERVICE = ConversionService()
    return _SHARED_SERVICE
