"""文档处理器模块"""
from processing.handlers.pdf_handler import PDFHandler
from processing.handlers.image_handler import ImageHandler
from processing.handlers.excel_handler import ExcelHandler
from processing.handlers.word_handler import WordHandler

__all__ = ['PDFHandler', 'ImageHandler', 'ExcelHandler', 'WordHandler']
