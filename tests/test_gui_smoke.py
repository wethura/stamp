"""GUI 冒烟回归：预览导航/选中拖拽删除/键盘/页码指示的边界行为。

曾摇出并守护两个真 bug：
- 删除实例/模板后画布选中态未清，方向键被死选中"吞掉"不再滚动
- 页码指示与活动页不同步

需要可用显示环境；无显示时整类跳过。所有用例共享一个 CTk 根窗口
（同进程反复创建 CTk 会挂死）。
"""
import tempfile
import unittest
from unittest import mock
from unittest.mock import MagicMock

from PIL import Image

from app import App
from processing.stamp_instance import StampInstanceManager
from processing.stamp_manager import StampManager
from ui.main_window import MainWindow


class TestGuiSmoke(unittest.TestCase):
    @classmethod
    def _pump(cls, rounds: int = 3):
        """多轮事件泵：Windows 下一轮 update 可能不足以完成子组件布局，
        canvas 未 sizing 会让渲染早退、页码指示停在前一状态。"""
        for _ in range(rounds):
            cls.root.update_idletasks()
            cls.root.update()

    @classmethod
    def setUpClass(cls):
        try:
            import customtkinter as ctk
        except Exception:
            raise unittest.SkipTest("customtkinter 不可用")
        try:
            cls.root = ctk.CTk()
            # 映射到屏幕外：winfo 尺寸/渲染依赖真实映射，又不闪屏打扰
            cls.root.geometry("1200x800+4000+4000")
            # 接管默认根身份：预览画布的 PhotoImage 隐式绑定
            # tkinter._default_root，必须建在本类自己的解释器里
            #（销毁后 tests.gui_support 的共享根会自动补位）
            import tkinter as tk
            tk._default_root = cls.root
        except Exception:
            raise unittest.SkipTest("无可用显示环境")
        cls.app = App()
        cls.window = MainWindow(cls.root, cls.app)
        cls.app.window = cls.window
        cls._pump()
        cls.app.pages = [Image.new("RGB", (800, 1130)) for _ in range(6)]
        cls.app.instance_manager = StampInstanceManager()
        cls.window.controls.set_instance_manager(cls.app.instance_manager)
        cls._img = Image.new("RGBA", (100, 100), (200, 0, 0, 255))
        cls.app.get_template_image = lambda tid: cls._img
        cls.app._refresh_preview()
        cls._pump()

    @classmethod
    def tearDownClass(cls):
        try:
            cls.root.destroy()
        except Exception:
            pass

    def setUp(self):
        """每用例回到第一页的干净导航状态。"""
        self.window.preview.reset_view()
        self._pump()

    def _refresh(self):
        self.app._refresh_preview()
        self._pump()

    def _click_at(self, page, ratio):
        pv = self.window.preview
        pv.scroll_to_page(page)
        self._pump()
        total = pv._page_offsets[-1] + pv._page_display_sizes[-1][1]
        view_top = pv.canvas.yview()[0] * total
        ev = MagicMock()
        ev.x = int(pv._page_display_sizes[page][0] * ratio)
        ev.y = int(pv._page_offsets[page] + pv._page_display_sizes[page][1] * ratio - view_top)
        pv._on_press(ev)
        return ev

    # ── 页码导航 ─────────────────────────────────────────────────────

    def test_load_shows_indicator_and_disables_prev(self):
        w = self.window
        self.assertEqual(w._page_label.cget("text"), "第 1 / 6 页")
        self.assertEqual(str(w._prev_page_btn.cget("state")), "disabled")
        self.assertNotEqual(str(w._next_page_btn.cget("state")), "disabled")

    def test_scroll_to_page_clamps_and_updates_indicator(self):
        pv = self.window.preview
        pv.scroll_to_page(99)
        self._pump()
        self.assertEqual(pv.get_active_page(), 5)
        self.assertEqual(self.app.active_page, 5)
        self.assertEqual(self.window._page_label.cget("text"), "第 6 / 6 页")
        self.assertEqual(str(self.window._next_page_btn.cget("state")), "disabled")
        pv.scroll_to_page(-5)
        self.assertEqual(pv.get_active_page(), 0)

    def test_click_hits_correct_page(self):
        ev = self._click_at(4, 0.05)
        pv = self.window.preview
        self._pump()
        self.assertEqual(pv.get_active_page(), 4)
        self.assertEqual(self.app.active_page, 4)
        self.assertIsNone(pv._selected_instance_id)

    def test_reset_view_returns_to_first_page(self):
        pv = self.window.preview
        pv.scroll_to_page(5)
        pv.reset_view()
        self._pump()
        self.assertEqual(pv.get_active_page(), 0)
        self.assertEqual(self.window._page_label.cget("text"), "第 1 / 6 页")

    # ── 印章交互 ─────────────────────────────────────────────────────

    def _add_stamp_on_page(self, page, pos=(0.4, 0.4)):
        inst = self.app.instance_manager.add_instance("tmpl", page)
        inst.pos_x, inst.pos_y = pos
        self._refresh()
        return inst

    def test_select_drag_release(self):
        inst = self._add_stamp_on_page(4)
        ev = self._click_at(4, 0.4)
        pv = self.window.preview
        self.assertEqual(pv._selected_instance_id, inst.instance_id)
        evm = MagicMock()
        evm.x = ev.x
        evm.y = ev.y + int(pv._page_display_sizes[4][1] * 0.10)
        pv._on_drag(evm)
        self.assertAlmostEqual(inst.pos_y, 0.50, delta=0.02)
        pv._on_release(MagicMock())
        self.assertIsNone(pv._dragging_instance_id)

    def test_delete_clears_canvas_selection_so_arrows_scroll(self):
        inst = self._add_stamp_on_page(0)
        pv = self.window.preview
        pv._selected_instance_id = inst.instance_id
        self.app._selected_instance_id = inst.instance_id
        pv._on_backspace(None)
        self._refresh()
        self.assertIsNone(self.app.instance_manager.get_instance(inst.instance_id))
        self.assertIsNone(pv._selected_instance_id, "删除后画布选中必须清空")
        pv.canvas.yview_moveto(0)
        before = pv.canvas.yview()[0]
        pv._on_arrow_key(0, 1)
        self.assertNotEqual(pv.canvas.yview()[0], before, "方向键应回到滚动模式")

    def test_template_deletion_clears_canvas_selection(self):
        mgr = StampManager(tempfile.mkdtemp())
        old = self.app.stamp_manager
        self.app.stamp_manager = mgr
        self.window.controls.set_stamp_manager(mgr)
        try:
            tmpl = mgr.add_stamp("t", self._img)
            inst = self.app.instance_manager.add_instance(tmpl.id, 0)
            self._refresh()
            pv = self.window.preview
            pv._selected_instance_id = inst.instance_id
            self.app._selected_instance_id = inst.instance_id
            mgr.delete_stamp(tmpl.id)
            self.app.on_stamp_library_changed()
            self._refresh()
            self.assertIsNone(pv._selected_instance_id, "删模板后画布选中必须清空")
            self.assertIsNone(self.app.instance_manager.get_instance(inst.instance_id))
        finally:
            self.app.stamp_manager = old
            self.window.controls.set_stamp_manager(old)
            self._refresh()

    def test_arrows_scroll_without_selection_and_nudge_with(self):
        pv = self.window.preview
        pv._selected_instance_id = None
        pv.canvas.yview_moveto(0)
        self._pump()
        before = pv.canvas.yview()[0]
        pv._on_arrow_key(0, 1)
        self.assertNotEqual(pv.canvas.yview()[0], before)

        inst = self._add_stamp_on_page(1)
        pv._selected_instance_id = inst.instance_id
        x0 = inst.pos_x
        pv._on_arrow_key(1, 0)
        self.assertAlmostEqual(inst.pos_x, x0 + 0.005, places=6)

    # ── 面板行为 ─────────────────────────────────────────────────────

    def test_rotation_entry_restores_on_invalid_input(self):
        inst = self.app.instance_manager.add_instance("tmpl", 0)
        cp = self.window.controls
        cp.set_editing_instance(inst.instance_id)
        cp._rotation_entry.delete(0, "end")
        cp._rotation_entry.insert(0, "abc")
        cp._on_rotation_entry()
        self.assertEqual(cp._rotation_entry.get(), "0")

    def test_rotation_entry_valid_input_calls_back(self):
        inst = self.app.instance_manager.add_instance("tmpl", 0)
        cp = self.window.controls
        cp.set_editing_instance(inst.instance_id)
        with mock.patch.object(cp, "on_instance_property_changed", autospec=True) as mocked:
            cp._rotation_entry.delete(0, "end")
            cp._rotation_entry.insert(0, "90")
            cp._on_rotation_entry()
            self.assertTrue(mocked.called)
            self.assertEqual(mocked.call_args[1].get("rotation"), 90)

    def test_empty_library_shows_placeholder(self):
        mgr = StampManager(tempfile.mkdtemp())
        old = self.app.stamp_manager
        self.app.stamp_manager = mgr
        self.window.controls.set_stamp_manager(mgr)
        try:
            children = self.window.controls._scroll_frame.winfo_children()
            self.assertTrue(any("尚未添加印章" in c.cget("text")
                                for c in children if hasattr(c, "cget")))
        finally:
            self.app.stamp_manager = old
            self.window.controls.set_stamp_manager(old)

    def test_card_drop_lands_on_active_page(self):
        created = []
        cp = self.window.controls
        cp.on_create_instance = lambda tid: (created.append(tid),
                                             self.app.create_instance_from_template(tid))
        cp._drag_template_id = "tmpl"
        pv = self.window.preview
        self.app.active_page = 3
        cp._on_stamp_drag_release(MagicMock(x_root=pv.winfo_rootx() + 50,
                                            y_root=pv.winfo_rooty() + 50))
        self._pump()
        self.assertEqual(created, ["tmpl"])
        instances = self.app.instance_manager.list_instances()
        self.assertEqual(instances[-1].page_index, 3)


if __name__ == "__main__":
    unittest.main()
