# Word 文档适配执行规格（含 WPS）

日期：2026-09-14。状态：规划完成，可启动 P0 技术验证；未实现，未进行跨平台实测。

本次用户要求补充 WPS 并形成执行文档。以下首版范围和数值为建议执行基线，不代表已逐项确认的产品承诺。P0 的结果决定实际启用哪些后端。既有调研见 [word-support.md](../../research/word-support.md)。

## 技术方向

- 保留 Python + tkinter + PyMuPDF 以及 UI / Controller / Processing 分层。
- 新增本地转换服务，接入 Microsoft Word、WPS、LibreOffice 等可替换后端；WordHandler 转换后委托 PDFHandler 预览和盖章。
- 同一会话只转换一次，预览和导出使用同一 PDF 快照。不能承诺不同引擎、字体环境生成完全一致的分页。
- 不使用自绘简化 Word 页面作为精确盖章基准。当前普通 PyMuPDF 不是 Word 排版引擎；官方将 Office 支持列于 Pro，不能只靠现有 fitz.open 实现 [S10]。

### 现有代码的实施影响

| 位置 | 当前行为 | 必要改动 |
|---|---|---|
| processing/base.py、registry.py | Handler 接口和类型注册 | 增加 WordHandler；输出类型名称与输入类型分离 |
| processing/handlers/__init__.py、processing/__init__.py | 处理器导入/注册 | 两处补齐新处理器 |
| app.py::_load_document | 同步加载全部页面，先关闭旧文档 | 后台转换、按需预览、成功后切换；失败保留旧会话 |
| app.py::_export_with_instances | 后续印章固定用 PDFHandler | 首版 PDF 路线可复用；保护目标文件，不顺带重构全部格式 |
| processing/stamp_instance.py | 当前章实例仅在内存保存 | 坐标绑定 PDF 快照；重新转换后重置，不新增跨会话持久化 |
| StampTool.spec / StampTool-win.spec | 两个平台构建入口 | 条件依赖、自动化资源和真实安装包验收 |

CONTEXT.md 中旧的章实例持久化描述与当前代码不一致，本方案以代码为准。仓库没有现成 Linux 构建规格，Linux 转换后端验证与完整应用分发需分开验收。

## 功能需求

### 首版范围

- 文件选择或拖入 `.docx`（含大写扩展名），预览、多页多章、旋转和透明度操作，输出 `原文件名-已盖章.pdf`，保留原始 Word。
- 探测可用本地转换引擎，提供选择、偏好记忆、取消、错误解释与手动 PDF 路径。
- 正式发布优先现有 Windows/macOS；Linux 同期评估转换能力，未通过 GUI 和打包验收前标记实验性。
- `.doc`、`.docm`、原生 `.wps`、可编辑 DOCX 输出、云转换、批量多文件和移动端不纳入首版。支持 WPS 作为引擎不等于支持 `.wps` 格式。

### 平台与 WPS 接入矩阵

| 平台/引擎 | 候选方式 | 启用条件及限制 |
|---|---|---|
| Windows / Word | COM 自动化 [S1] | 验证实际版本、激活状态、Python/Office 架构组合、已有进程与弹窗 |
| Windows / WPS | COM 优先；官方 kwps.application 自动化示例作为探测起点 [S3]，验证 PDF 导出 [S4] | 个人版/企业版分别验证对象注册、调用、授权和实例隔离；通过后与 Word 同级可选 |
| macOS / Word | JXA / Apple Events [S1] | 验证自动化权限、拒绝后恢复、Intel/Apple Silicon 和真实 .app [S7] |
| macOS / WPS | JS 加载项 + 本地桥接候选 [S5][S6] | 验证目标版本部署、PDF 导出、消息回传、离线运行和卸载；未通过提供手动 PDF 路径 |
| Linux / WPS | JS 加载项或厂商原生 SDK 候选 [S5][S6] | 按发行版/CPU/社区或企业版验证，明确 SDK 获取及分发条件；保持实验性 |
| 三平台 / LibreOffice | soffice 无界面转换及独立用户配置目录 [S2] | 验证安装位置、中文字体、分页、已有进程和超时清理 |

WPS 官方提供跨平台开发概述及 Document.ExportAsFixedFormat，但接口资料不能证明每个客户端发行版都支持从本工具调用。不能把 Windows COM 移植假设应用于 Mac/Linux，也不假设 WPS 支持 soffice 的命令行参数。

