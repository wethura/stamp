# 兼容性验证记录（P0.6）

每行一条真实环境记录。状态口径：**通过 / 条件支持 / 未验证 / 不可用**。
证据目录：`scripts/word_probe/out/<时间戳>/`（report.md / report.json / PDF 与首屏截图）。
未在表中出现的平台组合一律视为「未验证」，不得笼统宣称「支持 WPS / 支持 Word」。

## macOS（Apple Silicon）

| 日期 | OS | CPU | 应用/Python | 引擎及版本 | 接口方式 | 样本 | 结论 | 限制与备注 | 证据 |
|---|---|---|---|---|---|---|---|---|---|
| 2026-09-14 | macOS 26.6.2 (25G83) | arm64 | 源码运行 / Python 3.10 | LibreOffice 26.2.5.2（官方 .app + homebrew soffice） | `soffice --headless --convert-to pdf`，独立 UserInstallation | contract-1p / contract-10p / contract-100p / mixed-layout / corrupt | **通过**（见下注） | 损坏 .docx 会被 Text 滤镜当纯文本导入 → 应用层必须前置校验 zip 文件头；横向页节尺寸正确翻转（792×612pt）；文字层全程保留 | `out/*/report.md` |
| 2026-09-14 | macOS 26.6.2 (25G83) | arm64 | 源码运行 / Python 3.10 | Microsoft Word 16.112.4（Microsoft 365 订阅版 .app） | JXA / Apple Events（osascript） | contract-1p | **条件支持 → 待人工复核** | Apple Events 通路可用（running/quit 正常应答）；存在首启/模态弹窗（登录、激活或文件访问确认）时 open/save 全部 -1712 超时，quit 被 -128 取消。需人工完成/关闭弹窗后复测；打包 .app 的 TCC 授权未验证 | `out/20260914-015144/report.md` 及逐步诊断记录 |
| 2026-09-14 | macOS 26.6.2 (25G83) | arm64 | 源码运行 / Python 3.10 | Microsoft Word 16.112.4 | JXA 分阶段脚本（ensure-ready / open+save+close / quit） | contract-1p 复测 ×2 | **仍受阻（同一原因）** | 分阶段定位成功：ensure-ready 与就绪等待通过，卡点稳定复现在 open/save；向 Word 沙盒容器目录（必定可写）保存同样 -1712，排除「纯沙盒写路径」单一解释；quit 被 -128 取消证实模态窗仍在前台。已排除：自动化权限（-1743 未出现）。待人工处理弹窗后第三轮复测 | 会话诊断记录（quit -128 / open -1712 复现步骤） |
| 2026-09-14 | macOS 26.6.2 (25G83) | arm64 | 源码运行 / Python 3.10 | Microsoft Word 16.112.4 | JXA 分阶段 + MER 自动退出 | contract-1p 复测 | **找到根因，saveAs 单点待复核** | 根因确认：**Microsoft Error Reporting（Word 附带崩溃报告器）的模态报告窗**阻塞了全部 Apple Events——强制结束它之后 `open` 立即恢复响应。但 open→**saveAs**→close 链路在 saveAs 一步仍挂起（timeout 60s 强杀），且 `timeout` 无法中断挂起的 osascript；saveAs 触发的对话框内容需肉眼确认（疑为文件访问/格式确认类面板）。引擎已加入 MER 自动检测退出；下一步：屏幕前确认 saveAs 弹窗内容后复测 | 会话诊断记录（MER pgrep 命中、清掉后 open exit=0、saveAs 挂起复现） |
| 2026-09-14 | macOS 26.6.2 (25G83) | arm64 | 源码运行 / Python 3.10 | WPS Office 12.1.28492 (build 28492) | 未调用（加载项+本地桥接候选，见 spec S5/S6） | — | **未验证 → 手动路径** | 已检测到客户端；macOS 自动化需加载项部署验证，未部署前仅提供「在 WPS 中导出 PDF 后拖入本工具」 | 引擎探测输出 |

### LibreOffice（macOS）样本明细（2026-09-14）

| 样本 | 期望 | 实测 | 判定 |
|---|---|---|---|
| contract-1p | 1 页，含「第五条」 | 1 页，文字层保留，612×792pt | ✅ |
| contract-10p | 10 页 | 10 页，首末页标记文字齐全 | ✅ |
| contract-100p | 100 页 | 100 页，1.79s，文字层保留 | ✅ |
| mixed-layout | 2 页，横/纵节尺寸正确，表格不截断 | 2 页，纵向 612×792pt + 横向 792×612pt | ✅ |
| corrupt（非 zip 字节流） | 引擎报错 | **被当纯文本成功导入** → 判定探测 FAIL，要求应用层前置校验 | ⚠️ 设计修正项 |

corrupt 样本的教训已固化为设计约束：**进入任何引擎前，先用 zip 中央目录/`[Content_Types].xml` 校验 DOCX 文件头**，不依赖引擎自身报错（对应验收样本 A04/A05）。

## Windows（x64）

| 日期 | OS | 引擎 | 结论 | 备注 |
|---|---|---|---|---|
| — | 未验证 | Word COM / WPS COM | **未验证** | spec P0.2 待有 Windows 环境时执行 |

## Linux

| 日期 | OS | 引擎 | 结论 | 备注 |
|---|---|---|---|---|
| — | 未验证 | LibreOffice / WPS 加载项 | **未验证** | spec P0.4，保持实验性 |

## 记录口径提醒

- 引擎「探测到」≠「转换成功」；必须附样本编号与结果文件路径。
- 授权/登录状态、字体集未记录的行，补齐前不得升级结论。
- 源码运行通过不等于打包 .app/.exe 通过；打包验收单独一行记录。
