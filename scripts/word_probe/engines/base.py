"""Word 转换引擎探测/转换的公共契约。

对应 .project/plans/word-support/spec.md P0.1：每个后端实现 probe() 与
convert()，统一产出可序列化的结果，供 probe.py 汇总为证据报告。
"""

import hashlib
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

DEFAULT_TIMEOUT_S = 120

# 错误分类（spec「异常与用户出口」对应的机器可读版本）
ERR_TIMEOUT = "timeout"
ERR_PERMISSION = "permission"          # macOS 自动化授权被拒
ERR_ENGINE_MISSING = "engine_missing"  # 未安装 / 无法定位可执行文件
ERR_CONVERT = "convert"                # 引擎调用了但没产出 PDF
ERR_INVALID_PDF = "invalid_pdf"        # 产出文件无法按 PDF 打开或校验失败
ERR_INTERNAL = "internal"


@dataclass
class EngineInfo:
    engine_id: str
    name: str
    available: bool
    version: str = ""
    detail: str = ""            # 安装路径 / 不可用原因
    manual_path_only: bool = False  # True 表示接口不可用，仅支持手动导入 PDF


@dataclass
class ConvertResult:
    ok: bool
    engine_id: str
    sample: str
    pdf_path: Optional[str] = None
    elapsed_s: float = 0.0
    error_kind: Optional[str] = None
    error_detail: str = ""
    source_sha_before: str = ""
    source_sha_after: str = ""
    source_untouched: bool = True
    cleanup_note: str = ""
    metrics: dict = field(default_factory=dict)  # pages / sizes / text 校验结果


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def run_command(cmd: list, timeout_s: float) -> subprocess.CompletedProcess:
    """Run a conversion command with timeout; raise TimeoutExpired on stall."""
    return subprocess.run(
        cmd, capture_output=True, text=True, timeout=timeout_s,
    )


def classify_oserror(exc: OSError) -> str:
    return ERR_ENGINE_MISSING
