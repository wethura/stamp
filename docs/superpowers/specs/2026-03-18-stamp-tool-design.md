# Stamp Tool — Design Spec

**Date:** 2026-03-18
**Status:** Draft

## Context

用户需要一个 Windows 桌面工具，将印章（JPG/PNG）盖到原始文件（PDF 或图片）上，输出为 PDF。核心需求：自动去除 JPG 章的白底、可拖拽调整章的位置、可调整章的大小、PDF 多页时用户自选盖章页码。

---

## Architecture

三层结构，保持简洁：

```
UI Layer (tkinter)
    ↓
Controller (app.py) — 持有所有状态
    ↓
Processing Layer (Pillow + PyMuPDF)
```

- **UI Layer**: 渲染窗口、预览画布、控件，触发事件，不直接操作文件
- **Controller**: 持有应用状态（文档、章图像、位置比例、大小比例、选中页码），协调 UI 与处理层
- **Processing Layer**: 纯函数，无 tkinter 依赖，可独立测试

---

## Tech Stack

| 用途 | 库 |
|------|-----|
| GUI | tkinter（Python 内置） |
| PDF 处理 | PyMuPDF (fitz) >= 1.23.0 |
| 图像处理 | Pillow >= 10.0.0 |
| 打包 | PyInstaller → .exe |

**依赖极简**：`requirements.txt` 只有 `pymupdf` 和 `pillow`。

---

## UI Layout

```
+--------------------------------------------------+
|  [打开文档]  [打开章]              [导出 PDF]    |  ← 工具栏
+---------------------------+----------------------+
|                           |  盖章页码:           |
|                           |  (滚动列表)          |
|   预览画布                |  ☑ 第1页             |
|                           |  ☑ 第2页             |
|   显示当前预览页内容       |  ☐ 第3页             |
|   章图像叠加其上           |  ...                 |
|   章可鼠标拖拽移动         |  (图片输入时隐藏)    |
|                           |                      |
|                           |  章大小:             |
|                           |  [====滑块====]      |
|                           |  比例: [100]% (相对页宽)|
|                           |                      |
|                           |  预览页: [< 1/3 >]   |
+---------------------------+----------------------+
|  状态栏                                          |
+--------------------------------------------------+
```

---

## Key Design Decisions

### 位置存储：比例值（锚点为章的左上角）
章的位置以页面宽高的比例（0.0~1.0）存储，锚点为章图像的**左上角**。默认右下角放置时，初始值为 `(1.0 - stamp_w_ratio, 1.0 - stamp_h_ratio)`，确保章完整显示在页面内。拖拽时自动 clamp，防止章超出页面边界。

### 大小存储：相对页面宽度的比例
`stamp_size_ratio` 表示章宽度占页面宽度的比例（默认 0.2，即页宽的 20%）。章高度按原始宽高比自动计算。滑块范围 5%~80%。

### 白底去除规则
- **JPG 输入**：自动执行 BFS 漫水填充去白底
- **PNG 输入**：跳过去白底（PNG 通常已有透明通道）
- **RGBA PNG**：直接使用，不修改已有透明度
- BFS 从四角出发，替换近白色像素（R>225 且 G>225 且 B>225，且 A==255）为透明

### 章序列化格式
处理后的章图像（RGBA PIL Image）在传给 PyMuPDF `insert_image` 前，统一序列化为 **PNG bytes**，以保留透明通道。

### 图片输入 → PDF 输出
当输入为图片文件时：
- 视为单页文档，隐藏页码选择面板
- 导出时：创建新 `fitz.Document`，用 `page.insert_image()` 将原图插入为第一页，再叠加章，保存为 PDF

### 输出路径
点击"导出 PDF"时弹出文件保存对话框（`tkinter.filedialog.asksaveasfilename`），默认文件名为 `原文件名_stamped.pdf`。

### 无页码选中时的导出行为
若用户未选中任何页码，导出按钮点击时弹出警告对话框："请至少选择一页盖章"，阻止导出。

### 大页码列表
页码复选框放在带滚动条的 `tkinter.Frame` 中，支持 100+ 页的 PDF。

