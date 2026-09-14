"""Word 转换引擎探测 CLI（P0.1）。

用法：
    python -m scripts.word_probe.probe                    # 全引擎全样本
    python -m scripts.word_probe.probe --engines soffice  # 指定引擎
    python -m scripts.word_probe.probe --full             # 加 100 页样本

产出：scripts/word_probe/out/report-<时间戳>.{md,json} 及 PDF/截图证据。
不接入 GUI；源样本目录不会被写入（转换在工作副本上进行并做前后哈希比对）。
"""

import argparse
import json
import shutil
import time
from datetime import datetime
from pathlib import Path

from .engines import soffice as soffice_engine
from .engines import word_mac as word_engine
from .engines import wps_mac as wps_engine
from .engines.base import ERR_INVALID_PDF, ConvertResult
from .make_samples import generate
from .validate import validate_pdf

PROBE_DIR = Path(__file__).parent
OUT_DIR = PROBE_DIR / "out"

# 样本 → 校验期望。corrupt 样本期望引擎报错（若被当纯文本导入则视为 FAIL，
# 说明应用层需要前置 docx 文件头校验）。
SAMPLE_EXPECTATIONS = {
    "contract-1p": {"pages": 1, "contains": ("第 1 页 / 共 1 页", "第五条")},
    "contract-10p": {"pages": 10, "contains": ("第 1 页 / 共 10 页", "第 10 页 / 共 10 页")},
    "contract-100p": {"pages": 100, "contains": ("第 100 页 / 共 100 页",)},
    "mixed-layout": {"pages": 2, "contains": ("混合布局样本", "横向页")},
    "corrupt": {"expect_failure": True},
}


def _run_engine(module, sample_name: str, work_copy: Path, out_pdf: Path,
                timeout_s: float) -> ConvertResult:
    expect = SAMPLE_EXPECTATIONS.get(sample_name, {})
    start = time.monotonic()
    result = module.convert(work_copy, out_pdf, timeout_s=timeout_s)
    result.elapsed_s = round(time.monotonic() - start, 2)

    if expect.get("expect_failure"):
        if not result.ok:
            result.metrics["expected_failure"] = True
            result.metrics["classified_error"] = result.error_kind
            result.metrics["error_detail"] = result.error_detail
            result.ok = True  # 按预期失败 = 探测通过
            result.error_kind = None
            result.error_detail = ""
        else:
            result.ok = False
            result.error_kind = ERR_INVALID_PDF
            result.error_detail = "损坏文件被引擎当作有效文档导入——需要应用层前置校验 docx 文件头"
        result.sample = sample_name
        return result

    if result.ok:
        try:
            metrics = validate_pdf(Path(result.pdf_path), expect.get("pages"),
                                   expect.get("contains", ()))
            result.metrics.update(metrics)
            if not metrics.get("ok"):
                result.ok = False
                result.error_kind = ERR_INVALID_PDF
                result.error_detail = metrics.get("detail", "PDF 校验未通过（缺文字或页数不符）")
        except Exception as exc:  # noqa: BLE001
            result.ok = False
            result.error_kind = ERR_INVALID_PDF
            result.error_detail = f"PDF 无法校验: {exc}"
    result.sample = sample_name
    return result


def _cleanup_work(work_dir: Path):
    shutil.rmtree(work_dir, ignore_errors=True)


