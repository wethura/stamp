"""章管理器 - 管理多个章的持久化存储"""
import json
import base64
import os
import tempfile
from dataclasses import dataclass, asdict
from itertools import count
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
        self._id_seq = count(1)
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
        temporary_path = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8",
                                             dir=self.config_dir, delete=False) as f:
                temporary_path = f.name
                json.dump([asdict(s) for s in self._stamps], f, ensure_ascii=False, indent=2)
            os.replace(temporary_path, self.data_file)
        finally:
            if temporary_path and os.path.exists(temporary_path):
                os.unlink(temporary_path)

    def list_stamps(self) -> List[StampData]:
        """获取所有章"""
        return self._stamps.copy()

    def add_stamp(self, name: str, img: Image.Image) -> StampData:
        """添加新章模板"""
        # 与 StampInstanceManager 相同：低时钟分辨率平台连续添加会撞 id
        stamp_id = f"{datetime.now().strftime('%Y%m%d%H%M%S%f')}-{next(self._id_seq)}"

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

    def update_stamp(self, stamp_id: str, name: Optional[str] = None,
                     image: Optional[Image.Image] = None) -> Optional[StampData]:
        """更新章模板信息"""
        for stamp in self._stamps:
            if stamp.id == stamp_id:
                old_name, old_image = stamp.name, stamp.image_base64
                encoded_image = None
                if image is not None:
                    buf = io.BytesIO()
                    image.save(buf, format="PNG")
                    encoded_image = base64.b64encode(buf.getvalue()).decode("utf-8")
                if name is not None:
                    stamp.name = name
                if encoded_image is not None:
                    stamp.image_base64 = encoded_image
                try:
                    self._save()
                except Exception:
                    stamp.name, stamp.image_base64 = old_name, old_image
                    raise
                return stamp
        return None

    def delete_stamp(self, stamp_id: str) -> bool:
        """删除章"""
        for i, stamp in enumerate(self._stamps):
            if stamp.id == stamp_id:
                self._stamps.pop(i)
                try:
                    self._save()
                except Exception:
                    self._stamps.insert(i, stamp)
                    raise
                return True
        return False

    def get_stamp(self, stamp_id: str) -> Optional[StampData]:
        """获取单个章"""
        for stamp in self._stamps:
            if stamp.id == stamp_id:
                return stamp
        return None
