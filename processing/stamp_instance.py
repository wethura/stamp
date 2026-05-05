"""章实例管理器 - 管理页级章实例配置（纯内存）"""
from dataclasses import dataclass
from typing import List, Optional
from datetime import datetime


@dataclass
class StampInstance:
    """章实例 - 每页/每位置的独立配置"""
    instance_id: str
    template_id: str
    page_index: int
    pos_x: float = 0.7
    pos_y: float = 0.7
    size_ratio: float = 0.2
    rotation: float = 0.0
    opacity: float = 1.0


class StampInstanceManager:
    """章实例管理器 - 纯内存 CRUD，不落盘"""

    def __init__(self):
        self._instances: List[StampInstance] = []

    def add_instance(self, template_id: str, page_index: int) -> StampInstance:
        """添加新实例到指定页面"""
        instance_id = datetime.now().strftime("%Y%m%d%H%M%S%f")
        instance = StampInstance(
            instance_id=instance_id,
            template_id=template_id,
            page_index=page_index
        )
        self._instances.append(instance)
        return instance

    def remove_instance(self, instance_id: str) -> bool:
        """删除实例"""
        for i, instance in enumerate(self._instances):
            if instance.instance_id == instance_id:
                self._instances.pop(i)
                return True
        return False

    def update_instance(self, instance_id: str,
                        pos_x: Optional[float] = None,
                        pos_y: Optional[float] = None,
                        size_ratio: Optional[float] = None,
                        rotation: Optional[float] = None,
                        opacity: Optional[float] = None) -> Optional[StampInstance]:
        """更新实例配置"""
        for instance in self._instances:
            if instance.instance_id == instance_id:
                if pos_x is not None:
                    instance.pos_x = pos_x
                if pos_y is not None:
                    instance.pos_y = pos_y
                if size_ratio is not None:
                    instance.size_ratio = size_ratio
                if rotation is not None:
                    instance.rotation = rotation
                if opacity is not None:
                    instance.opacity = opacity
                return instance
        return None

    def get_page_instances(self, page_index: int) -> List[StampInstance]:
        """获取指定页面的所有实例"""
        return [i for i in self._instances if i.page_index == page_index]

    def get_instance(self, instance_id: str) -> Optional[StampInstance]:
        """获取单个实例"""
        for instance in self._instances:
            if instance.instance_id == instance_id:
                return instance
        return None

    def list_instances(self) -> List[StampInstance]:
        """获取所有实例"""
        return self._instances.copy()