每个 WPS 组合记录：完整版本/构建号、个人或企业发行版、安装渠道、CPU、登录/授权状态、自动化对象或插件版本、部署步骤。若依赖特殊商业授权则标记条件支持，不将其作为普通用户首版前提。云端 WebOffice 是另一种接入方式，不纳入本地方案。

### 引擎选择与交互

1. 优先使用已保存且仍可用的用户选择；只有一个通过能力探测的引擎时自动使用。
2. 首次有多个可用引擎时，提示选择“平时编辑此文件的软件”，显示可用的 Word / WPS / LibreOffice 并记住选择。不固定把 WPS 排在 Word 后，也不凭 DOCX 元数据强制选择。
3. 显示“正在转换 Word 文档…”及取消按钮；无法获取真实进度时使用不定进度条。
4. 转换完成显示“将导出为 PDF，请核对分页和签字区域”，首屏就绪后即可盖章，其他页按需加载。
5. 转换失败提供“换一种转换方式”和“手动导入 PDF”。不静默换引擎后复用旧坐标。
6. 已有章时重新转换，提示“重新转换可能改变分页，继续后需重新放置印章”。成功取得新快照后才切换并清空章位置；失败保留旧会话。

| 异常 | 用户出口 |
|---|---|
| 仅安装 WPS，接口不可用 | “已检测到 WPS，当前版本暂不能自动转换。请在 WPS 中导出 PDF 后导入。” |
| 无可用引擎 | 提供受支持工具安装指引及手动 PDF 入口；首版不随应用捆绑办公软件 |
| macOS 自动化拒绝 | 解释需要允许 StampTool 控制办公软件，给出系统设置恢复指引或手动 PDF 路径 |
| 加密、损坏、超时 | 分别显示原因；首版不做密码输入，建议在原软件处理后导出 PDF |
| 源文件外部修改 | 当前会话使用已有快照；重新导入才读取新内容并重新放章 |

手动路径：“在 WPS/Word 中打开文件 → 导出为 PDF → 将 PDF 拖入本工具”。正常操作不展示 COM、插件端口等实现信息，诊断详情可包含版本与错误类别。

## 非功能需求

### 性能（拟定验收指标）

- 可能阻塞的转换和能力探测在受控后台任务执行，tkinter 更新只在主线程；PDF 对象不跨线程并发使用。
- 导入/取消后 200ms 内反馈界面状态；默认转换超时 120 秒，首次系统授权等待单独显示，不误报文件损坏。
- 取消后 1 秒内恢复操作；过期结果不得覆盖新会话。确认属于本任务的子进程应在 5 秒内结束；无法安全终止共享办公进程时放弃结果、延后清理，不能强杀用户进程。
- P0 测量 1/10/100 页样本冷/热启动、首屏耗时、峰值内存；P1 根据真实硬件和文档冻结性能预算，不承诺所有长文档固定耗时。

### 数据一致性

- 原文件不覆盖，不触发办公软件保存；使用工作副本转换，校验本工具未改变源文件。
- 会话记录源路径、工作副本指纹、引擎及版本、PDF 路径与页尺寸；坐标只关联该 PDF 快照，导出不得再次转换。
- 保留转换 PDF 的文字/矢量背景，不将整页截图化导出；字体替换和复杂排版差异须核对 [S8][S9]。
- 导出先写临时文件并校验可打开，再原子替换目标；失败不破坏已有输出文件，同名覆盖遵循保存对话框选择。
- 会话关闭清理源副本和 PDF；异常残留下次启动按应用专属目录清理，不删除其他软件或仍在运行任务的文件。

### 安全与依赖

- 本工具不上传文档；转换关闭宏执行、外链更新和源文件自动保存。无法满足的后端记录限制或不启用。
- 仅关闭本任务打开的文档；复用用户进程时不能调用全局 Quit，更不能按进程名批量杀 Word/WPS。
- 依赖按平台条件导入；macOS/Linux 不加载 Windows COM 模块。办公软件的激活联网与实际离线转换分别测试，不因本工具无上传就宣称全链路离线可用。
- 若采用 WPS 本地桥接，验证仅本机访问、随机会话凭证、受限输入/输出目录、请求超时和卸载恢复，不暴露通用脚本执行接口。

