# StampTool 盖章工具

桌面端文档盖章工具：为 PDF、图片、Excel、Word 文档添加印章，支持拖拽定位、大小/透明度/旋转调整，导出为带印章的文件。

## 更新日志

### v0.1.3

- **修复 Windows 上检测不到 Office/WPS**：`winreg` 未被 PyInstaller 收录（函数内延迟导入对静态分析不可靠），改用顶层条件导入并在 Windows 打包规格中显式声明
- 打包自检新增引擎探测验证：Windows 上断言注册表可用，此类打包缺失今后会在 CI 直接拦截，不再流到用户手里

### v0.1.2

- **修复 Windows 打开 Word 文档时闪退**：引擎探测中任何异常（例如缺失注册表模块）此前会中断整个应用；现在一律降级为「该引擎不可用」，不影响其他引擎与应用本身
- **打开文档不再卡界面**：引擎检查移到后台执行（此前同步阻塞，LibreOffice 首次启动可能让界面卡住数十秒）；单个引擎探测超时缩短至 8 秒，同会话内结果缓存
- **没有可用办公软件时给出清晰出口**：说明原因并提供「手动导入 PDF」入口，不再直接报错
- **新增运行日志**：写入 `~/.stamp_tool/logs/stamp_tool.log`，闪退会记录原因与调用栈（错误弹窗也会指向该文件），便于反馈问题
- 探测结果区分「未安装」与「无法读取注册表」，避免把检测失败误报成未安装
- 注：v0.1.2 解决了闪退，但 Windows 上 Office/WPS 检测仍不可用，已由 v0.1.3 修复——**请使用 v0.1.3 及以后版本**

### v0.1.1

- **修复**：双击印章添加时崩溃（启动构造与控制器字段名不一致，导致核心功能不可用）
- 打包产物新增启动自检：验证主窗口映射与「渲染 → 盖章 → 导出」完整链路
- 新增启动路径回归测试，锁定控制器构造契约

### v0.1.0

- 首个发布版本

## 下载

| 平台 | 文件 | 说明 |
|---|---|---|
| Windows x64 | `StampTool-*-windows-x64.zip` | 解压后双击 `StampTool.exe` 运行，无需安装 |
| macOS (Apple Silicon) | `StampTool-*-macos-arm64.dmg` | 打开 dmg，将 `StampTool` 拖入「应用程序」 |
| macOS (备用) | `StampTool-*-macos-arm64.zip` | 解压得到 `StampTool.app` |

> 本版本 macOS 包为 **Apple Silicon (arm64)** 构建，Intel Mac 暂不支持。

## 首次打开被系统拦截？

应用未做代码签名，macOS/Windows 首次打开会提示来源不明，属正常现象：

- **macOS**：请先将 `StampTool` 拖入「应用程序」再运行（推荐，也是标准安装方式）。若仍被拦截：右键点击 → 「打开」→ 再次确认；或执行
  `xattr -dr com.apple.quarantine /Applications/StampTool.app`
- **Windows**：SmartScreen 提示时点击「更多信息」→「仍要运行」

## Word (.docx) 文档支持

打开 `.docx` 时，工具会调用本机已安装的办公软件把它转换为 PDF 快照（预览与盖章都基于该快照，原始 Word 文件不会被修改），导出结果为 `原文件名-已盖章.pdf`。

- 支持的后端：**LibreOffice**（三平台）、**Microsoft Word**（macOS 自动化 / Windows COM）、**WPS Office**（Windows COM）
- 打开文档时会询问「平时用哪个软件编辑这个文件」，选择后记住；也可在工具栏 **⚙ 设置** 中随时更改或重新检测
- 未检测到可用引擎时，提供手动路径：在 Word/WPS/LibreOffice 中导出 PDF 后直接拖入本工具
- 首次使用可能需要系统授权（macOS「自动化」权限）

## 已知限制

- Windows 端的 Word/WPS COM 转换已实现，但尚未在装有 Office 的实机环境完成验证；如遇问题请改用 LibreOffice 后端或手动导入 PDF
- 加密或损坏的 `.docx` 会被拦截并提示，不做密码输入
- 不支持 `.doc`、`.docm`、原生 `.wps`，也不输出可编辑的 Word 文件

## 校验

每个包均可在 Actions 运行页找到对应的构建与测试记录；构建过程见仓库 `.github/workflows/build.yml`。
