"""合成 .docx 验证样本生成（A01/A02 子集 + 错误路径样本）。

用 python-docx 生成确定性分页的中文合同样本；多页样本用显式分页符，
保证任何引擎转换后页数可校验。
"""

from pathlib import Path

from docx import Document
from docx.enum.section import WD_ORIENT
from docx.enum.text import WD_BREAK
from docx.shared import Cm, Pt

CONTRACT_TITLE = "技术验证用中文合同样本"
CLAUSES = [
    "第一条　本合同用于盖章工具 Word 适配的技术验证，不代表任何真实约定。",
    "第二条　样本页面内容为确定性生成，用于核对分页、文字层与页面尺寸。",
    "第三条　验证方应在导出 PDF 后核对页数、正文完整性与签字区域位置。",
    "第四条　本页包含中文宋体正文、标点与阿拉伯数字 0123456789。",
    "第五条　如缺少字体，应记录替换情况，不得静默丢字。",
]
SIGN_LINE = "甲方（盖章）：____________　　乙方（盖章）：____________"


def _apply_cjk(style_font, name="宋体", size=12):
    style_font.name = name
    style_font.size = Pt(size)


def make_contract(path: Path, pages: int):
    """生成 pages 页的中文合同；每页固定 1 条标题行 + 5 条条款 + 分页符。"""
    doc = Document()
    _apply_cjk(doc.styles["Normal"].font)

    for page_idx in range(pages):
        heading = doc.add_paragraph()
        run = heading.add_run(f"{CONTRACT_TITLE}（第 {page_idx + 1} 页 / 共 {pages} 页）")
        run.bold = True
        run.font.size = Pt(16)
        for clause in CLAUSES:
            doc.add_paragraph(f"{clause}〔本页编号 {page_idx + 1}〕")
        doc.add_paragraph(SIGN_LINE)
        if page_idx != pages - 1:
            doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)

    doc.save(str(path))


def make_mixed_layout(path: Path):
    """A02 子集：页眉页脚 + 表格 + 横向页节，校验页面尺寸与不截断。"""
    doc = Document()
    _apply_cjk(doc.styles["Normal"].font)

    section = doc.sections[0]
    section.header.paragraphs[0].text = "页眉：盖章工具技术验证样本"
    section.footer.paragraphs[0].text = "页脚：第 1 页（纵向）"

    doc.add_heading("混合布局样本", level=1)
    doc.add_paragraph("下方为跨列合并表格，之后为横向页节。")
    table = doc.add_table(rows=3, cols=3)
    table.style = "Table Grid"
    for row in range(3):
        for col in range(3):
            table.cell(row, col).text = f"R{row + 1}C{col + 1}"
    table.cell(0, 0).merge(table.cell(0, 2))
    table.cell(0, 0).text = "表头（合并单元格）"

    # 横向节
    land = doc.add_section()
    land.orientation = WD_ORIENT.LANDSCAPE
    land.page_width, land.page_height = section.page_height, section.page_width
    land.footer.paragraphs[0].text = "页脚：第 2 页（横向）"
    doc.add_paragraph("本页为横向页，用于校验页面尺寸是否随节正确变化。")
    doc.add_paragraph(SIGN_LINE)

    doc.save(str(path))


def make_corrupt(path: Path):
    """非 docx 字节流，用于验证错误分类不崩溃。"""
    path.write_bytes(b"this is not a zip archive")


SAMPLES = {
    "contract-1p": lambda p: make_contract(p, 1),
    "contract-10p": lambda p: make_contract(p, 10),
    "contract-100p": lambda p: make_contract(p, 100),
    "mixed-layout": make_mixed_layout,
    "corrupt": make_corrupt,
}


def generate(out_dir: Path, names=None) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    names = names or ["contract-1p", "contract-10p", "mixed-layout", "corrupt"]
    made = {}
    for name in names:
        path = out_dir / f"{name}.docx"
        SAMPLES[name](path)
        made[name] = path
    return made


if __name__ == "__main__":
    import sys

    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent / "out" / "samples"
    for name, path in generate(target).items():
        print(f"{name}: {path}")
