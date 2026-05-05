## 当前 Sprint：体验优化
目标：提升 Stamp Tool 的日常使用体验

关键点：
- 删除章按钮更明显
- 支持拖入文档打开
- 印章透明度可调

### ✅ P1：体验优化（已完成）
📋 [功能规格](.project/plans/experience-optimization/spec.md) | [测试规格](.project/plans/experience-optimization/dod.md)
- [x] 删除按钮显式化
- [x] 拖入文档打开
- [x] 印章透明度可调

### ✅ P2：印章增强（已完成）
📋 [功能规格](.project/done/sprints/体验优化-印章增强/plans/stamp-enhancement/spec.md) | [测试规格](.project/done/sprints/体验优化-印章增强/plans/stamp-enhancement/dod.md) | [技术设计](.project/done/sprints/体验优化-印章增强/plans/stamp-enhancement/design.md)
- [x] 数据模型重构（模板+实例分离）
- [x] 每页独立配置
- [x] 旋转支持
- [x] 纵横页面适配

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
