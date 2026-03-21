"""文档处理器抽象基类定义"""
from abc import ABC, abstractmethod
from typing import Set, Tuple
from PIL import Image


class DocumentHandler(ABC):
    """文档处理器基类

    所有文档格式处理器必须实现此接口。
    采用策略模式，每种格式一个独立的处理器类。
    """

    @classmethod
    @abstractmethod
    def extensions(cls) -> Set[str]:
        """支持的文件扩展名

        Returns:
            扩展名集合，如 {'.pdf', '.PDF'}
        """
        pass

    @classmethod
    @abstractmethod
    def can_handle(cls, path: str) -> bool:
        """判断是否能处理该文件

        Args:
            path: 文件路径

        Returns:
            是否能处理
        """
        pass

    @classmethod
    @abstractmethod
    def display_name(cls) -> str:
        """显示名称

        Returns:
            用于 UI 显示的名称，如 'PDF 文档'
        """
        pass

    @abstractmethod
    def load(self, path: str) -> None:
        """加载文档

        Args:
            path: 文件路径
        """
        pass

    @abstractmethod
    def page_count(self) -> int:
        """获取页数/Sheet数

        Returns:
            页面数量
        """
        pass

    @abstractmethod
    def render_page(self, index: int, preview_width: int = 1600) -> Image.Image:
        """渲染指定页为图像

        用于预览显示。

        Args:
            index: 页面索引（从 0 开始）
            preview_width: 预览图像的目标宽度

        Returns:
            PIL.Image 对象
        """
        pass

    @abstractmethod
    def get_page_size(self, index: int) -> Tuple[float, float]:
        """获取页面原始尺寸

        Args:
            index: 页面索引

        Returns:
            (宽度, 高度) 元组
        """
        pass

    @abstractmethod
    def export_with_stamp(
        self,
        output_path: str,
        stamp_img: Image.Image,
        position_ratio: Tuple[float, float],
        stamp_size_ratio: float,
        selected_pages: Set[int]
    ) -> None:
        """导出带章的文档

        Args:
            output_path: 输出文件路径
            stamp_img: 印章图像（RGBA）
            position_ratio: 印章位置比例 (x, y)，范围 0.0~1.0
            stamp_size_ratio: 印章大小比例（相对于页面宽度）
            selected_pages: 选中的页面索引集合
        """
        pass

    @abstractmethod
    def default_output_extension(self) -> str:
        """默认输出扩展名

        Returns:
            扩展名，如 '.pdf' 或 '.xlsx'
        """
        pass

    @abstractmethod
    def close(self) -> None:
        """释放资源"""
        pass
