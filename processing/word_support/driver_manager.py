"""可选的 LibreOffice 转换组件（驱动）管理。

目标场景：用户机器上没有任何可用的 Word 转换引擎。由用户自行决定
是否下载一份应用自管理的 LibreOffice，默认装到 ~/.stamp_tool/drivers/，
也可在确认对话里指定其他磁盘上的空目录：

- Windows：官方 MSI 以「管理员映像」方式解包（msiexec /a）——
  不需要管理员权限、不写注册表、不影响系统安装
- macOS：官方 DMG 挂载后复制 .app 并去除隔离属性
- Linux：不提供（建议用系统包管理器安装）

完整性：仅允许 HTTPS + 官方域；下载后校验精确字节数与 sha256；
任何失败/取消都不留半成品（staging + 原子改名）。staging 建在
目标目录同级（同卷才能原子改名）；自定义位置记录在
~/.stamp_tool/drivers/driver_location.json，供后续启动发现。
"""
import hashlib
import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import urllib.request
from pathlib import Path
from typing import Callable, Optional

logger = logging.getLogger(__name__)

ALLOWED_HOSTS = {"download.documentfoundation.org"}
CHUNK = 1 << 20
# MSI 管理员映像解包后约为安装包的 3~4 倍；按 4 倍预留磁盘
UNPACK_FACTOR = 4

LIBREOFFICE_VERSION = "26.2.6"
_BASE = (f"https://download.documentfoundation.org/libreoffice/stable/"
         f"{LIBREOFFICE_VERSION}")

# 下载目录（目录列表标注的体积为约数；字节数与 sha256 以实际下载校准）
# size_bytes / sha256 于 2026-09-16 从官方源实测校准（26.2.6）。
# TDF 不发布 .sha256；此哈希为官方文件的实际值，升级版本时需重新校准。
CATALOG = {
    "win32": {
        "kind": "msi",
        "url": f"{_BASE}/win/x86_64/LibreOffice_{LIBREOFFICE_VERSION}_Win_x86-64.msi",
        "size_bytes": 373252096,
        "sha256": "f9877032fd908beb9c0ddf06df4af5c2e85f419c42e14876c4cce5aae5fb2660",
    },
    "darwin": {
        "kind": "dmg",
        "url": f"{_BASE}/mac/aarch64/LibreOffice_{LIBREOFFICE_VERSION}_MacOS_aarch64.dmg",
        "size_bytes": 297798926,
        "sha256": "94bb3248df074c225490a8a6d1d9dc87c7d6783dbb7a8e9f0d0c3d94348552af",
    },
}

KIND_LABEL = {"msi": "Windows 安装包", "dmg": "macOS 磁盘映像"}


class DriverError(RuntimeError):
    """kind: cancelled | network | checksum | disk | extract | unsupported"""

    def __init__(self, kind: str, message: str):
        self.kind = kind
        super().__init__(message)


def _progress_phase(cb: Optional[Callable], phase: str, done: int, total: int):
    if cb is None:
        return
    try:
        cb(phase, done, total)
    except Exception:  # noqa: BLE001  进度回调失败不影响下载
        pass


