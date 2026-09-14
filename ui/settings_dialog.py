"""系统设置对话框：Word 转换引擎选择（基于本机安装探测）。

引擎可见性按环境决定：未安装的显示「未安装」；已安装但接口未验证的
（macOS WPS）显示「暂不支持自动转换」；可用引擎可选为首选并持久化。
"""
from typing import List, Optional, Tuple

import customtkinter as ctk

from processing.word_support.engines import EngineInfo
from processing.word_support.service import ConversionService
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
            radio = ctk.CTkRadioButton(
                row, text=info.name, variable=self._choice,
                value=info.engine_id, height=28,
                fg_color=Colors.PRIMARY, hover_color=Colors.PRIMARY_HOVER,
                font=(Fonts.FAMILY, Fonts.BODY_SIZE),
                text_color=Colors.TEXT_PRIMARY if selectable else Colors.TEXT_TERTIARY,
                state="normal" if selectable else "disabled",
            )
            radio.pack(anchor="w")
            color = (Colors.TEXT_SECONDARY if selectable else Colors.TEXT_TERTIARY)
            ctk.CTkLabel(row, text=status, font=(Fonts.FAMILY, Fonts.SMALL_SIZE),
                         text_color=color).pack(anchor="w", padx=34)

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
