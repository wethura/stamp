# Word 适配技术设计（P1.1 冻结 v1）

状态：2026-09-14 冻结 v1（B 路线：凭 LibreOffice/macOS 通过进入首版实现；Word saveAs 复核后仅影响 word-jxa 后端启用开关，不改契约）。

## 1. 架构

```
App._load_document(.docx)
        │
        ▼
DocxPrecheck（新增，纯函数）         ← A04/A05 教训：不信任引擎
  ├─ zip 中央目录 + [Content_Types].xml 校验
  └─ 失败 → 分类报错（损坏/加密/非 docx），不启动引擎
        │
        ▼
ConversionService（新增，后台线程）
  ├─ engines 注册表：word_com / wps_com / word_jxa / wps_bridge / soffice
  ├─ 探测（缓存 + 偏好记忆）；多引擎时弹选择 UI
  ├─ convert(work_copy, out_pdf, cancel_token, timeout=120s)
  └─ 产出 PDF 快照 + 会话元数据
        │
        ▼
PDFHandler（复用）                  ← 预览与盖章全部基于快照
```

- 会话元数据：源路径、工作副本 sha256、引擎 id+版本、快照路径、页尺寸列表。印章坐标只关联快照（`processing/stamp_instance.py` 无需持久化改动，重转换后清空重放）。
- 同一会话只转换一次；导出**不得**再次转换。

## 2. 引擎契约（P1.1 待冻结项的当前稿）

```python
class ConversionEngine(Protocol):
    id: str
    def probe(self) -> EngineInfo: ...          # 不启动 GUI、不阻塞 >5s
    def convert(self, work_copy, out_pdf, *,
                timeout_s, cancel_token) -> ConvertResult: ...
    def cleanup(self) -> CleanupReport: ...     # 只处置本任务启动的进程/文档
```

- **就绪等待**：启动引擎后轮询就绪（Word：`running()` + 静置），再做 open/save——首启弹窗期事件会挂起。
- **取消**：cancel_token 在引擎进程侧生效（soffice：terminate 我们的子进程；Word：无法安全中断共享进程，标记放弃结果 + 人工弹窗提示）。
- **进程归属**（spec 安全要求，实测重申）：soffice 用独立 `UserInstallation` 即为本任务私有进程，可安全 kill；Word/WPS 是共享用户进程，永不 `pkill`，只允许「本任务启动 → 退出失败如实报告」。

## 3. 错误分类 → 用户出口（与 spec 表格对齐）

| error_kind | 探测阶段证据 | 用户出口 |
|---|---|---|
| engine_missing | soffice 未安装 / Word.app 不存在 | 指引安装 + 手动 PDF 入口 |
| permission | JXA err -1743 | 解释自动化授权，系统设置恢复指引 |
| modal_blocked（新增） | open/save -1712、quit -128 | 「办公软件有未处理弹窗，请处理后重试」 |
| timeout | 转换 >120s | 取消 + 建议手动导出 |
| precheck_failed（新增） | zip 头校验失败 | 「文件损坏或加密，请在原软件中处理后导出 PDF」 |
| convert / invalid_pdf | soffice 把 corrupt 文件当纯文本导入（实测） | 由 precheck 拦截，兜底走 invalid_pdf |
| manual_path_only | macOS WPS | 「在 WPS 中导出 PDF 后拖入本工具」 |

## 4. P0 实测已固化的决策

1. **应用层前置校验 DOCX**（zip 中央目录 + `[Content_Types].xml`）——LibreOffice 会把任意字节流按 Text 滤镜"成功"转换，不能依赖引擎报错（A04/A05）。
2. **Word JXA 分三阶段限时**（ensure-ready / open+save+close / quit），每阶段独立超时与错误归类——单脚本超时无法定位卡点。
3. **soffice 独立 UserInstallation**：避免与用户运行中的 LibreOffice 冲突；转换实测 1p/10p/100p 全部 <2s。
4. **工作副本 + 前后 sha256**：源文件零写入已验证。
5. macOS WPS：保持手动路径，加载项桥接另立验证任务（P0.3 后半）。
6. **Word 转换前必须检测并退出 Microsoft Error Reporting**（`Word.app/Contents/SharedSupport/`）：其模态"发送报告"窗会阻塞 Word 的全部 Apple Events（open/save 全部 -1712、quit 被 -128 取消），且由异常退出循环反复触发。已实现自动检测退出（`word_mac.py::_dismiss_error_reporter`）；正常产品路径对应错误出口「办公软件有未处理弹窗」。
7. **Word 的 saveAs 是当前唯一未打通的单点**（open 已验证可通）：保存时疑似弹出不可见的对话框。候选处置：容器暂存（已实现待验证）、保存到 ~/Documents 等用户已知目录、或要求首次使用时人工授权一次。P1 设计评审时结合 docx2pdf 的生产实现对比定案。

