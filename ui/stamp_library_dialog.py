"""Focused library maintenance window; edits are saved explicitly."""

from tkinter import filedialog, messagebox

import customtkinter as ctk

from processing.stamp import load_stamp
from ui.theme import Colors, Fonts


class StampLibraryDialog(ctk.CTkToplevel):
    def __init__(self, parent, manager, on_changed, on_delete):
        super().__init__(parent)
        self.title("管理印章")
        self.geometry("720x500")
        self.minsize(660, 460)
        self.configure(fg_color=Colors.SURFACE_BASE)
        self.transient(parent)
        self._manager = manager
        self._on_changed = on_changed
        self._on_delete = on_delete
        self._selected_id = None
        self._replacement = None
        self._buttons = {}
        self.protocol("WM_DELETE_WINDOW", self._close)
        self.bind("<Escape>", lambda event: self._close())
        self._build_ui()
        self._refresh_list()
        self.wait_visibility()
        self.grab_set()

    def _build_ui(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(1, weight=1)
        ctk.CTkLabel(
            self, text="管理印章", font=(Fonts.FAMILY, 20, "bold"),
            text_color=Colors.TEXT_PRIMARY,
        ).grid(row=0, column=0, columnspan=2, sticky="w", padx=24, pady=(20, 12))

        library = ctk.CTkFrame(self, width=220, fg_color=Colors.SURFACE_RAISED)
        library.grid(row=1, column=0, sticky="nsew", padx=(24, 12), pady=(0, 20))
        library.grid_columnconfigure(0, weight=1)
        library.grid_rowconfigure(1, weight=1)
        self._count = ctk.CTkLabel(library, text="", text_color=Colors.TEXT_SECONDARY)
        self._count.grid(row=0, column=0, sticky="w", padx=12, pady=8)
        self._list = ctk.CTkScrollableFrame(library, width=190, fg_color="transparent")
        self._list.grid(row=1, column=0, sticky="nsew", padx=4, pady=(0, 8))
        self._list.grid_columnconfigure(0, weight=1)

        editor = ctk.CTkFrame(self, fg_color="transparent")
        editor.grid(row=1, column=1, sticky="nsew", padx=(0, 24), pady=(0, 20))
        editor.grid_columnconfigure(0, weight=1)
        editor.grid_rowconfigure(0, weight=1)
        self._preview = ctk.CTkLabel(
            editor, text="暂无印章", height=190,
            fg_color=Colors.SURFACE_RAISED, corner_radius=10,
            text_color=Colors.TEXT_SECONDARY,
        )
        self._preview.grid(row=0, column=0, sticky="nsew", pady=(0, 8))
        self._details = ctk.CTkLabel(editor, text="", text_color=Colors.TEXT_TERTIARY, height=20)
        self._details.grid(row=1, column=0, sticky="w")
        ctk.CTkLabel(editor, text="印章名称", text_color=Colors.TEXT_SECONDARY).grid(row=2, column=0, sticky="w")
        self._name = ctk.CTkEntry(editor, height=34, font=(Fonts.FAMILY, Fonts.BODY_SIZE))
        self._name.grid(row=3, column=0, sticky="ew", pady=(0, 8))
        self._replace = ctk.CTkButton(
            editor, text="替换图片…", height=32,
            fg_color=Colors.SURFACE_RAISED, hover_color=Colors.SURFACE_OVERLAY,
            text_color=Colors.TEXT_PRIMARY, command=self._replace_image,
        )
        self._replace.grid(row=4, column=0, sticky="w")
        ctk.CTkLabel(
            editor, text="保存后，当前文档中使用此章的位置也会更新。",
            wraplength=350, justify="left", text_color=Colors.TEXT_SECONDARY,
            font=(Fonts.FAMILY, Fonts.SMALL_SIZE),
        ).grid(row=5, column=0, sticky="w", pady=8)
        actions = ctk.CTkFrame(editor, fg_color="transparent")
        actions.grid(row=6, column=0, sticky="ew")
        actions.grid_columnconfigure(1, weight=1)
        self._delete = ctk.CTkButton(
            actions, text="删除印章", width=90, height=34,
            fg_color=Colors.SURFACE_RAISED, hover_color=Colors.SURFACE_OVERLAY,
            text_color=Colors.DANGER, command=self._delete_selected,
        )
        self._delete.grid(row=0, column=0)
        self._save = ctk.CTkButton(
            actions, text="保存修改", width=110, height=34,
            fg_color=Colors.PRIMARY, hover_color=Colors.PRIMARY_HOVER,
            text_color="#FFFFFF", command=self._save_selected,
        )
        self._save.grid(row=0, column=2)

    def _refresh_list(self, selected_id=None):
        for child in self._list.winfo_children():
            child.destroy()
        self._buttons.clear()
        stamps = self._manager.list_stamps()
        self._count.configure(text=f"印章库 · {len(stamps)} 枚")
        for index, stamp in enumerate(stamps):
            name = stamp.name if len(stamp.name) <= 12 else stamp.name[:11] + "…"
            button = ctk.CTkButton(
                self._list, text=name, anchor="w", height=38,
                fg_color="transparent", hover_color=Colors.SURFACE_OVERLAY,
                text_color=Colors.TEXT_PRIMARY, font=(Fonts.FAMILY, Fonts.BODY_SIZE),
                command=lambda sid=stamp.id: self._select(sid),
            )
            button.grid(row=index, column=0, sticky="ew", pady=2)
            self._buttons[stamp.id] = button
        if not stamps:
            ctk.CTkLabel(self._list, text="请先在主窗口导入印章", wraplength=170,
                         text_color=Colors.TEXT_SECONDARY).grid(row=0, column=0, pady=20)
        target = selected_id if selected_id in self._buttons else (stamps[0].id if stamps else None)
        self._load_selection(target)

    def _dirty(self):
        stamp = self._manager.get_stamp(self._selected_id)
        return stamp is not None and (self._replacement is not None or self._name.get() != stamp.name)

    def _discard_changes(self):
        return not self._dirty() or messagebox.askyesno(
            "放弃修改", "当前印章有未保存的修改，确定要放弃吗？", parent=self)

    def _select(self, stamp_id):
        if stamp_id != self._selected_id and self._discard_changes():
            self._load_selection(stamp_id)

    def _load_selection(self, stamp_id):
        self._selected_id = stamp_id
        self._replacement = None
        stamp = self._manager.get_stamp(stamp_id)
        for sid, button in self._buttons.items():
            button.configure(fg_color=Colors.SURFACE_OVERLAY if sid == stamp_id else "transparent")
        self._name.configure(state="normal")
        self._name.delete(0, "end")
        state = "normal" if stamp else "disabled"
        for widget in (self._replace, self._delete, self._save):
            widget.configure(state=state)
        if stamp:
            self._name.insert(0, stamp.name)
            self._show_image(stamp.get_image())
        else:
            self._preview.configure(image=None, text="暂无印章\n关闭此窗口后，点击「导入印章」开始添加")
            self._details.configure(text="")
        self._name.configure(state=state)

    def _show_image(self, image):
        preview = image.copy()
        preview.thumbnail((280, 180))
        self._photo = ctk.CTkImage(light_image=preview, dark_image=preview, size=preview.size)
        self._preview.configure(image=self._photo, text="")
        suffix = " · 待保存" if self._replacement is not None else ""
        self._details.configure(text=f"{image.width} × {image.height} 像素{suffix}")

    def _replace_image(self):
        path = filedialog.askopenfilename(
            parent=self, title="替换印章图片",
            filetypes=[("图片文件", "*.jpg *.jpeg *.png *.bmp *.tiff *.tif *.webp")],
        )
        if not path:
            return
        try:
            image = load_stamp(path)
        except Exception as exc:
            messagebox.showerror("加载失败", f"无法加载图片：{exc}", parent=self)
            return
        self._replacement = image
        self._show_image(image)

    def _save_selected(self):
        if self._selected_id is None:
            return
        name = self._name.get().strip()
        if not name:
            messagebox.showwarning("名称不能为空", "请输入印章名称。", parent=self)
            self._name.focus_set()
            return
        try:
            self._manager.update_stamp(self._selected_id, name=name, image=self._replacement)
        except Exception as exc:
            messagebox.showerror("保存失败", str(exc), parent=self)
            return
        self._on_changed()
        self._refresh_list(self._selected_id)
        self._details.configure(text=self._details.cget("text") + " · 已保存")

    def _delete_selected(self):
        if self._selected_id is None:
            return
        try:
            deleted = self._on_delete(self._selected_id, parent=self)
        except Exception as exc:
            messagebox.showerror("删除失败", str(exc), parent=self)
            return
        if deleted:
            self._refresh_list()

    def _close(self):
        if self._discard_changes():
            self.grab_release()
            self.destroy()
