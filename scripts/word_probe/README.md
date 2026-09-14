# Word 转换引擎探测（P0）

对应 `.project/plans/word-support/spec.md` P0.1–P0.6。本目录是独立 CLI，
不接入 GUI；验证通过的后端才会在 P2 实现 `WordHandler` 时接入。

## 用法

```bash
# 全引擎、默认样本（1页/10页/混合布局/损坏样本）
python -m scripts.word_probe.probe

# 只测 LibreOffice；加 100 页样本
python -m scripts.word_probe.probe --engines soffice --full

# 只测 Word JXA（注意：可能触发 macOS 自动化授权弹窗与 Word 首启弹窗）
python -m scripts.word_probe.probe --engines word
```

产出写入 `out/<时间戳>/`：`report.md`、`report.json`、样本 docx、转换 PDF
与首屏渲染 PNG。该目录已 gitignore，仅将结论抄录至
`.project/plans/word-support/compatibility.md`。

## 样本说明（`make_samples.py`）

| 名称 | 内容 | 通过条件 |
|---|---|---|
| contract-1p / 10p / 100p | 确定性分页的中文合同（显式分页符） | 页数一致 + 标记文字在文字层 |
| mixed-layout | 页眉页脚 + 合并单元格表格 + 横向页节 | 2 页且横向节尺寸翻转 |
| corrupt | 非 zip 字节流 | 引擎必须报错（被"成功"导入即 FAIL） |

## 平台注意（2026-09-14 macOS 实测）

- **Word JXA**：存在首启/模态弹窗（登录、激活、文件访问确认、异常退出恢复）
  时，open/save 事件全部 -1712 超时。先人工清空 Word 弹窗再跑。
- **LibreOffice**：使用独立 `UserInstallation`，不影响用户正在运行的实例；
  损坏文件会被 Text 滤镜当纯文本导入 → 应用层必须前置校验 docx 文件头。
- 源样本只读使用：转换在工作副本上进行，前后 sha256 比对，确保源文件零修改。