## 5. 会话状态机（冻结 v1）

```
Idle ──选文件──▶ Prechecking ──通过──▶ Probing(缓存命中可跳过)
   │                   │失败                │
   │                   ▼                   ▼多引擎
   └──────────── Failed(分类文案)    EngineChoosing(用户选择,记忆)
   需转换                 │单引擎/已记忆
   ◀─────────────────────┘
   ▼
Converting(后台线程,不定进度条+取消,120s超时)
   ├─成功──▶ SnapshotReady(切换会话;已有章时先提示重转换并清空章位置)
   ├─取消──▶ Idle(1s内恢复;迟到结果按会话id丢弃)
   ├─超时/失败──▶ Failed(换引擎 / 手动PDF 两出口;旧会话保留)
   └─重新导入──▶ Prechecking(读新内容,旧章位清空)
```

不变式：`SnapshotReady` 前不可盖章导出；导出永远使用快照，不二次转换；同一时刻至多一个活跃转换会话（带会话 id），晚到结果按 id 丢弃。

## 6. 临时目录与进程归属（冻结 v1）

| 资源 | 位置 | 归属 | 清理时机 |
|---|---|---|---|
| 工作副本 | `<应用缓存>/word-work/<会话id>/` | 本会话 | 会话关闭/切换成功后删除 |
| 转换 PDF 快照 | 同上 `snapshot.pdf` | 本会话 | 导出成功且会话关闭后删除 |
| soffice 配置目录 | 系统临时目录随机名 | 本任务子进程 | 转换结束即删（probe 已实现） |
| Word 容器暂存 | `~/Library/Containers/com.microsoft.word/Data/Documents/WordProbeStage/` | 本任务 | 移回目标后即删 |
| 异常残留 | 启动时扫描本应用缓存目录 | 仅本应用目录 | 下次启动清理，不碰其他软件文件 |

进程归属细则：soffice 用独立 `UserInstallation`，属本任务进程，可 terminate；Word/WPS 是共享用户进程——只允许「本任务启动 → 退出」，退出被弹窗取消时如实报告，永不 pkill；**Microsoft Error Reporting 允许自动退出**（无用户文档，实测阻塞自动化，2026-09-14 根因）。

## 7. 待办（进 P2 前必须收敛）

- [ ] macOS Word saveAs 弹窗人工复核后重跑 contract-1p/10p/mixed/corrupt，更新 compatibility.md。
- [ ] Word 输出 PDF 与 LibreOffice 输出做分页/字体差异记录（A01 基准比对）。
- [ ] docx2pdf 的 macOS JXA 细节比对（其生产级脚本处理了弹窗/权限的边角）。
- [ ] Windows COM 探测脚本移植（P0.2），Linux soffice 验证（P0.4）。
- [ ] 加密 docx 样本构造与 precheck 分类（当前未验证）。

## 8. LibreOffice 引擎的三层位置策略（2026-09-16，用户实测反馈驱动）

自动探测遗漏是常态（每用户安装 %LOCALAPPDATA%\\Programs\\LibreOffice、
自定义盘符、绿色版都曾漏报）。策略分层：

| 层 | 优先级 | 说明 |
|---|---|---|
| STAMPTOOL_SOFFICE 环境覆盖 | 1 | 测试/高级用户 |
| 用户手动指定目录（~/.stamp_tool/soffice_path.json） | 2 | 探测不是真理；宽容解析安装根/program/.app/父目录/可执行文件 |
| 内置下载组件（DriverManager，~/.stamp_tool/drivers） | 3 | 官方源+字节数+SHA-256；Windows msiexec /a 解包（无 UAC/不写注册表）、macOS DMG 复制去隔离 |
| 自动探测 | 4 | Program Files(x86/x64)、LOCALAPPDATA 每用户、注册表 InstallLocation(HKLM+HKCU×64/32 视图)、PATH；扫描路径全量落日志 |

职责边界（用户明确）：「指定目录/下载引擎」只在 ⚙ 设置 的引擎页；
无引擎弹窗只给「手动导入 PDF」+指引设置页。