### 兼容性

- 优先验证 Windows 11 x64、macOS Intel/Apple Silicon；完整记录 OS/Python/PyInstaller/办公软件版本。源码运行通过不等于 .exe/.app 通过。
- Linux 优先 Ubuntu x86_64；麒麟/UOS/ARM64 独立建行，有真实环境和证据后才支持。Windows ARM64 及老系统同理。
- 检查中文宋体/仿宋/黑体需求、合法替代字体与字体缺失，不随意捆绑系统字体；无法可靠识别缺失字体时不宣称检测完整。

## 执行任务与阶段出口

开发负责 P0–P2，测试/维护者负责样本基准与平台复核，可由同一人承担。勾选任务必须附运行环境和证据。

### P0：技术验证（下一步直接执行）

- [ ] P0.1 新建 scripts/word_probe/ 最小探测/转换入口与合成样本，暂不接入 GUI；报告环境、引擎/版本、接口、授权、耗时、页数/尺寸、错误及清理结果。
- [ ] P0.2 优先 Windows WPS 个人版与可取得的企业版，再验证 Word；覆盖未启动、已打开未保存文档、Word/WPS 共存、未登录/已登录。取得不到的版本记“未验证”。
- [ ] P0.3 macOS 验证 Word 自动化及打包权限；单独验证 WPS 加载项本地 PDF 导出、桥接、部署/卸载和离线运行，不复用未经验证的 Word JXA 假设。
- [ ] P0.4 三平台验证 LibreOffice；Linux WPS 调查并在可取得的环境验证加载项/SDK。缺少企业 SDK 不阻塞其他后端。
- [ ] P0.5 完成下方样本矩阵，保存源软件手动 PDF 基准、自动转换 PDF、截图和差异结论。
- [ ] P0.6 产出同目录 design.md 和 compatibility.md：按平台给出通过/条件支持/未验证/不可用结论及理由，不能笼统写“支持 WPS”。

出口：每个启用后端通过“探测 → 转换 → PDF 校验 → 安全清理”，基本合同布局可接受，已有文档不受影响。WPS 三个平台均形成结论，即使是“手动路径”。Windows/macOS 各至少一个后端通过即可继续首版；其他后端保持禁用。

### P1：冻结设计和测试规格（依赖 P0）

- [ ] P1.1 design.md 明确 probe/convert/cancel/cleanup 契约、状态机、进程归属、临时目录、错误分类及技术风险结论。
- [ ] P1.2 新建同目录 dod.md，将下方用例映射到自动测试/平台手工测试，填入真实支持版本及性能预算。
- [ ] P1.3 实施前同步 .project/SPEC.md 的 DOCX 输入、PDF 输出和外部软件依赖边界；Linux 升级正式分发时再同步平台范围。

出口：高风险接口已验证或明确排除，spec/design/dod 一致。先技术验证，再测试规格，再产品实现。

### P2：实现最小闭环（依赖 P1）

- [ ] P2.1 按 dod.md 先写失败/取消/输出一致性测试，再实现转换服务和已验证后端。
- [ ] P2.2 实现 WordHandler、两处注册、PDF 委托和输出过滤器。
- [ ] P2.3 实现后台转换、按需预览、成功后会话切换和过期结果丢弃。
- [ ] P2.4 实现引擎选择/记忆、WPS 不可用提示、权限恢复和手动 PDF 入口。
- [ ] P2.5 完成多章导出与临时/目标文件保护，不扩展为全格式导出重构。

### P3：平台验收（依赖 P2）

- [ ] P3.1 在干净用户环境验证 Windows/macOS 真实安装包、缺失依赖、权限拒绝及恢复。
- [ ] P3.2 回归现有 PDF、图片、Excel、印章库；区分既有问题与新增问题。
- [ ] P3.3 更新兼容名单和用户说明，列清 WPS 版本条件、安装要求及替代流程。
- [ ] P3.4 Linux 仅转换通过则保持实验性；正式发布须补 GUI、中文字体、拖入、打包和安装/卸载验收。

## 验收样本与标准

