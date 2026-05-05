# 测试配置

## 命令
python -m unittest discover tests -v

## 单元测试策略
使用 Python unittest 进行单元测试，测试文件放在 tests/ 目录，命名约定 test_*.py。

## 测试基础设施

### 功能测试
- 框架：unittest（标准库）
- 测试文件位置：tests/test_*.py
- 共享工具：tests/__init__.py
- 数据策略：使用 tempfile 创建临时目录，测试后自动清理

### GUI 测试
- 框架：unittest + tkinter
- 测试文件位置：tests/test_controls_panel.py 等
- 共享工具：MagicMock 模拟 StampManager，避免真实文件系统操作
- 数据策略：使用 mock 对象模拟 StampData，避免 tkinter mainloop

## 代码质量工具

### 格式化
- 命令：未配置（Python 项目无统一格式化工具）

### Lint 自动修复
- 命令：未配置

### 静态检查
- 命令：未配置
