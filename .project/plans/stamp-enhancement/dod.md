# 印章增强 测试规格

## 功能测试

### 模板创建后可在列表中查看 {#template-create-list v1.0}

**前置条件：**
- 应用已启动
- 无现有章模板

**操作：**
1. 点击「导入新章」
2. 选择一张图片并确认
3. 输入名称「测试章」

**预期结果：**
- 章列表显示「测试章」缩略图
- 该模板可通过 `StampManager.list_stamps()` 获取

### 实例创建并关联到当前页 {#instance-create-page v1.0}

**前置条件：**
- 应用已启动
- 已打开一个 3 页 PDF
- 已导入 1 个章模板（章 A）
- 当前预览第 1 页

**操作：**
1. 双击章 A

**预期结果：**
- 第 1 页预览区域显示章 A 实例
- `StampInstanceManager.get_page_instances(0)` 返回 1 条记录
- 该实例的 `template_id` 等于章 A 的 ID
- 该实例的 `page_index` 等于 0

### 同一模板在同一页创建多个实例 {#same-template-multi-instance v1.0}

**前置条件：**
- 应用已启动
- 已打开文档
- 已导入章 A
- 当前预览第 1 页

**操作：**
1. 双击章 A（创建实例 1）
2. 再次双击章 A（创建实例 2）

**预期结果：**
- 第 1 页预览显示两个章 A 实例
- `get_page_instances(0)` 返回 2 条记录
- 两条记录的 `template_id` 相同但 `instance_id` 不同

### 切换页面显示不同实例 {#page-switch-instances v1.0}

**前置条件：**
- 应用已启动
- 已打开 2 页 PDF
- 已导入章 A
- 第 1 页有章 A 实例（位置 x=0.3, y=0.3）
- 第 2 页有章 A 实例（位置 x=0.7, y=0.7）

**操作：**
1. 从第 1 页切换到第 2 页

**预期结果：**
- 预览区域显示第 2 页的实例（位置 x=0.7, y=0.7）
- 第 1 页的实例不在预览中显示

### 拖拽实例调整位置 {#instance-drag-position v1.0}

**前置条件：**
- 应用已启动
- 已打开文档
- 第 1 页有章 A 实例（位置 x=0.5, y=0.5）

**操作：**
1. 在预览区拖拽该实例到右下角

**预期结果：**
- 实例位置更新（x > 0.5, y > 0.5）
- 该实例的 `pos_x` 和 `pos_y` 值已更新
- 其他页的同名实例位置不变

### Backspace 删除选中实例 {#backspace-delete-instance v1.0}

**前置条件：**
- 应用已启动
- 已打开文档
- 第 1 页有 2 个实例
- 实例 A 处于选中状态

**操作：**
1. 按 Backspace 键

**预期结果：**
- 实例 A 从预览区消失
- `get_page_instances(0)` 只返回 1 条记录
- 实例 B 仍显示

### 右键菜单删除实例 {#context-menu-delete v1.0}

**前置条件：**
- 应用已启动
- 已打开文档
- 第 1 页有 1 个实例

**操作：**
1. 右键点击该实例
2. 选择「删除」

**预期结果：**
- 该实例从预览区消失
- `get_page_instances(0)` 返回空列表

### 大小滑块只影响当前实例 {#size-slider-instance-only v1.0}

**前置条件：**
- 应用已启动
- 已打开 2 页 PDF
- 第 1 页和第 2 页各有章 A 实例
- 当前预览第 1 页
- 实例处于编辑状态

**操作：**
1. 将大小滑块从 20% 拖到 50%

**预期结果：**
- 第 1 页实例大小变为 50%
- 第 2 页实例大小仍为 20%
- 预览实时更新

### 透明度滑块只影响当前实例 {#opacity-slider-instance-only v1.0}

**前置条件：**
- 应用已启动
- 已打开 2 页 PDF
- 第 1 页和第 2 页各有章 A 实例
- 当前预览第 1 页
- 实例处于编辑状态

**操作：**
1. 将透明度滑块从 100% 拖到 50%

**预期结果：**
- 第 1 页实例透明度变为 50%
- 第 2 页实例透明度仍为 100%
- 预览实时更新

### 旋转滑块 0° 到 45° 预览更新 {#rotation-45-preview v1.0}

**前置条件：**
- 应用已启动
- 已打开文档
- 第 1 页有章 A 实例
- 实例处于编辑状态

**操作：**
1. 将旋转滑块从 0° 拖到 45°

**预期结果：**
- 预览区域印章旋转 45°
- 实例的 `rotation` 字段等于 45.0
- 印章中心位置保持不变

### 旋转 90° 预览和导出 {#rotation-90-export v1.0}

**前置条件：**
- 应用已启动
- 已打开 PDF 文档
- 第 1 页有章 A 实例，旋转 90°

**操作：**
1. 导出盖章文档

**预期结果：**
- 导出成功
- 导出的 PDF 中印章旋转 90°
- 印章中心位置与预览一致

### 横页识别和尺寸计算 {#landscape-page-size v1.0}

**前置条件：**
- 应用已启动

**操作：**
1. 打开一个横页 PDF（宽 > 高）

