"""LibreOffice 位置的探测、验证与用户手动指定。

探测只是一层便利：装了但探测不到的情况永远存在（自定义目录、
绿色版、权限差异……）。因此提供第二层——用户手动指定安装目录，
持久化后优先级高于一切自动探测。
"""
import json
import logging
import os
import sys
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)

# 手动指定的持久化位置（~/.stamp_tool/soffice_path.json）
def _store_path() -> Path:
    return Path.home() / ".stamp_tool" / "soffice_path.json"


# ── 手动指定 ─────────────────────────────────────────────────────────

def validate_soffice_target(target) -> Optional[Path]:
    """把用户选中的「可执行文件或目录」解析为 soffice 路径。

    接受（按宽容度排序）：
    - soffice 可执行文件本身
    - Windows 安装根目录（含 program/soffice.exe）
    - program 目录本身 / macOS .app 目录（含 Contents/MacOS/soffice）
    - 上述的上一级目录（如直接选了 Program Files，浅层搜一层）
    """
    p = Path(target)
    exe_name = "soffice.exe" if sys.platform == "win32" else "soffice"

    if p.is_file():
        return p if p.name in ("soffice", "soffice.exe") else None

    if not p.is_dir():
        return None

    def exe_under(*rels) -> Optional[Path]:
        for rel in rels:
            candidate = p.joinpath(*rel)
            if candidate.is_file():
                return candidate
        return None

    # 直接命中：选的就是安装根 / program 目录 / .app 目录
    found = exe_under(("program", exe_name), (exe_name,),
                      ("Contents", "MacOS", "soffice"),
                      ("LibreOffice.app", "Contents", "MacOS", "soffice"))
    if found:
        return found
    # 浅层搜索一层：用户选了父目录（如 C:\\Program Files）
    for child in sorted(p.iterdir()):
        if not child.is_dir():
            continue
        found = exe_under_from(child)
        if found:
            return found
    return None


def exe_under_from(base: Path) -> Optional[Path]:
    exe_name = "soffice.exe" if sys.platform == "win32" else "soffice"
    for rel in (("program", exe_name), (exe_name,),
                ("Contents", "MacOS", "soffice"),
                ("LibreOffice.app", "Contents", "MacOS", "soffice")):
        candidate = base.joinpath(*rel)
        if candidate.is_file():
            return candidate
    return None


def set_manual_soffice(target) -> Optional[Path]:
    """验证并持久化用户指定的位置；无效返回 None。"""
    resolved = validate_soffice_target(target)
    if resolved is None:
        return None
    _store_path().parent.mkdir(parents=True, exist_ok=True)
    tmp = _store_path().with_suffix(".tmp")
    tmp.write_text(json.dumps({"soffice": str(resolved)}, ensure_ascii=False),
                   encoding="utf-8")
    os.replace(tmp, _store_path())
    logger.info("用户手动指定 LibreOffice: %s", resolved)
    return resolved


def get_manual_soffice() -> Optional[Path]:
    try:
        data = json.loads(_store_path().read_text(encoding="utf-8"))
        path = Path(data["soffice"])
        if path.is_file():
            return path
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return None


def clear_manual_soffice():
    try:
        _store_path().unlink()
    except OSError:
        pass


# ── 自动探测候选 ─────────────────────────────────────────────────────

def candidate_paths() -> List[Path]:
    """系统安装的全部候选路径（不含手动指定/内置组件/PATH，按序）。"""
    if sys.platform == "win32":
        program_files = [
            Path(os.environ.get("ProgramFiles", r"C:\Program Files")),
            Path(os.environ.get("ProgramFiles(x86)",
                                r"C:\Program Files (x86)")),
            Path(os.environ.get("ProgramW6432", r"C:\Program Files")),
        ]
        localappdata = os.environ.get("LOCALAPPDATA")
        roots = [pf / "LibreOffice" for pf in program_files]
        # 「仅为我安装」的默认位置——历史探测遗漏导致过误报
        if localappdata:
            roots.append(Path(localappdata) / "Programs" / "LibreOffice")
        roots.extend(_windows_registry_roots())
        seen, out = set(), []
        for root in roots:
            if root in seen:
                continue
            seen.add(root)
            out.append(root / "program" / "soffice.exe")
        return out
    if sys.platform == "darwin":
        return [
            Path("/Applications/LibreOffice.app/Contents/MacOS/soffice"),
            Path.home() / "Applications/LibreOffice.app/Contents/MacOS/soffice",
        ]
    return [Path("/usr/bin/soffice"), Path("/usr/local/bin/soffice"),
            Path("/opt/libreoffice/program/soffice"),
            Path("/snap/bin/libreoffice")]


def _windows_registry_roots() -> List[Path]:
    """从卸载信息读 LibreOffice 的 InstallLocation（含自定义安装盘）。"""
    if sys.platform != "win32":
        return []
    roots: List[Path] = []
    try:
        import winreg
    except ImportError:
        return roots
    views = [winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER]
    # KEY_WOW64_64KEY/32KEY：32 位 Python 读 64/32 位注册表视图的正确常量名
    # （曾误写成 KEYWOW64_64VIEW → AttributeError，Windows 上探测整体失效）
    accesses = [winreg.KEY_READ | winreg.KEY_WOW64_64KEY,
                winreg.KEY_READ | winreg.KEY_WOW64_32KEY]
    for hive in views:
        for access in accesses:
            try:
                base = winreg.OpenKey(
                    hive,
                    r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
                    0, access)
            except OSError:
                continue
            with base:
                index = 0
                while True:
                    try:
                        sub_name = winreg.EnumKey(base, index)
                        index += 1
                    except OSError:
                        break
                    try:
                        with winreg.OpenKey(base, sub_name, 0, access) as sub:
                            display, _ = winreg.QueryValueEx(sub, "DisplayName")
                            if "LibreOffice" not in str(display):
                                continue
                            location, _ = winreg.QueryValueEx(
                                sub, "InstallLocation")
                            if location:
                                roots.append(Path(str(location)))
                    except OSError:
                        continue
    return roots


def log_detection_scan(candidates: List[Path], found: Optional[Path],
                       source: str):
    """探测路径全部落日志：探测不到时用户/我们能看清它到底扫过哪。"""
    for cand in candidates:
        logger.info("LibreOffice 探测: %s → %s", cand,
                    "命中" if found == cand else "无")
    if found is None:
        logger.info("LibreOffice 自动探测未命中（来源=%s）；"
                    "可在 ⚙ 设置 中手动指定安装目录", source)
