"""OS 文件拖入支持：把主窗口注册为系统拖放目标（tkinterdnd2 / tkdnd）。

接线要点（此前拖拽静默失效的根因都在这里）：
- tkdnd 是 Tcl 扩展，必须先在根窗口的解释器里 ``package require tkdnd``，
  否则 ``drop_target_register`` 抛 TclError；
- tkinterdnd2 导入时只把 ``dnd_bind`` 等方法打到 ``tkinter.BaseWidget`` 上，
  根窗口（``tkinter.Tk`` 子类，如 CTk）不在其中，需要补挂到实例上。

任何一步失败都只降级为「无拖拽」，绝不阻断启动（与引擎探测同一纪律）。
"""

import logging
from typing import Callable, List, Optional

logger = logging.getLogger(__name__)

# 每个解释器只加载一次；False 表示已确认不可用（区别于未尝试的 None）
_loaded_version = None


def _load_tkdnd(root) -> Optional[str]:
    """在 root 的 Tcl 解释器里加载 tkdnd；返回版本号，不可用返回 None。"""
    global _loaded_version
    if _loaded_version is None:
        try:
            from tkinterdnd2.TkinterDnD import _require
            _loaded_version = _require(root)
            logger.info("tkdnd 已加载 (版本 %s)", _loaded_version)
        except Exception as exc:  # noqa: BLE001  打包缺文件/平台不支持等
            logger.warning("tkdnd 不可用，文件拖入功能停用: %s", exc)
            _loaded_version = False
    return _loaded_version or None


def enable_file_drop(root, on_drop_data: Callable[[str], None]) -> Optional[str]:
    """把整个主窗口（root）注册为文件拖放目标。

    ``on_drop_data`` 在主线程收到 tkdnd 的 %D 原始字符串（Tcl 列表），
    由调用方用 :func:`parse_drop_paths` 解析。返回 tkdnd 版本号；
    功能不可用时返回 None（调用方可据此记日志/自检）。
    """
    version = _load_tkdnd(root)
    if not version:
        return None
    try:
        from tkinterdnd2 import DND_FILES
        from tkinterdnd2.TkinterDnD import DnDWrapper

        # Tk 根不在 BaseWidget 补丁范围内：把 DnDWrapper 的方法与
        # % 替换表挂到实例上（dnd_bind 内部会取这些属性）
        for name in ("_subst_format_dnd", "_subst_format_str_dnd"):
            if not hasattr(root, name):
                setattr(root, name, getattr(DnDWrapper, name))
        for name in ("_substitute_dnd", "_dnd_bind", "dnd_bind",
                     "drop_target_register", "drop_target_unregister"):
            if not hasattr(root, name):
                setattr(root, name, getattr(DnDWrapper, name).__get__(root))

        root.drop_target_register(DND_FILES)
        root.dnd_bind("<<Drop>>", lambda event: on_drop_data(event.data))
        logger.info("主窗口已注册为文件拖放目标 (tkdnd %s)", version)
        return version
    except Exception:  # noqa: BLE001  注册失败只影响拖拽本身
        logger.warning("注册文件拖放目标失败", exc_info=True)
        return None


def parse_drop_paths(drop_data: str, tk_interp=None) -> List[str]:
    """把 tkdnd 的 %D（Tcl 列表字符串）解析为路径列表。

    %D 是 Tcl 列表：含空格的路径以 ``{}`` 包裹、反斜杠是转义符，
    多个文件是多个元素——``shlex``/``split`` 都会把 Windows 路径弄坏，
    必须用 ``splitlist``。没有解释器（测试桩）时退化为手工解析。
    """
    if tk_interp is not None:
        try:
            paths = list(tk_interp.splitlist(drop_data))
        except Exception:  # noqa: BLE001  桩对象的假解释器等
            paths = None
        # 非空输入却解出空列表 = 假解释器（MagicMock 迭代为空），不采信
        if (paths is not None and all(isinstance(p, str) for p in paths)
                and (paths or not drop_data.strip())):
            if "\\" not in drop_data or any("\\" in p for p in paths):
                return [p for p in paths if p]
            # 反斜杠被 Tcl 当转义吃掉了（非 Tcl 列表形式的路径）→ 手工解析
    return _split_tcl_list(drop_data)


def _split_tcl_list(text: str) -> List[str]:
    """Tcl 列表的手工解析（无解释器时的降级路径）。"""
    items: List[str] = []
    buf: List[str] = []
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if ch == "{":
            i += 1
            while i < n and text[i] != "}":
                if text[i] == "\\" and i + 1 < n:
                    buf.append(text[i + 1])
                    i += 2
                    continue
                buf.append(text[i])
                i += 1
            i += 1  # 跳过收尾 }
        elif ch.isspace():
            if buf:
                items.append("".join(buf))
                buf = []
            i += 1
        else:
            buf.append(ch)
            i += 1
    if buf:
        items.append("".join(buf))
    return [p for p in items if p]