### 拖拽实现：tkinter Canvas 事件
```python
canvas.tag_bind(stamp_item, "<ButtonPress-1>", on_drag_start)
canvas.tag_bind(stamp_item, "<B1-Motion>", on_drag_move)
canvas.tag_bind(stamp_item, "<ButtonRelease-1>", on_drag_end)
```
位置和大小设置为**全局**（所有页共用同一位置和大小），预览页切换只改变背景页面内容。

---

## Data Flow

```
[打开文档]
  → fitz.open() (PDF) 或 Pillow.open() (图片)
  → PDF: 渲染第1页为 PIL Image，显示页码复选框
  → 图片: 转为 PIL Image，隐藏页码面板
  → 显示在画布

[打开章]
  → Pillow.open()
  → 若为 JPG (非 RGBA): remove_white_background() → RGBA PIL Image
  → 若为 PNG: 直接使用（convert("RGBA")）
  → 按 stamp_size_ratio 缩放
  → 计算默认右下角位置 position_ratio
  → 合成预览 → 刷新画布

[拖拽章]
  → 鼠标偏移换算为比例偏移 → 更新 position_ratio（clamp 到合法范围）
  → 重新合成预览 → 刷新画布（无文件 I/O）

[调整大小滑块]
  → 更新 stamp_size_ratio
  → 重新缩放章 → 重新计算 position_ratio（clamp）→ 刷新画布

[切换预览页]
  → 渲染对应页为 PIL Image → 合成章 → 刷新画布

[导出 PDF]
  → 若无选中页码: 弹出警告，返回
  → 弹出保存文件对话框
  → 若输入为图片: 创建新 fitz.Document，插入原图为第一页
  → 对每一页:
      若在 selected_pages 中:
        将章 PIL Image 序列化为 PNG bytes
        计算实际像素坐标 rect = position_ratio * page_size
        fitz.page.insert_image(rect, stream=png_bytes, overlay=True)
      否则: 原样保留
  → fitz.save(output_path)
  → 弹出成功提示
```

---

## File Structure

```
stamp/
├── main.py                  # 入口，~10行，启动 App
├── app.py                   # Controller：状态 + 协调
├── ui/
│   ├── __init__.py
│   ├── main_window.py       # 主窗口布局
│   ├── preview_canvas.py    # Canvas 组件 + 拖拽逻辑
│   └── controls_panel.py    # 右侧面板：滑块、复选框、按钮
├── processing/
│   ├── __init__.py
│   ├── document.py          # 加载 PDF/图片，渲染页面为 PIL Image
│   ├── stamp.py             # 加载章，去白底，缩放，序列化为 PNG bytes
│   └── exporter.py          # 合成章到 PDF 页面，保存
├── requirements.txt         # pymupdf>=1.23.0, pillow>=10.0.0
└── stamp.spec               # PyInstaller 打包配置
```

---

## Packaging

```bash
pyinstaller --onefile --windowed --name StampTool --collect-all pymupdf main.py
```

`--windowed` 在 Windows 上隐藏控制台窗口。`--collect-all pymupdf` 确保 PyMuPDF 的二进制依赖（fitz._fitz.pyd 及 MuPDF DLLs）被正确打包。

---

## Error Handling

| 场景 | 处理方式 |
|------|---------|
| 密码保护的 PDF | 弹出错误对话框："不支持加密 PDF" |
| 损坏的文件 | 弹出错误对话框："文件无法读取" |
| 无页码选中时导出 | 弹出警告："请至少选择一页盖章" |
| 章超出页面边界 | 自动 clamp，不报错 |

---

## Verification

1. 运行 `python main.py` 启动应用，确认窗口正常显示
2. 上传多页 PDF，确认页码复选框正确显示且可滚动
3. 上传白底 JPG 章，确认预览中白底被去除（背景透明）
4. 上传带透明通道的 PNG 章，确认透明度保留，不执行去白底
5. 拖拽章到不同位置，确认位置在导出 PDF 中正确（用 PDF 阅读器验证）
6. 调整章大小滑块，确认导出 PDF 中大小正确
7. 选择部分页码，确认只有选中页有章
8. 不选任何页码，点击导出，确认弹出警告
9. 上传图片文件（非 PDF），确认页码面板隐藏，可正常输出 PDF
10. 运行 `pyinstaller --onefile --windowed --name StampTool --collect-all pymupdf main.py`，确认 .exe 在无 Python 环境的 Windows 上可运行
