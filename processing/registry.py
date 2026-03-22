"""文档处理器注册表"""
from typing import List, Type, Optional, Set, Tuple
from processing.base import DocumentHandler


class HandlerRegistry:
    """处理器注册表

    使用注册机制实现处理器的动态发现和选择。
    新增格式只需创建 Handler 类并注册即可。
    """

    _handlers: List[Type[DocumentHandler]] = []

    @classmethod
    def register(cls, handler_class: Type[DocumentHandler]) -> None:
        """注册处理器

        Args:
            handler_class: 处理器类（不是实例）
        """
        if handler_class not in cls._handlers:
            cls._handlers.append(handler_class)

    @classmethod
    def get_handler(cls, path: str) -> Optional[DocumentHandler]:
        """根据文件路径获取合适的处理器

        Args:
            path: 文件路径

        Returns:
            处理器实例，如果没有匹配则返回 None
        """
        for handler_class in cls._handlers:
            if handler_class.can_handle(path):
                return handler_class()
        return None

    @classmethod
    def all_extensions(cls) -> Set[str]:
        """获取所有支持的扩展名

        Returns:
            扩展名集合
        """
        result = set()
        for handler_class in cls._handlers:
            result.update(handler_class.extensions())
        return result

    @classmethod
    def get_file_filters(cls) -> List[Tuple[str, str]]:
        """生成文件对话框的过滤器

        Returns:
            过滤器列表，如 [("PDF 文件", "*.pdf"), ...]
        """
        filters = []
        # 按处理器分组
        for handler_class in cls._handlers:
            exts = handler_class.extensions()
            # 生成 "*.pdf" "*.PDF" 格式（macOS 兼容）
            ext_patterns = " ".join(f"*{ext}" for ext in exts)
            filters.append((handler_class.display_name(), ext_patterns))

        # 添加"所有支持的文件"过滤器
        all_exts = cls.all_extensions()
        all_patterns = " ".join(f"*{ext}" for ext in sorted(all_exts))
        filters.insert(0, ("所有支持的文件", all_patterns))

        return filters

    @classmethod
    def get_output_filter(cls, handler: DocumentHandler) -> Tuple[str, str]:
        """获取输出文件过滤器

        Args:
            handler: 当前使用的处理器

        Returns:
            (显示名称, 过滤器模式)
        """
        ext = handler.default_output_extension()
        name = handler.display_name()
        return (name, f"*{ext}")
