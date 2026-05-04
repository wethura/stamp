## 当前 Sprint：体验优化
目标：提升 Stamp Tool 的日常使用体验

关键点：
- 删除章按钮更明显
- 支持拖入文档打开
- 印章透明度可调

### P1：印章增强（待规划）
- [ ] 旋转支持
- [ ] 纵+横页面公章支持
- [ ] 单独每页设置章

## 进行中

## 已实现功能
- **[文档盖章]** - 支持 PDF、图片、Excel 文件添加印章 → [详情](.project/feats/document-stamp.md)
- **[体验优化]** - 删除按钮显式化、拖入文档、印章透明度 → [详情](.project/feats/experience-optimization.md)

## 技术栈
Python + tkinter + PyMuPDF + Pillow + numpy + openpyxl + PyInstaller

## 技术决策
- 三层架构：UI / Controller / Processing
- Strategy Pattern 处理不同文档类型
- Registry Pattern 动态发现文档处理器

<!-- sync-marker: init | 2026-05-04 -->