**预期结果：**
- 页面被识别为横页
- 印章大小基于页面宽度计算

### 混合方向文档每页独立 {#mixed-orientation-pages v1.0}

**前置条件：**
- 应用已启动
- 有一个混合方向 PDF（第 1 页纵页，第 2 页横页）
- 两页各有章 A 实例

**操作：**
1. 切换预览第 1 页和第 2 页

**预期结果：**
- 第 1 页印章大小基于纵页宽度
- 第 2 页印章大小基于横页宽度
- 两页印章视觉大小比例一致

### 导出时多实例叠加 {#export-multi-instance v1.0}

**前置条件：**
- 应用已启动
- 已打开 PDF 文档
- 第 1 页有 2 个章 A 实例（位置不同）

**操作：**
1. 导出盖章文档

**预期结果：**
- 导出成功
- 第 1 页 PDF 上有两个印章
- 两个印章位置与预览一致

### 导出时每页独立配置 {#export-per-page-config v1.0}

**前置条件：**
- 应用已启动
- 已打开 2 页 PDF
- 第 1 页有章 A 实例（大小 30%，位置左上）
- 第 2 页有章 A 实例（大小 50%，位置右下）

**操作：**
1. 导出盖章文档

**预期结果：**
- 导出成功
- 第 1 页印章大小 30%，位置左上
- 第 2 页印章大小 50%，位置右下

### 模板拖拽到预览区创建实例（需人工验证） {#template-drag-create-instance v1.0}

**前置条件：**
- 应用已启动
- 已打开一个 3 页 PDF
- 已导入 1 个章模板（章 A）
- 当前预览第 1 页

**操作：**
1. 在章列表中按住章 A 的缩略图
2. 拖拽到预览区
3. 释放鼠标

**预期结果：**
- 第 1 页预览区域显示章 A 实例
- `StampInstanceManager.get_page_instances(0)` 返回 1 条记录
- 该实例的 `template_id` 等于章 A 的 ID
- 该实例的 `page_index` 等于 0

**手动验证步骤：**
1. 启动应用，打开一个 PDF，导入章模板
2. 按住章列表中的模板缩略图
3. 拖拽到预览区，释放
4. 确认预览区出现印章实例

## 数据测试

### 实例 save/load 往返一致性 {#instance-save-load-roundtrip v1.0}

**前置条件：**
- `StampInstanceManager` 已初始化，关联文档路径 `/tmp/test/doc.pdf`
- 已添加 2 个实例：
  - 实例 A：template_id=t1, page_index=0, pos_x=0.2, pos_y=0.3, size_ratio=0.3, rotation=45.0, opacity=0.8
  - 实例 B：template_id=t2, page_index=1, pos_x=0.5, pos_y=0.5, size_ratio=0.5, rotation=0.0, opacity=1.0

**操作：**
1. 调用 `manager.save()`
2. 创建新的 `StampInstanceManager`（同一路径）
3. 调用 `new_manager.load()`
4. 查询 `new_manager.get_page_instances(0)` 和 `get_page_instances(1)`

**预期结果：**
- 实例 A 的所有字段与保存前一致（instance_id、template_id、page_index、pos_x、pos_y、size_ratio、rotation、opacity）
- 实例 B 的所有字段与保存前一致
- 两个实例的 instance_id 不变

### 实例持久化文件格式 {#instance-persist-file-format v1.0}

**前置条件：**
- `StampInstanceManager` 已初始化，关联文档路径 `/tmp/test/report.pdf`
- 已添加 1 个实例（任意配置）

**操作：**
1. 调用 `manager.save()`
2. 检查 `/tmp/test/` 目录下的文件

**预期结果：**
- 存在文件 `.report.pdf.stamp-config.json`（点号前缀 + 原文件名 + `.stamp-config.json`）
- 文件内容为合法 JSON
- JSON 顶层结构为 `{"instances": [...]}`

### 空实例列表保存 {#instance-save-empty v1.0}

**前置条件：**
- `StampInstanceManager` 已初始化，关联文档路径 `/tmp/test/empty.pdf`
- 未添加任何实例

**操作：**
1. 调用 `manager.save()`
2. 创建新的 `StampInstanceManager`（同一路径）
3. 调用 `new_manager.load()`

**预期结果：**
- `/tmp/test/` 下存在 `.empty.pdf.stamp-config.json`
- 文件内容为 `{"instances": []}`
- `new_manager.get_page_instances(0)` 返回空列表

### 文档移动后配置丢失 {#doc-move-config-lost v1.0}

**前置条件：**
- `StampInstanceManager` 已初始化，关联文档路径 `/tmp/test/doc.pdf`
- 已添加 1 个实例并调用 `save()`
- `/tmp/test/` 下存在 `.doc.pdf.stamp-config.json`

**操作：**
1. 将 `/tmp/test/doc.pdf` 移动到 `/tmp/other/doc.pdf`
2. 创建新的 `StampInstanceManager`，关联路径 `/tmp/other/doc.pdf`
3. 调用 `new_manager.load()`
4. 查询 `new_manager.get_page_instances(0)`

**预期结果：**
- `/tmp/other/` 下不存在 `.stamp-config.json` 文件
- `new_manager.get_page_instances(0)` 返回空列表
