# 功能：文档盖章

## 概述
支持对 PDF、图片、Excel 文件添加印章图片，可调整印章的位置、大小、旋转角度和透明度。

## 支持的文档类型

| 类型 | 扩展名 | 处理器 |
|------|--------|--------|
| PDF | .pdf | PDFHandler (PyMuPDF) |
| 图片 | .png, .jpg, .jpeg, .bmp, .tiff | ImageHandler (Pillow) |
| Excel | .xlsx, .xls | ExcelHandler (openpyxl) |

## 印章参数
- 位置：X/Y 坐标（基于页面左下角）
- 大小：缩放比例
- 旋转：角度（0-360）
- 透明度：0-100%

## 导出
- 保持原格式输出
- 默认输出路径：原文件名 + `_stamped` 后缀
