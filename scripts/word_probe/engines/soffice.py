"""LibreOffice 引擎：soffice 无界面转换，独立用户配置目录。

对应 spec P0.4 / [S2]。使用独立 UserInstallation 避免与用户正在运行的
LibreOffice 实例冲突；超时终止的进程属于本任务，可安全 kill。
"""

import shutil
import subprocess
import tempfile
from pathlib import Path

from .base import (
    ERR_CONVERT,
    ERR_ENGINE_MISSING,
    ERR_TIMEOUT,
    DEFAULT_TIMEOUT_S,
    ConvertResult,
    EngineInfo,
    sha256_of,
)

SOFFICE_CANDIDATES = [
    "/Applications/LibreOffice.app/Contents/MacOS/soffice",
    "soffice",  # PATH (homebrew 等)
]


def _find_bin() -> Path:
    for cand in SOFFICE_CANDIDATES:
        found = shutil.which(cand) if "/" not in cand else (Path(cand) if Path(cand).exists() else None)
        if found:
            return Path(found)
    return None


def probe() -> EngineInfo:
    bin_path = _find_bin()
    if bin_path is None:
        return EngineInfo("soffice", "LibreOffice (headless)", False,
                          detail="未找到 soffice 可执行文件")
    version = ""
    try:
        out = subprocess.run([bin_path.as_posix(), "--version"],
                             capture_output=True, text=True, timeout=30)
        version = (out.stdout or out.stderr).strip().splitlines()[0]
    except Exception:
        pass
    return EngineInfo("soffice", "LibreOffice (headless)", True,
                      version=version, detail=bin_path.as_posix())


def convert(work_copy: Path, out_pdf: Path, timeout_s: float = DEFAULT_TIMEOUT_S) -> ConvertResult:
    result = ConvertResult(ok=False, engine_id="soffice",
                           sample=work_copy.name,
                           source_sha_before=sha256_of(work_copy))
    bin_path = _find_bin()
    if bin_path is None:
        result.error_kind = ERR_ENGINE_MISSING
        result.error_detail = "未找到 soffice"
        return result

    out_dir = out_pdf.parent
    profile = tempfile.mkdtemp(prefix="wordprobe-lo-profile-")
    cmd = [
        bin_path.as_posix(),
        f"-env:UserInstallation=file://{profile}",
        "--headless", "--norestore", "--nolockcheck",
        "--convert-to", "pdf:writer_pdf_Export",
        "--outdir", out_dir.as_posix(),
        work_copy.as_posix(),
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s)
    except subprocess.TimeoutExpired:
        result.error_kind = ERR_TIMEOUT
        result.error_detail = f"转换超过 {timeout_s}s，soffice 子进程已终止"
        result.cleanup_note = "timeout: soffice killed"
        shutil.rmtree(profile, ignore_errors=True)
        return result

    shutil.rmtree(profile, ignore_errors=True)
    produced = out_dir / (work_copy.stem + ".pdf")
    if proc.returncode != 0 or not produced.exists():
        result.error_kind = ERR_CONVERT
        result.error_detail = (proc.stderr or proc.stdout or "").strip()[:400] or \
                              f"退出码 {proc.returncode}，未生成 PDF"
        return result
    if produced.resolve() != out_pdf.resolve():
        produced.rename(out_pdf)

    result.ok = True
    result.pdf_path = out_pdf.as_posix()
    result.metrics["soffice_returncode"] = proc.returncode
    result.source_sha_after = sha256_of(work_copy)
    result.source_untouched = result.source_sha_before == result.source_sha_after
    result.cleanup_note = "soffice 单次转换自动退出；配置目录已删除"
    return result
