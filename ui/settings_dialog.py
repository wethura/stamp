"""系统设置对话框：Word 转换引擎选择（基于本机安装探测）。

引擎可见性按环境决定：未安装的显示「未安装」；已安装但接口未验证的
（macOS WPS）显示「暂不支持自动转换」；可用引擎可选为首选并持久化。
探测可能遗漏（自定义目录等），LibreOffice 行提供「手动指定目录」。
"""
from tkinter import filedialog, messagebox
from typing import List, Optional, Tuple

import customtkinter as ctk

from processing.word_support.engines import EngineInfo
from processing.word_support.service import ConversionService, get_shared_service
from ui.theme import Colors, Fonts

AUTO_OPTION = "auto"


def build_engine_rows(infos: List[EngineInfo]) -> List[Tuple[EngineInfo, bool, str]]:
    """把探测结果转成展示行：(引擎, 可选为首选, 状态文案)。纯函数，可测。"""
    ordered = sorted(infos, key=lambda i: (not i.available, i.manual_path_only))
    rows = []
    for info in ordered:
        selectable = info.available and not info.manual_path_only
        if not info.available:
            status = "未安装"
        elif info.manual_path_only:
            status = "已安装 · 暂不支持自动转换（可手动导出 PDF）"
        else:
            # 探测版本可能是纯版本号，也可能是整行输出（如
            # "LibreOffice 26.2.5.2 build"）——取第一个含数字的词
            version = next((tok for tok in info.version.split() if any(c.isdigit() for c in tok)), "")
            status = f"已安装 · {version}" if version else "已安装"
        rows.append((info, selectable, status))
    return rows


def _auto_status(rows: List[Tuple[EngineInfo, bool, str]]) -> str:
    usable = [info for info, selectable, _ in rows if selectable]
    if not usable:
        return "当前没有可自动转换的引擎"
    return "按检测顺序使用：" + " → ".join(info.name for info in usable)