class DriverManager:
    """应用自管理转换组件的下载/安装/卸载与查询。

    catalog/allowed_hosts 可注入（测试用本地源）；默认用模块级钉板。
    """

    def __init__(self, base_dir: Optional[str] = None, catalog: dict = None,
                 allowed_hosts: set = None):
        if base_dir is None:
            base_dir = os.path.join(os.path.expanduser("~"),
                                    ".stamp_tool", "drivers")
        self.base_dir = Path(base_dir)
        self._catalog = catalog if catalog is not None else CATALOG
        self._allowed_hosts = (allowed_hosts if allowed_hosts is not None
                               else ALLOWED_HOSTS)
        self.default_install_dir = self.base_dir / "libreoffice"
        self._pointer = self.base_dir / "driver_location.json"
        self._downloads = self.base_dir / "downloads"
        resolved = self._resolve_install_dir()
        # 发现顺序：当前（指针指向的）位置 → 默认位置
        self._all_locations = ([resolved, self.default_install_dir]
                               if resolved != self.default_install_dir
                               else [self.default_install_dir])
        self.install_dir = resolved

    @property
    def _marker(self) -> Path:
        return self.install_dir / "driver.json"

    def _resolve_install_dir(self) -> Path:
        """按位置指针还原自定义安装目录；指针失效时回到默认目录。"""
        try:
            data = json.loads(self._pointer.read_text(encoding="utf-8"))
            custom = data.get("install_dir")
        except (OSError, ValueError, AttributeError):
            return self.default_install_dir
        if not custom or not isinstance(custom, str):
            return self.default_install_dir
        path = Path(custom)
        if (path.is_absolute() and path != self.default_install_dir
                and (path / "driver.json").exists()):
            return path
        return self.default_install_dir

    # ── 查询 ─────────────────────────────────────────────────────────

    def platform_supported(self) -> bool:
        return sys.platform in self._catalog

    def catalog_info(self) -> dict:
        info = self._catalog.get(sys.platform)
        if info is None:
            return {}
        out = dict(info)
        out["version"] = LIBREOFFICE_VERSION
        out["size_mb"] = round((info.get("size_bytes") or 0) / 1024 / 1024)
        return out

    def _install_candidates(self) -> list:
        """所有可能存在自管理安装的位置（当前 install_dir 优先）。"""
        head = [self.install_dir]
        return head + [d for d in self._all_locations
                       if d not in head]

    def managed_soffice_path(self) -> Optional[Path]:
        """自管理 LibreOffice 的 soffice 可执行文件（未安装返回 None）。"""
        for root in self._install_candidates():
            found = self._soffice_under(root)
            if found is not None:
                return found
        return None

    def _soffice_under(self, root: Path) -> Optional[Path]:
        if not (root / "driver.json").exists():
            return None
        recorded = self._load_marker(root / "driver.json").get("soffice")
        if recorded:
            candidate = Path(recorded)
            if candidate.exists():
                return candidate
        # 标记丢失/失效时按布局兜底搜索
        for pattern in ("**/soffice.exe", "**/soffice"):
            for hit in root.glob(pattern):
                if hit.is_file():
                    return hit
        return None

    def status(self) -> dict:
        soffice = self.managed_soffice_path()
        marker = {}
        if soffice is not None:
            for root in self._install_candidates():
                if root in soffice.parents:
                    marker = self._load_marker(root / "driver.json")
                    break
        return {
            "installed": soffice is not None,
            "soffice": str(soffice) if soffice else None,
            "version": marker.get("version"),
            "size_bytes": marker.get("size_bytes"),
        }

    def _load_marker(self, path: Path = None) -> dict:
        try:
            with open(path or self._marker, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    # ── 安装 ─────────────────────────────────────────────────────────

    def install(self, progress_cb: Optional[Callable] = None,
                cancel_event: Optional[threading.Event] = None,
                target_dir: Optional[str] = None) -> dict:
        """下载并安装自管理 LibreOffice；成功返回 status()。

        target_dir：安装到用户指定的绝对路径目录（须为空目录或旧的
        自管理安装目录）；缺省装到默认目录。staging 建在目标同级，
        保证跨盘安装也能原子改名落位。
        """
        info = self._catalog.get(sys.platform)
        if info is None:
            raise DriverError(
                "unsupported",
                "当前平台暂不提供内置下载，请用系统包管理器安装 LibreOffice。")

        if target_dir:
            target = Path(target_dir).expanduser()
            if not target.is_absolute():
                raise DriverError(
                    "disk", "安装位置必须是绝对路径，"
                            f"例如 D:\\LibreOffice（收到：{target_dir}）。")
            self._validate_target(target)
            if target != self.install_dir:
                # 记下旧位置：安装成功后统一清理，不留上 GB 的孤儿
                if self.install_dir not in self._all_locations:
                    self._all_locations.append(self.install_dir)
                self.install_dir = target
        # 未指定目录时沿用当前（指针解析出的）位置；
        # 旧自定义位置在成功后统一清理。

        self._check_cancel(cancel_event)
        self._check_disk(info)

        self._downloads.mkdir(parents=True, exist_ok=True)
        archive = self._downloads / f"libreoffice.{info['kind']}"
        try:
            self._download(info, archive, progress_cb, cancel_event)
            self._verify(info, archive, progress_cb)
            self.install_dir.parent.mkdir(parents=True, exist_ok=True)
            staging = Path(tempfile.mkdtemp(prefix="lo-stage-",
                                            dir=str(self.install_dir.parent)))
            try:
                soffice = self._extract(info, archive, staging,
                                        progress_cb, cancel_event)
                self._finalize(staging, soffice, info)
                self._cleanup_old_locations()
            finally:
                shutil.rmtree(staging, ignore_errors=True)
        finally:
            archive.unlink(missing_ok=True)

        return self.status()

    # ── 各阶段 ───────────────────────────────────────────────────────

    @staticmethod
    def _check_cancel(cancel_event):
        if cancel_event is not None and cancel_event.is_set():
            raise DriverError("cancelled", "已取消下载")

    def _validate_target(self, target: Path):
        """自定义安装目录只允许空目录或旧的自管理安装（防误删用户数据）。"""
        if not target.exists():
            return
        if not any(target.iterdir()):
            return
        if self._load_marker(target / "driver.json").get("kind") == "libreoffice":
            return
        raise DriverError(
            "disk",
            f"所选目录不是空的：\n{target}\n\n"
            f"请选择一个空目录，组件将直接安装到该目录。")

    @staticmethod
    def _free_bytes(start: Path) -> int:
        probe = start
        while not probe.exists():
            probe = probe.parent
        return shutil.disk_usage(probe).free

    def _check_disk(self, info: dict):
        size = info.get("size_bytes") or 0
        if size <= 0:
            return
        need_archive = size            # 下载包落在 base_dir/downloads
        need_unpack = size * UNPACK_FACTOR  # staging 解包 → 目标目录
        free_base = self._free_bytes(self.base_dir)
        if free_base < need_archive:
            raise DriverError(
                "disk",
                f"磁盘空间不足：下载约需 {need_archive // 1024 // 1024} MB，"
                f"当前分区可用 {free_base // 1024 // 1024} MB。")
        free_target = self._free_bytes(self.install_dir)
        if free_target < need_unpack:
            raise DriverError(
                "disk",
                f"目标分区空间不足：安装约需 {need_unpack // 1024 // 1024} MB"
                f"（解包后），\n{self.install_dir} 所在分区可用 "
                f"{free_target // 1024 // 1024} MB。")

    def _download(self, info, archive: Path, progress_cb, cancel_event):
        url = info["url"]
        from urllib.parse import urlparse
        parsed = urlparse(url)
        # 环回地址允许 http（仅测试接缝）；外部源一律 HTTPS
        loopback = parsed.hostname in {"127.0.0.1", "localhost", "::1"}
        if parsed.scheme != "https" and not loopback:
            raise DriverError("network", "仅支持 HTTPS 下载源")
        if parsed.hostname not in self._allowed_hosts:
            raise DriverError("network", f"下载源不在允许列表: {url}")

        try:
            req = urllib.request.Request(url, headers={"User-Agent": "StampTool"})
            resp = urllib.request.urlopen(req, timeout=60)
        except Exception as exc:  # noqa: BLE001
            raise DriverError("network", f"无法连接下载源: {exc}")

        total = int(resp.headers.get("Content-Length") or 0)
        expected = info.get("size_bytes")
        if expected and total and total != expected:
            resp.close()
            raise DriverError(
                "checksum",
                f"下载源文件大小与预期不符（{total} ≠ {expected} 字节），"
                f"可能已发布新版本，请更新应用后再试。")

        done = 0
        hasher = hashlib.sha256()
        try:
            with open(archive, "wb") as f:
                while True:
                    self._check_cancel(cancel_event)
                    chunk = resp.read(CHUNK)
                    if not chunk:
                        break
                    f.write(chunk)
                    hasher.update(chunk)
                    done += len(chunk)
                    _progress_phase(progress_cb, "download", done,
                                    total or expected or done)
        except DriverError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise DriverError("network", f"下载中断: {exc}")
        finally:
            resp.close()

        if expected and done != expected:
            raise DriverError(
                "checksum",
                f"下载不完整（{done} / {expected} 字节），请重试。")
        self._downloaded_sha = hasher.hexdigest()

    def _verify(self, info, archive: Path, progress_cb):
        _progress_phase(progress_cb, "verify", 0, 1)
        expected_sha = info.get("sha256")
        actual = getattr(self, "_downloaded_sha", None)
        if actual is None:
            hasher = hashlib.sha256()
            with open(archive, "rb") as f:
                for chunk in iter(lambda: f.read(CHUNK), b""):
                    hasher.update(chunk)
            actual = hasher.hexdigest()
        if expected_sha and actual != expected_sha:
            raise DriverError(
                "checksum",
                "文件校验失败（SHA-256 不符），已丢弃下载内容。")
        self._verified_sha = actual
        _progress_phase(progress_cb, "verify", 1, 1)

    def _extract(self, info, archive: Path, staging: Path,
                 progress_cb, cancel_event) -> Path:
        _progress_phase(progress_cb, "extract", 0, 0)
        self._check_cancel(cancel_event)
        if info["kind"] == "msi":
            self._extract_msi(archive, staging)
        elif info["kind"] == "dmg":
            self._extract_dmg(archive, staging)
        else:  # pragma: no cover
            raise DriverError("extract", f"未支持的包类型 {info['kind']}")

        soffice = next((p for p in sorted(staging.rglob("soffice.exe"))
                        if p.is_file()), None) \
            if sys.platform == "win32" else \
            next((p for p in sorted(staging.rglob("soffice")) if p.is_file()), None)
        if soffice is None:
            raise DriverError(
                "extract", "解包后未找到 soffice 可执行文件，安装中止。")
        _progress_phase(progress_cb, "extract", 1, 1)
        return soffice

    @staticmethod
    def _extract_msi(archive: Path, staging: Path):
        """管理员映像解包：无需管理员权限、不写注册表、不装服务。"""
        cmd = ["msiexec", "/a", str(archive), "/qn",
               f"TARGETDIR={staging}"]
        try:
            proc = subprocess.run(cmd, capture_output=True, timeout=1800)
        except Exception as exc:  # noqa: BLE001
            raise DriverError("extract", f"msiexec 执行失败: {exc}")
        if proc.returncode != 0:
            detail = (proc.stderr or b"").decode("utf-8", "ignore").strip()
            raise DriverError("extract",
                              f"MSI 解包失败（exit {proc.returncode}）: {detail}")

    @staticmethod
    def _extract_dmg(archive: Path, staging: Path):
        mount = tempfile.mkdtemp(prefix="lo-dmg-")
        try:
            attach = subprocess.run(
                ["hdiutil", "attach", str(archive), "-nobrowse",
                 "-readonly", "-mountpoint", mount],
                capture_output=True, timeout=600)
            if attach.returncode != 0:
                detail = (attach.stderr or b"").decode("utf-8", "ignore")
                raise DriverError("extract", f"DMG 挂载失败: {detail}")
            try:
                src = Path(mount) / "LibreOffice.app"
                if not src.exists():
                    raise DriverError("extract", "DMG 中未找到 LibreOffice.app")
                dest = staging / "LibreOffice.app"
                shutil.copytree(src, dest)
                # 去除网络下载隔离属性，命令行直接调用 soffice 才不会被拦
                subprocess.run(
                    ["xattr", "-dr", "com.apple.quarantine", str(dest)],
                    capture_output=True, timeout=120)
            finally:
                subprocess.run(["hdiutil", "detach", mount, "-quiet"],
                               capture_output=True, timeout=120)
        finally:
            shutil.rmtree(mount, ignore_errors=True)

    def _finalize(self, staging: Path, soffice_in_staging: Path, info: dict):
        _dest = self.install_dir
        if _dest.exists():
            # 只覆盖空目录或旧的自管理安装；绝不删用户自己的数据
            if self._load_marker(_dest / "driver.json").get("kind") == "libreoffice":
                shutil.rmtree(_dest)
            elif any(_dest.iterdir()):
                raise DriverError(
                    "extract", f"目标目录不为空：{_dest}")
            else:
                _dest.rmdir()  # Windows 上目录不能原地替换，先移除空目录
        # staging → install_dir 原子化（staging 建在同级，同分区 rename）
        os.replace(staging, _dest)
        soffice = _dest / soffice_in_staging.relative_to(staging)
        marker = {
            "kind": "libreoffice",
            "version": LIBREOFFICE_VERSION,
            "source_url": info["url"],
            "sha256": getattr(self, "_verified_sha", None),
            "size_bytes": info.get("size_bytes"),
            "soffice": str(soffice),
            "license": "MPL-2.0 (LibreOffice, The Document Foundation)",
        }
        tmp = self._marker.with_suffix(".tmp")
        self._marker.parent.mkdir(parents=True, exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(marker, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self._marker)
        self._write_pointer()

    def _write_pointer(self):
        """记录自定义安装位置；装回默认目录时清除指针。"""
        try:
            if self.install_dir == self.default_install_dir:
                self._pointer.unlink(missing_ok=True)
                return
            self._pointer.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._pointer.with_suffix(".tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump({"install_dir": str(self.install_dir)},
                          f, ensure_ascii=False, indent=2)
            os.replace(tmp, self._pointer)
        except OSError as exc:
            # 安装本体已就位；指针写失败只是下次启动发现不了该位置
            logger.warning("写入安装位置指针失败: %s", exc)

    def _cleanup_old_locations(self):
        """安装成功后移除其他位置上的旧自管理安装（不留上 GB 的孤儿）。"""
        current = self.install_dir
        for old in self._install_candidates():
            if old != current and (old / "driver.json").exists():
                shutil.rmtree(old, ignore_errors=True)

    # ── 卸载 ─────────────────────────────────────────────────────────

    def uninstall(self):
        for location in self._install_candidates():
            shutil.rmtree(location, ignore_errors=True)
        shutil.rmtree(self._downloads, ignore_errors=True)
        try:
            self._pointer.unlink(missing_ok=True)
        except OSError:
            pass