def main():
    parser = argparse.ArgumentParser(description="Word 转换引擎探测（P0）")
    parser.add_argument("--engines", default="word,soffice,wps",
                        help="逗号分隔：word,soffice,wps")
    parser.add_argument("--samples", default="contract-1p,contract-10p,mixed-layout,corrupt")
    parser.add_argument("--timeout", type=float, default=120)
    parser.add_argument("--full", action="store_true", help="包含 100 页样本")
    parser.add_argument("--outdir", type=Path, default=OUT_DIR)
    args = parser.parse_args()

    if args.full and "contract-100p" not in args.samples:
        args.samples += ",contract-100p"
    sample_names = [s.strip() for s in args.samples.split(",") if s.strip()]
    engine_names = [e.strip() for e in args.engines.split(",") if e.strip()]
    engine_modules = {"word": word_engine, "soffice": soffice_engine, "wps": wps_engine}

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir = args.outdir / stamp
    samples_dir = run_dir / "samples"
    made = generate(samples_dir, sample_names)

    engine_infos = {name: module.probe() for name, module in engine_modules.items()}

    all_results = []
    for engine_name in engine_names:
        info = engine_infos[engine_name]
        module = engine_modules[engine_name]
        for sample_name in sample_names:
            sample_path = made[sample_name]
            if not info.available:
                result = ConvertResult(ok=False, engine_id=info.engine_id, sample=sample_name,
                                       error_kind="engine_missing", error_detail=info.detail)
            elif info.manual_path_only:
                result = ConvertResult(ok=False, engine_id=info.engine_id, sample=sample_name,
                                       error_kind="manual_path_only",
                                       error_detail="自动化接口未验证，仅支持手动导入 PDF")
            else:
                work_dir = run_dir / "work" / f"{engine_name}-{sample_name}"
                work_dir.mkdir(parents=True, exist_ok=True)
                work_copy = work_dir / sample_path.name
                shutil.copy2(sample_path, work_copy)
                try:
                    result = _run_engine(module, sample_name, work_copy,
                                         work_dir / f"{sample_name}.pdf", args.timeout)
                finally:
                    _cleanup_work(work_dir)
            all_results.append(result)
            status = "PASS" if result.ok else f"FAIL({result.error_kind})"
            print(f"[{status}] {engine_name} × {sample_name}"
                  f"  {result.elapsed_s}s  {result.error_detail[:80]}")

    report = build_report(engine_infos, all_results, run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    md_path = run_dir / "report.md"
    json_path = run_dir / "report.json"
    md_path.write_text(report["markdown"], encoding="utf-8")
    json_path.write_text(json.dumps(report["json"], ensure_ascii=False, indent=2),
                         encoding="utf-8")
    print(f"\n报告: {md_path}\nJSON: {json_path}")


def build_report(engine_infos, results, run_dir: Path) -> dict:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = [f"# Word 转换引擎探测报告（{now}）", ""]
    lines += ["## 环境", ""]
    for info in engine_infos.values():
        status = "可用" if info.available else "不可用"
        extra = "，仅手动路径" if info.manual_path_only else ""
        lines.append(f"- {info.name}: {status}{extra}，版本 {info.version or '未知'}，{info.detail}")
    lines += ["", "## 转换结果", "",
              "| 引擎 | 样本 | 结果 | 耗时s | 页数 | 错误 |", "|---|---|---|---|---|---|"]
    for r in results:
        pages = r.metrics.get("page_count", "-") if r.ok else "-"
        lines.append(f"| {r.engine_id} | {r.sample} | {'✅' if r.ok else '❌ ' + str(r.error_kind)} "
                     f"| {r.elapsed_s} | {pages} | {(r.error_detail or '')[:60]} |")
    lines += ["", "## 关键明细", ""]
    for r in results:
        if not r.ok:
            lines.append(f"- **{r.engine_id} × {r.sample}**：{r.error_kind} — {r.error_detail}")
        else:
            sizes = r.metrics.get("page_sizes_pt")
            lines.append(f"- {r.engine_id} × {r.sample}：页数 {r.metrics.get('page_count')}，"
                         f"文字层 {'保留' if r.metrics.get('text_layer_preserved') else '丢失'}，"
                         f"尺寸 {sizes}，源文件未被修改={r.source_untouched}")
        if r.cleanup_note:
            lines.append(f"  - 清理：{r.cleanup_note}")
    markdown = "\n".join(lines)

    payload = {
        "generated_at": now,
        "engines": [vars(i) for i in engine_infos.values()],
        "results": [dict(vars(r)) for r in results],
        "run_dir": str(run_dir),
    }
    return {"markdown": markdown, "json": payload}


if __name__ == "__main__":
    main()
