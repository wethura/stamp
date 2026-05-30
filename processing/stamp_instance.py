"""章实例管理器 - 管理页级章实例配置，支持 JSON 持久化"""
import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import List, Optional


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


def _build_config_path(doc_path: str) -> str:
    """根据文档路径生成配置文件路径：.<文件名>.stamp-config.json"""
    dirname = os.path.dirname(doc_path)
    basename = os.path.basename(doc_path)
    return os.path.join(dirname, f".{basename}.stamp-config.json")


class StampInstanceManager:
    """章实例管理器 - 支持持久化到文档同级 .stamp-config.json"""

    def __init__(self, doc_path: str = ""):
        self._doc_path = doc_path
        self._config_path = _build_config_path(doc_path) if doc_path else ""
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

    def save(self):
        """将所有实例序列化并写入文档同级配置文件"""
        if not self._config_path:
            return
        data = {"instances": [asdict(inst) for inst in self._instances]}
        with open(self._config_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def load(self):
        """从文档同级配置文件读取并反序列化实例列表"""
        if not self._config_path or not os.path.exists(self._config_path):
            return
        with open(self._config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self._instances = [StampInstance(**item) for item in data.get("instances", [])]
