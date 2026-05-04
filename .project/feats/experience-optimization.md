# 体验优化

## 功能概述

提升 Stamp Tool 的日常使用体验，包含三项改进：删除按钮显式化、拖入文档支持、印章透明度可调。

## 实现详情

### 删除章按钮显示优化

**问题**：原删除按钮使用 `place` 绝对定位在缩略图右上角，可能被遮挡或不易点击。

**实现**：
- `ui/controls_panel.py:228-232` — 改为显式「删除」文字按钮，位于章列表项底部
- `ui/controls_panel.py:262-279` — 点击后弹出 `messagebox.askyesno` 确认对话框
- 删除后同步更新选中状态和编辑状态（滑块重置为默认值）

### 拖入文档支持

**实现**：
- `ui/drop_target.py` — 提取公共拖放逻辑，支持 tkdnd 扩展和原生回退
- `ui/main_window.py:61` — `MainWindow` 和 `MainFrame` 均注册拖放目标
- `app.py:61-106` — `on_file_dropped()` 解析拖放数据，支持单文件、拒绝多文件、验证格式

**路径解析**：
- macOS: `<Drop>` 事件
- Windows/Linux: `<<Drop>>` 事件
- 多文件: `shlex.split()` 解析，提示「请每次拖入一个文件」

### 印章透明度效果

**实现**：
- `processing/stamp_manager.py:22` — `StampData` 新增 `opacity: float = 1.0` 字段
- `ui/controls_panel.py:100-111` — 编辑区域增加透明度滑块（0%~100%）
- `processing/stamp.py:57-66` — `apply_opacity()` 使用 Pillow alpha 通道乘法
- 预览和导出（PDF/图片/Excel）均应用相同透明度逻辑

**数据流**：
```
StampData.opacity → ControlsPanel._on_opacity_changed → StampManager.update_stamp()
                                              ↓
ControlsPanel.get_selected_stamps() → apply_opacity() → 预览/导出
```

## 测试覆盖

- `tests/test_controls_panel.py` — 删除按钮可见性、确认对话框、状态同步
- `tests/test_drop_support.py` — 支持/不支持文件、多文件拒绝、路径遍历
- `tests/test_opacity.py` — 默认值、50%效果、0%完全透明、持久化

## 技术决策

- 透明度使用 Pillow `Image.point()` 实现，避免 numpy 依赖增加
- 拖放使用 tkdnd 优先、原生回退的策略，最大化平台兼容性
- `StampSelection` 新增 `opacity` 字段显式传递，避免动态属性
