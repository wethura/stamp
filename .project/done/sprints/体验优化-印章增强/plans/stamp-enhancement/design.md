# 技术设计：印章增强

## 风险验证结论

### PyMuPDF 旋转支持
- **问题**：`page.insert_image()` 是否支持任意角度旋转？
- **验证方式**：spike 代码
- **结论**：⚠️ 有限制 — `rotate` 参数只接受 0/90/180/270，不支持任意角度
- **影响**：需要改用 Pillow 预旋转图像，然后以旋转后的尺寸计算 rect 插入。spec.md 已明确此方案

### Pillow 旋转行为
- **问题**：`Image.rotate(expand=True)` 后图像尺寸变化和透明背景处理
- **验证方式**：spike 代码
- **结论**：✅ 可行 — `expand=True` 自动扩展画布保持完整图像，透明背景自动填充（alpha=0）。旋转后尺寸从 100x100 变为 142x142（45°时）
- **影响**：预览和导出时需要以旋转后的尺寸计算位置和包围盒

### tkinter 拖拽实现
- **问题**：章列表到预览区的拖拽是否可行？
- **验证方式**：spike 代码
- **结论**：✅ 可行 — 通过 `Toplevel(overrideredirect=True)` 创建浮动窗口，绑定 `<B1-Motion>` 跟随鼠标，释放时检测是否在目标区域内
- **影响**：需要处理拖拽开始、移动、释放三个事件，以及跨窗口坐标转换

### Backspace/右键删除
- **问题**：Canvas 上的 Backspace 和右键菜单绑定
- **验证方式**：spike 代码
- **结论**：✅ 可行 — `<BackSpace>` 绑定到 Canvas 或根窗口，右键通过 `<Button-2>`(macOS) 和 `<Button-3>`(Win/Linux) 触发菜单

## 关键技术决策

- **旋转实现**：Pillow 预旋转 + PyMuPDF 无旋转插入 — PyMuPDF 不支持任意角度旋转，必须在 Python 层预处理
- **拖拽实现**：自定义浮动窗口方案 — tkinter 无内置跨控件 DND，需手动实现
- **实例存储**：JSON 文件跟文档走 — 配置与文档生命周期一致

## 依赖与结构

### 核心依赖
- Pillow ≥ 8.0.0（旋转、透明度）
- PyMuPDF ≥ 1.18.0（PDF 插入，注意 rotate 参数限制）
- tkinter（拖拽、右键菜单）

### 模块结构

```
processing/
  stamp_manager.py      # StampTemplate 管理（全局）
  stamp_instance.py     # StampInstance 管理（跟文档）
  stamp.py              # apply_opacity, apply_rotation
ui/
  controls_panel.py     # 章列表（模板库）+ 编辑区域
  preview_canvas.py     # 实例显示 + 拖拽 + 删除
```

### 接口设计

```python
# processing/stamp_instance.py
@dataclass
class StampInstance:
    instance_id: str
    template_id: str
    page_index: int
    pos_x: float
    pos_y: float
    size_ratio: float
    rotation: float = 0.0
    opacity: float = 1.0

class StampInstanceManager:
    def __init__(self, doc_path: str)
    def add_instance(self, template_id: str, page_index: int) -> StampInstance
    def remove_instance(self, instance_id: str) -> bool
    def update_instance(self, instance_id: str, **kwargs) -> Optional[StampInstance]
    def get_page_instances(self, page_index: int) -> List[StampInstance]
    def save(self)
    def load(self)

# processing/stamp.py
def apply_rotation(img: Image.Image, angle: float) -> Image.Image:
    """Rotate image around center, expand canvas, preserve transparency."""

# ui/preview_canvas.py
class PreviewCanvas:
    # New methods
    def add_instance(self, instance: StampInstance, template: StampTemplate)
    def remove_selected_instance(self)
    def on_instance_selected(self, instance_id: str)
    def on_instance_dragged(self, instance_id: str, pos_x: float, pos_y: float)
```
