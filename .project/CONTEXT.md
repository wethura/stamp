## 已实现功能
- **[文档盖章]** - 支持 PDF、图片、Excel 文件添加印章 → [详情](.project/feats/document-stamp.md)
- **[体验优化]** - 删除按钮显式化、拖入文档、印章透明度 → [详情](.project/feats/experience-optimization.md)
- **[印章增强]** - 模板+实例分离、每页独立配置、旋转支持、持久化、拖拽创建 → [详情](.project/feats/印章增强.md)

## 开发工具

## 待推进规划
- **Word 文档适配（含 WPS）**：已形成执行规格，下一步 P0 跨平台转换验证；未实现，Linux 正式分发仍待评估。→ [执行规格](plans/word-support/spec.md) · [调研依据](research/word-support.md)

## 技术栈
Python + tkinter + PyMuPDF + Pillow + numpy + openpyxl + PyInstaller

## 技术决策
- 三层架构：UI / Controller / Processing
- Strategy Pattern 处理不同文档类型
- Registry Pattern 动态发现文档处理器
- 旋转：Pillow 预旋转 + PyMuPDF 无旋转插入（PyMuPDF rotate 参数只支持 0/90/180/270）
- 实例持久化：JSON 文件跟文档走（`.<文件名>.stamp-config.json`），每次实例变更自动保存，拖拽位置在 release 时保存
- 拖拽实现：tkinter 自定义浮动窗口方案（Toplevel + overrideredirect + 全局事件绑定）

<!-- sync-marker: 4994ae5 | 2026-05-30 -->