| 编号 | 场景 | 通过条件 |
|---|---|---|
| A01 | Word/WPS 分别制作的 1/10/100 页中文合同 | 与各自软件手动导出的 PDF 比较；记录页数、换行和签字区差异，缺字/丢内容不可接受 |
| A02 | 跨页表格、合并单元格、页眉页脚、分节、横竖页、浮动图形 | 无截断，页面尺寸正确；分页差异逐项解释并限定适用范围 |
| A03 | 同页/跨页多章、旋转/透明度、边缘放置 | 预览与导出同源；统一 144 DPI 渲染，印章预期边界误差 ≤2 像素，背景不重排 |
| A04 | 缺字体、中文/空格/长路径、只读源目录 | 不崩溃；清楚解释失败或提示核对；不要求源目录可写 |
| A05 | 加密/损坏/无引擎/WPS 接口不可用 | 原因可区分，手动路径可达，旧会话仍可操作 |
| A06 | 取消/超时/连续导入 A 和 B/关闭应用 | UI 响应，A 晚到结果不覆盖 B，临时资源最终清理 |
| A07 | 已有未保存的 Word/WPS 文档 | 成功/失败/取消均不改变其内容、窗口或未保存状态；源文件不被修改 |
| A08 | Word/WPS 共存，指定 WPS，更换引擎 | 尊重选择，新快照成功后重置章位置，不静默沿用旧坐标 |
| A09 | 断网、个人/企业、未登录、插件未部署 | 记录真实可用性与条件，不把安装检测当作转换成功 |
| A10 | macOS 拒绝/重新授权，Intel/ARM .app | 可恢复，记录真实包测试；无样机不标通过 |
| A11 | 导出中断、目标已存在 | 失败不破坏已有文件，不覆盖 DOCX；成功输出页数/尺寸与快照一致 |
| A12 | 现有 PDF/图片/Excel 和印章库 | 运行相关既有测试并抽查 UI，新增功能不破坏现有入口 |

compatibility.md 每行记录：OS及版本、CPU、应用/Python版本、引擎完整版本、发行版/渠道、授权/登录、字体集、接口/插件版本、样本编号、基准/结果文件路径、结论/限制、日期。

## 风险与推进决策

- 高风险：WPS 发行版接口与部署差异、macOS 权限、共享办公进程、字体分页。由 P0 收敛后才进入实现。
- 中风险：全量预览内存、取消后的资源清理、打包依赖。由长文档、异常路径和真实安装包验收收敛。
- 未通过的自动化路线保留手动 PDF 入口，不牺牲已验证后端的交付。
- 可编辑 Word 后续优先研究书签/占位符定点插章，另建规格，不承诺跨软件任意页坐标稳定。
- 下一项工作：P0.1/P0.2，准备统一探测和样本，优先获取 Windows WPS 的实际自动化结果。本次没有执行任何 P0 验证。

## 资料依据

查阅日期：2026-09-14。资料证明候选能力，不替代平台实测。

- [S1 docx2pdf 官方仓库](https://github.com/AlJohri/docx2pdf)
- [S2 LibreOffice 命令行参数](https://help.libreoffice.org/latest/en-US/text/shared/guide/start_parameters.html)
- [S3 WPS Application 对象](https://open.wps.cn/documents/app-integration-dev/wps365/client/wpsoffice/jsapi/wps/Application/obj)
- [S4 WPS PDF 导出接口](https://open.wps.cn/documents/app-integration-dev/wps365/client/wpsoffice/jsapi/wps/Document/member/ExportAsFixedFormat)
- [S5 WPS 客户端开发概述](https://open.wps.cn/documents/app-integration-dev/wps365/client/wpsoffice/wps-integration-mode/wps-client-dev-introduction)
- [S6 WPS 加载项开发说明](https://open.wps.cn/documents/app-integration-dev/wps365/client/wpsoffice/wps-integration-mode/wps-addin-development/wps-addin-development-instructions)
- [S7 Apple 自动化权限](https://support.apple.com/en-ae/guide/mac-help/mchl108e1718/mac)
- [S8 LibreOffice 格式兼容说明](https://help.libreoffice.org/latest/en-GB/text/shared/guide/ms_import_export_limitations.html)
- [S9 Microsoft 字体替换与布局](https://support.microsoft.com/en-US/Office/fonts/use-the-modern-font-picker-in-office)
- [S10 PyMuPDF 支持格式](https://pymupdf.readthedocs.io/en/latest/how-to-open-a-file.html)
- [S11 python-docx 图片能力](https://python-docx.readthedocs.io/en/latest/user/shapes.html)