class SettingsDialog(ctk.CTkToplevel):
    def __init__(self, parent, service: ConversionService,
                 on_saved: Optional[callable] = None):
        super().__init__(parent)
        self.title("系统设置")
        self.geometry("520x430")
        self.resizable(False, False)
        self.attributes("-topmost", True)
        self._service = service
        self._on_saved = on_saved

        ctk.CTkLabel(self, text="系统设置",
                     font=(Fonts.FAMILY, 18, "bold"),
                     text_color=Colors.TEXT_PRIMARY).pack(anchor="w", padx=24, pady=(18, 2))
        ctk.CTkLabel(self, text="打开 Word 文档时，使用哪个已安装的软件转换为 PDF",
                     font=(Fonts.FAMILY, Fonts.SMALL_SIZE),
                     text_color=Colors.TEXT_SECONDARY).pack(anchor="w", padx=24)

        # ── Word 转换引擎 区块 ───────────────────────────────────────
        section = ctk.CTkFrame(self, fg_color=Colors.SURFACE_RAISED, corner_radius=10)
        section.pack(fill="both", expand=True, padx=24, pady=(12, 8))
        ctk.CTkLabel(section, text="Word 转换引擎",
                     font=(Fonts.FAMILY, Fonts.HEADING_SIZE, "bold"),
                     text_color=Colors.TEXT_PRIMARY).pack(anchor="w", padx=16, pady=(12, 4))

        self._rows_frame = ctk.CTkFrame(section, fg_color="transparent")
        self._rows_frame.pack(fill="both", expand=True, padx=8, pady=(0, 4))

        self._choice = ctk.StringVar(value=AUTO_OPTION)
        self._rebuild_rows(refresh=False)

        # ── 底部操作 ─────────────────────────────────────────────────
        bottom = ctk.CTkFrame(self, fg_color="transparent")
        bottom.pack(fill="x", padx=24, pady=(0, 16))
        ctk.CTkButton(bottom, text="↻  重新检测", width=104, height=36,
                      fg_color="transparent", border_width=1,
                      border_color=Colors.BORDER_SUBTLE,
                      hover_color=Colors.SURFACE_OVERLAY,
                      text_color=Colors.TEXT_PRIMARY,
                      command=lambda: self._rebuild_rows(refresh=True)
                      ).pack(side="left")
        ctk.CTkButton(bottom, text="取消", width=88, height=36,
                      fg_color="transparent", border_width=1,
                      border_color=Colors.BORDER_SUBTLE,
                      hover_color=Colors.SURFACE_OVERLAY,
                      text_color=Colors.TEXT_SECONDARY,
                      command=self.destroy).pack(side="right")
        ctk.CTkButton(bottom, text="保存", width=88, height=36,
                      fg_color=Colors.PRIMARY, hover_color=Colors.PRIMARY_HOVER,
                      text_color="white",
                      font=(Fonts.FAMILY, Fonts.BODY_SIZE, "bold"),
                      command=self._save).pack(side="right", padx=(0, 8))

        self.transient(parent)
        self.grab_set()

    # ── 内部 ─────────────────────────────────────────────────────────

    def _rebuild_rows(self, refresh: bool):
        for child in self._rows_frame.winfo_children():
            child.destroy()
        infos = list(self._service.probe_all(refresh=refresh).values())
        rows = build_engine_rows(infos)

        current = self._service.current_preference() or AUTO_OPTION
        selectable_ids = {info.engine_id for info, selectable, _ in rows if selectable}
        if current not in selectable_ids and current != AUTO_OPTION:
            current = AUTO_OPTION
        self._choice.set(current)

        # 自动（推荐）
        auto_row = ctk.CTkFrame(self._rows_frame, fg_color="transparent")
        auto_row.pack(fill="x", pady=3, padx=8)
        ctk.CTkRadioButton(auto_row, text="自动（推荐）", variable=self._choice,
                           value=AUTO_OPTION, height=28,
                           fg_color=Colors.PRIMARY, hover_color=Colors.PRIMARY_HOVER,
                           font=(Fonts.FAMILY, Fonts.BODY_SIZE, "bold"),
                           text_color=Colors.TEXT_PRIMARY).pack(anchor="w")
        ctk.CTkLabel(self._rows_frame, text=_auto_status(rows),
                     font=(Fonts.FAMILY, Fonts.SMALL_SIZE),
                     text_color=Colors.TEXT_SECONDARY).pack(anchor="w", padx=34)

        for info, selectable, status in rows:
            row = ctk.CTkFrame(self._rows_frame, fg_color="transparent")
            row.pack(fill="x", pady=3, padx=8)
            head = ctk.CTkFrame(row, fg_color="transparent")
            head.pack(fill="x")
            radio = ctk.CTkRadioButton(
                head, text=info.name, variable=self._choice,
                value=info.engine_id, height=28,
                fg_color=Colors.PRIMARY, hover_color=Colors.PRIMARY_HOVER,
                font=(Fonts.FAMILY, Fonts.BODY_SIZE),
                text_color=Colors.TEXT_PRIMARY if selectable else Colors.TEXT_TERTIARY,
                state="normal" if selectable else "disabled",
            )
            radio.pack(side="left")
            color = (Colors.TEXT_SECONDARY if selectable else Colors.TEXT_TERTIARY)
            ctk.CTkLabel(row, text=status, font=(Fonts.FAMILY, Fonts.SMALL_SIZE),
                         text_color=color).pack(anchor="w", padx=34)
            # LibreOffice 行：提供内置组件的下载/移除（用户自行决定）
            if info.engine_id == "soffice":
                self._add_driver_action(head, selectable)

    def _add_driver_action(self, head, engine_available: bool):
        """LibreOffice 行右侧：手动指定（探测遗漏时）/ 下载组件 / 移除。"""
        from tkinter import filedialog

        from processing.word_support import paths as lo_paths
        from processing.word_support.driver_manager import DriverManager

        manager = DriverManager()

        def refresh(_installed: bool = False):
            # 也作为 run_driver_install 的 on_done(installed) 回调，
            # 必须能接收一个位置参数
            self._rebuild_rows(refresh=True)

        def locate():
            """用户手动指定已安装的 LibreOffice 目录（探测不是真理）。"""
            chosen = filedialog.askdirectory(
                title="选择 LibreOffice 安装目录\n"
                      "（Windows：包含 program\\soffice.exe 的目录；"
                      "macOS：LibreOffice.app 所在目录）",
                parent=self)
            if not chosen:
                return
            resolved = lo_paths.set_manual_soffice(chosen)
            if resolved is None:
                messagebox.showwarning(
                    "未找到 soffice",
                    f"在所选目录中没有找到 LibreOffice 的 soffice 可执行文件：\n"
                    f"{chosen}\n\n"
                    f"请选择 LibreOffice 的安装目录"
                    f"（或直接选择 soffice 可执行文件）。")
                return
            get_shared_service().probe_all(refresh=True)
            refresh()

        def clear_manual():
            lo_paths.clear_manual_soffice()
            get_shared_service().probe_all(refresh=True)
            refresh()

        manual = lo_paths.get_manual_soffice()

        if manual is not None:
            ctk.CTkButton(
                head, text="取消指定目录", width=100, height=24,
                fg_color="transparent", border_width=1,
                border_color=Colors.BORDER_SUBTLE,
                hover_color=Colors.SURFACE_OVERLAY,
                text_color=Colors.TEXT_SECONDARY,
                font=(Fonts.FAMILY, Fonts.SMALL_SIZE),
                command=clear_manual,
            ).pack(side="right", padx=(4, 0))
        elif not engine_available:
            # 探测无果：手动指定是首选出口，下载是最后手段
            ctk.CTkButton(
                head, text="指定安装目录…", width=110, height=24,
                fg_color="transparent", border_width=1,
                border_color=Colors.BORDER_SUBTLE,
                hover_color=Colors.SURFACE_OVERLAY,
                text_color=Colors.PRIMARY,
                font=(Fonts.FAMILY, Fonts.SMALL_SIZE),
                command=locate,
            ).pack(side="right", padx=(4, 0))

        installed = manager.status()["installed"]
        if not installed:
            from ui.driver_dialogs import run_driver_install
            info = manager.catalog_info()
            if info:
                ctk.CTkButton(
                    head, text=f"下载组件（约 {info.get('size_mb', '?')} MB）",
                    width=150, height=24,
                    fg_color="transparent", border_width=1,
                    border_color=Colors.BORDER_SUBTLE,
                    hover_color=Colors.SURFACE_OVERLAY,
                    text_color=Colors.TEXT_SECONDARY,
                    font=(Fonts.FAMILY, Fonts.SMALL_SIZE),
                    command=lambda: run_driver_install(self, on_done=refresh),
                ).pack(side="right", padx=(4, 0))
        else:
            def remove_driver():
                if messagebox.askyesno(
                        "移除转换组件",
                        "确定移除内置下载的 LibreOffice 组件吗？\n"
                        "（不影响系统安装的任何软件；需要时可再次下载）"):
                    manager.uninstall()
                    refresh()

            ctk.CTkButton(
                head, text="移除组件", width=88, height=24,
                fg_color="transparent", border_width=1,
                border_color=Colors.BORDER_SUBTLE,
                hover_color=Colors.SURFACE_OVERLAY,
                text_color=Colors.TEXT_SECONDARY,
                font=(Fonts.FAMILY, Fonts.SMALL_SIZE),
                command=remove_driver,
            ).pack(side="right", padx=(4, 0))

    def _save(self):
        choice = self._choice.get()
        if choice == AUTO_OPTION:
            self._service.clear_preference()
        else:
            self._service.save_preference(choice)
        if self._on_saved:
            self._on_saved(choice)
        self.destroy()


def open_settings(parent, service: ConversionService, on_saved=None):
    """打开系统设置对话框（模态）。"""
    return SettingsDialog(parent, service, on_saved=on_saved)
