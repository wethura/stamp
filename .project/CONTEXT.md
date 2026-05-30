## 当前 Sprint：体验优化-印章增强（完善中）
目标：提升 Stamp Tool 的日常使用体验 + 完善印章增强未实现功能

关键点：
- 实例配置持久化（关闭应用后配置不丢失）
- 模板拖拽到预览区创建实例

### 🚧 P3：印章增强完善（当前）
📋 [功能规格](.project/plans/stamp-enhancement/spec.md) | [测试规格](.project/plans/stamp-enhancement/dod.md) | [技术设计](.project/plans/stamp-enhancement/design.md)
- [x] 实例配置 JSON 持久化
- [x] 模板拖拽到预览区创建实例

## 进行中

## 已实现功能
- **[文档盖章]** - 支持 PDF、图片、Excel 文件添加印章 → [详情](.project/feats/document-stamp.md)
- **[体验优化]** - 删除按钮显式化、拖入文档、印章透明度 → [详情](.project/feats/experience-optimization.md)
- **[印章增强]** - 模板+实例分离、每页独立配置、旋转支持 → [详情](.project/feats/印章增强.md)

## 开发工具

## 技术栈
Python + tkinter + PyMuPDF + Pillow + numpy + openpyxl + PyInstaller

## 技术决策
- 三层架构：UI / Controller / Processing
- Strategy Pattern 处理不同文档类型
- Registry Pattern 动态发现文档处理器
- 旋转：Pillow 预旋转 + PyMuPDF 无旋转插入（PyMuPDF rotate 参数只支持 0/90/180/270）
- 实例数据：纯内存管理，不持久化到文件

<!-- sync-marker: 24628fe | 2026-05-05 -->
