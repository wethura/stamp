"""macOS WPS 引擎：仅做安装探测。

spec P0.3：macOS WPS 的自动化候选是 JS 加载项 + 本地桥接（S5/S6），
需要单独部署与验证，不在本轮 P0 范围内。当前结论口径为
「已检测到客户端，接口未验证 → 手动导入 PDF 路径」。
"""

import subprocess
from pathlib import Path

from .base import EngineInfo

WPS_APP = Path("/Applications/wpsoffice.app")


def probe() -> EngineInfo:
    if not WPS_APP.exists():
        return EngineInfo("wps", "WPS Office (macOS)", False,
                          detail="未安装 /Applications/wpsoffice.app")
    version = ""
    for key in ("CFBundleShortVersionString", "CFBundleVersion"):
        try:
            out = subprocess.run(
                ["defaults", "read", str(WPS_APP / "Contents/Info.plist"), key],
                capture_output=True, text=True, timeout=10,
            )
            value = out.stdout.strip()
            if value:
                version = value if not version else f"{version} ({value})"
                break
        except Exception:
            pass
    return EngineInfo(
        "wps", "WPS Office (macOS)", True,
        version=version, detail=str(WPS_APP),
        manual_path_only=True,
    )
