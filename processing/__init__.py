"""文档处理模块

注册所有可用的文档处理器。
"""
from processing.registry import HandlerRegistry
from processing.handlers import PDFHandler, ImageHandler, ExcelHandler
from processing.stamp import load_stamp, scale_stamp

# 注册处理器（顺序决定文件对话框中的显示顺序）
HandlerRegistry.register(PDFHandler)
HandlerRegistry.register(ImageHandler)
HandlerRegistry.register(ExcelHandler)

__all__ = [
    'HandlerRegistry',
    'PDFHandler',
    'ImageHandler',
    'ExcelHandler',
    'load_stamp',
    'scale_stamp',
]
