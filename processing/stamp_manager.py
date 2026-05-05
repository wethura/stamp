"""章管理器 - 管理多个章的持久化存储"""
import json
import base64
import os
from dataclasses import dataclass, asdict
from typing import List, Optional
from datetime import datetime
from PIL import Image
import io


@dataclass
class StampData:
    """章模板数据模型 - 只包含元数据，不包含页级配置"""
    id: str
    name: str
    image_base64: str
    created_at: str

    def get_image(self) -> Image.Image:
        """解码 base64 获取 PIL Image"""
        img_bytes = base64.b64decode(self.image_base64)
        return Image.open(io.BytesIO(img_bytes)).convert("RGBA")


class StampManager:
    """章管理器 - 负责章的 CRUD 和持久化"""

    def __init__(self, config_dir: Optional[str] = None):
        if config_dir is None:
            # 默认存储在用户目录下
            config_dir = os.path.join(os.path.expanduser("~"), ".stamp_tool")
        self.config_dir = config_dir
        self.data_file = os.path.join(config_dir, "stamps.json")
        self._stamps: List[StampData] = []
        self._load()

    def _load(self):
        """从文件加载章数据"""
        if not os.path.exists(self.data_file):
            self._stamps = []
            return
        try:
            with open(self.data_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                valid_fields = {'id', 'name', 'image_base64', 'created_at'}
                self._stamps = []
                for item in data:
                    filtered = {k: v for k, v in item.items() if k in valid_fields}
                    self._stamps.append(StampData(**filtered))
        except (json.JSONDecodeError, KeyError):
            self._stamps = []

    def _save(self):
        """保存章数据到文件"""
        os.makedirs(self.config_dir, exist_ok=True)
        with open(self.data_file, "w", encoding="utf-8") as f:
            json.dump([asdict(s) for s in self._stamps], f, ensure_ascii=False, indent=2)

    def list_stamps(self) -> List[StampData]:
        """获取所有章"""
        return self._stamps.copy()

    def add_stamp(self, name: str, img: Image.Image) -> StampData:
        """添加新章模板"""
        stamp_id = datetime.now().strftime("%Y%m%d%H%M%S%f")

        buf = io.BytesIO()
        img.save(buf, format="PNG")
        image_base64 = base64.b64encode(buf.getvalue()).decode("utf-8")

        stamp = StampData(
            id=stamp_id,
            name=name,
            image_base64=image_base64,
            created_at=datetime.now().isoformat()
        )
        self._stamps.append(stamp)
        self._save()
        return stamp

    def update_stamp(self, stamp_id: str, name: Optional[str] = None) -> Optional[StampData]:
        """更新章模板信息"""
        for stamp in self._stamps:
            if stamp.id == stamp_id:
                if name is not None:
                    stamp.name = name
                self._save()
                return stamp
        return None

    def delete_stamp(self, stamp_id: str) -> bool:
        """删除章"""
        for i, stamp in enumerate(self._stamps):
            if stamp.id == stamp_id:
                self._stamps.pop(i)
                self._save()
                return True
        return False

    def get_stamp(self, stamp_id: str) -> Optional[StampData]:
        """获取单个章"""
        for stamp in self._stamps:
            if stamp.id == stamp_id:
                return stamp
        return None
