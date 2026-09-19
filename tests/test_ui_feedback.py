"""UI 反馈组件测试：统一图标集 / Tooltip / Toast / 工具栏动作可用性。

轻量控件一律复用 tests.gui_support 的共享 CTk 根（同进程反复建根会崩）。
"""
import unittest
from unittest.mock import MagicMock

from PIL import Image

from tests.gui_support import shared_ctk_root
from ui.feedback import Tooltip, show_toast
from ui.icons import AVAILABLE, _render, get_icon


class TestIconSet(unittest.TestCase):
    """程序化图标集：每个图标必须画出东西，且按参数缓存。"""

    def test_all_icons_render_nonblank(self):
        for name in AVAILABLE:
            img = _render(name, "#292925")
            self.assertEqual(img.size, (96, 96))
            bbox = img.getchannel("A").getbbox()
            self.assertIsNotNone(bbox, f"图标 {name} 渲染为空白")

    def test_unknown_icon_raises(self):
        with self.assertRaises(KeyError):
            get_icon("no-such-icon")

    def test_pil_render_cached_but_instances_fresh(self):
        shared_ctk_root()  # CTkImage 构造环境与生产一致
        a = get_icon("printer", 18, "#B63D32")
        b = get_icon("printer", 18, "#B63D32")
        # PhotoImage 绑定 Tk 解释器，CTkImage 不得跨根复用（曾致
        # "image pyimage doesn't exist"）；PIL 渲染则应缓存复用
        self.assertIsNot(a, b, "每次取图应是新建的 CTkImage")
        self.assertIs(a._light_image, b._light_image, "PIL 绘制结果应缓存")


class TestTooltipAndToast(unittest.TestCase):
    """悬停提示与非阻塞通知的基础行为。"""

    def setUp(self):
        self.root = shared_ctk_root()

    def test_tooltip_show_update_hide(self):
        import customtkinter as ctk
        btn = ctk.CTkButton(self.root, text="按钮")
        btn.pack()
        self.root.update_idletasks()

        tip = Tooltip(btn, "提示文案")
        tip._show()
        self.assertIsNotNone(tip._tip)
        self.assertEqual(tip._label.cget("text"), "提示文案")

        tip.set_text("更新后的提示")
        self.assertEqual(tip._label.cget("text"), "更新后的提示")

        tip._hide()
        self.assertIsNone(tip._tip)
        btn.destroy()

    def test_toast_stacks_and_dismisses(self):
        import customtkinter as ctk
        frame = ctk.CTkFrame(self.root, width=400, height=300)
        frame.pack()
        self.root.update_idletasks()

        # 清掉可能残留的旧通知，确保计数从零开始
        stale = getattr(self.root, "_toast_manager", None)
        if stale is not None:
            for card in list(stale._stack):
                card.dismiss()

        card1 = show_toast(frame, "第一条通知", kind="success")
        self.root.update_idletasks()
        card2 = show_toast(frame, "第二条通知", kind="info",
                           action_text="查看")
        self.root.update_idletasks()

        manager = self.root._toast_manager
        self.assertEqual(manager.active_count, 2, "两条通知应同时在场并堆叠")
        card1.dismiss()
        card2.dismiss()
        self.assertEqual(manager.active_count, 0)
        frame.destroy()


