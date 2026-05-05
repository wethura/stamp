# 印章增强

## 技术方向

- **架构选择**：StampData 拆分为 StampTemplate（纯模板）+ StampInstance（页级配置）。模板全局持久化，实例跟文档走
- **技术栈**：Python + tkinter + Pillow + PyMuPDF
- **关键技术决策**：
  - 实例配置存储在文档同级目录的 `.stamp-config.json` 中，换电脑/发文件时配置不丢失
  - 旋转使用 Pillow `Image.rotate()`，以图像中心为旋转点，透明背景填充
  - 页面方向根据宽高比自动判断，印章大小比例按方向分别计算

## 功能需求

### 1. 数据模型重构

- `StampTemplate`：id, name, image_base64（纯元数据，全局持久化到 ~/.stamp_tool）
- `StampInstance`：instance_id, template_id, page_index, pos_x, pos_y, size_ratio, rotation, opacity（页级配置，跟文档走）
- 同一模板可在同一页创建多个实例，每个实例独立配置

### 2. 章列表交互

- 章列表作为「模板库」，显示所有 StampTemplate
- 双击模板或拖拽到预览区 → 在当前页创建实例
- 模板本身不再直接参与盖章，需实例化后才生效

### 3. 预览区交互

- 显示当前页的所有 StampInstance
- 点击实例选中 → 进入编辑状态
- 拖拽实例调整位置
- Backspace 键删除选中实例
- 右键菜单：删除

### 4. 编辑区域

- 显示「正在编辑「章A」- 第3页实例」
- 大小滑块：5%~80%
- 透明度滑块：0%~100%
- 旋转滑块/输入框：0°~360°
- 修改只影响当前实例

### 5. 旋转支持

- `StampInstance` 增加 `rotation: float = 0.0`（0~360）
- 预览渲染：Pillow `Image.rotate(angle, expand=True, resample=Image.BICUBIC)`
- 旋转中心为图像中心，旋转后保持位置不变
- 导出时：预旋转图像后插入

### 6. 纵横页面适配

- 页面加载时识别方向：宽高比 > 1 为横页，< 1 为纵页
- 印章大小比例基于当前页实际尺寸计算
- 混合方向文档每页独立处理

### 7. 导出

- 每页按自己的实例配置盖章
- 同一页多个实例按顺序叠加
- 支持 PDF/图片/Excel

## 非功能需求

- 性能：无特殊要求
- 安全：无特殊要求
- 数据：实例配置 schema 变更，不保留旧数据兼容
- 兼容性：无特殊要求