class TestTooltipStormRegressions(unittest.TestCase):
    """回归（2026-09-19 用户实机）：悬停印章后弹窗全黑、运行久了假死。

    根因：置顶 override 提示窗盖住指针 → 系统持续合成 Enter/Leave →
    「显示→隐藏→再显示」无限建窗循环；且每次 _enter 用 add="+" 重复
    绑定，回调随悬停次数线性累积。以下断言守住这三条纪律。
    """

    def setUp(self):
        self.root = shared_ctk_root()

    def test_repeated_enter_does_not_accumulate_bindings(self):
        import tkinter as tk
        label = tk.Label(self.root, text="宿主")
        label.pack()
        tip = Tooltip(label, "提示")
        tip._bind_tree(label)
        first = label.bind("<Enter>")
        self.assertTrue(first, "首次绑树后应存在 Enter 绑定")
        for _ in range(5):
            tip._enter()   # 旧行为：每次 _enter 重复 add="+" 累积脚本
        self.assertEqual(label.bind("<Enter>"), first,
                         "重复 _enter 不得累积绑定脚本")
        label.destroy()

    def test_tip_repositioned_away_from_pointer(self):
        import tkinter as tk
        label = tk.Label(self.root, text="宿主")
        label.pack()
        self.root.update_idletasks()
        tip = Tooltip(label, "一段足够长的提示文案，让提示窗有一定宽度")
        # 指针正好落在提示窗的默认落点上（下方分支）
        px = label.winfo_rootx() + label.winfo_width() // 2
        py = label.winfo_rooty() + label.winfo_height() + 20
        label.winfo_pointerx = lambda: px
        label.winfo_pointery = lambda: py
        tip._show()
        try:
            self.root.update()
            tx = tip._tip.winfo_rootx()
            ty = tip._tip.winfo_rooty()
            tw = tip._tip.winfo_width()
            th = tip._tip.winfo_height()
            covered = tx <= px < tx + tw and ty <= py < ty + th
            self.assertFalse(covered, "提示窗不得覆盖指针位置")
        finally:
            tip._hide()
            label.destroy()

    def test_tip_is_inwindow_placed_child(self):
        """提示必须是宿主窗口内部的 place 子控件，不创建新窗口。

        （回归：override Toplevel 在 macOS 上渲染成 200×200pt 黑色
        方块——映射时不取内容尺寸。）
        """
        import tkinter as tk
        label = tk.Label(self.root, text="宿主")
        label.pack()
        self.root.update_idletasks()
        tip = Tooltip(label, "提示")
        tip._show()
        try:
            self.assertEqual(tip._tip.winfo_manager(), "place")
            self.assertIs(tip._tip.master, self.root,
                          "提示宿主应为所在窗口，而非新 Toplevel")
            self.assertEqual(str(tip._tip.winfo_class()), "Frame")
        finally:
            tip._hide()
            label.destroy()


class TestToolbarActionStates(unittest.TestCase):
    """工具栏导出/打印的可用性三态联动。"""

    def setUp(self):
        self.root = shared_ctk_root()
        self.controller = MagicMock()
        from ui.main_window import MainWindow
        self.window = MainWindow(self.root, self.controller)
        self.root.update_idletasks()

    def tearDown(self):
        try:
            self.window.destroy()
        except Exception:  # noqa: BLE001
            pass

    def _state(self, btn):
        return str(btn.cget("state"))

    def test_actions_disabled_without_document(self):
        self.assertEqual(self._state(self.window._export_btn), "disabled")
        self.assertEqual(self._state(self.window._print_btn), "disabled")
        self.assertIn("先打开", self.window._export_tooltip._text)

    def test_actions_enabled_with_document_and_stamp(self):
        self.window.update_action_states(has_document=True, has_stamps=True)
        self.assertEqual(self._state(self.window._export_btn), "normal")
        self.assertEqual(self._state(self.window._print_btn), "normal")
        self.assertIn("保持不变", self.window._export_tooltip._text)

    def test_document_without_stamp_hints_next_step(self):
        self.window.update_action_states(has_document=True, has_stamps=False)
        self.assertEqual(self._state(self.window._export_btn), "disabled")
        self.assertIn("印章", self.window._print_tooltip._text)


class TestAppAvailabilityWiring(unittest.TestCase):
    """App 侧：预览刷新后把可用性同步给主窗口。"""

    def test_refresh_preview_updates_action_states(self):
        from app import App
        from processing.stamp_instance import StampInstanceManager

        app = App()
        app.window = MagicMock()
        app.handler = MagicMock()
        app.doc_path = "/tmp/sample.pdf"
        app.pages = [Image.new("RGB", (10, 10))]
        app.instance_manager = StampInstanceManager()
        app.instance_manager.add_instance("template-1", 0)
        app.get_page_stamp_data = lambda i: app.instance_manager.get_page_instances(i)
        app.get_template_image = lambda tid: None

        app._refresh_preview()

        app.window.update_action_states.assert_called_once_with(True, True)
        app.window.preview.update_all_pages.assert_called_once()


if __name__ == "__main__":
    unittest.main()
