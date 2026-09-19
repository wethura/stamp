"""ControlsPanel 测试"""
import unittest
import tkinter as tk
import customtkinter as ctk
from unittest.mock import MagicMock, patch

from ui.controls_panel import ControlsPanel
from processing.stamp_manager import StampManager, StampData
from processing.stamp_instance import StampInstance


def simulate_ctk6():
    """把 5.2 的公开方法替换成一调用即炸的哨兵，模拟 6.0 的缺失。

    6.0 把 check_if_master_is_canvas 改名成私有 _check_if_valid_scroll，
    Windows 打包版曾因装到 6.0.0 导致每次滚轮都 AttributeError 并连环
    弹「程序遇到问题」模态框。create=True 使其同样适用于已装 6.x 的
    环境（属性本就不存在时补一个哨兵即可）。
    """
    return patch.object(ctk.CTkScrollableFrame, "check_if_master_is_canvas",
                        side_effect=AssertionError("不得依赖 5.2 的方法名"),
                        create=True)


class TestWheelScrollChain(unittest.TestCase):
    """印章列表 ↔ 外层面板的滚轮链路（回归：customtkinter 跨版本崩溃）。"""

    def setUp(self):
        # 不用 tests.gui_support 的共享根：本模块在全量顺序里排第 1，
        # 由它首发共享根会让 CTk 全局追踪器（AppearanceMode/Scaling
        # 的自续订 after 循环）挂上去，与后续 gui_smoke/word_flow 的
        # 第二、第三根生命周期叠加后，共享根上的对话框 update() 会
        # 永不排空（d9a1099 即可复现）。逐测自建 root 维持既有动力学。
        # 注意：图标改造（lru_cache 的 CTkImage 绑定首个 root）落地时
        # 需要迁共享根，届时必须连同上述追踪器问题一起解决。
        self.root = tk.Tk()
        self.root.withdraw()
        self.panel = ControlsPanel(self.root)
        self.panel.pack()
        self.panel.update_idletasks()

    def tearDown(self):
        self.root.destroy()

    @staticmethod
    def _event_on(widget, delta=120):
        ev = MagicMock()
        ev.widget = widget
        ev.delta = delta
        return ev

    def test_inner_list_ignores_wheel_outside_itself(self):
        """事件落在外层控件上：印章列表不响应、不报错、不依赖库内部方法。"""
        with simulate_ctk6():
            self.panel._scroll_frame._mouse_wheel_all(
                self._event_on(self.panel._size_slider))
        self.assertEqual(self.panel._scroll_frame._parent_canvas.yview(),
                         (0.0, 1.0))

    def test_panel_skips_wheel_inside_stamp_list(self):
        """事件落在印章列表内：外层面板让位，且不得调用库的 5.2 方法名。"""
        inner = self.panel._scroll_frame
        with simulate_ctk6():
            self.panel._mouse_wheel_all(
                self._event_on(inner._parent_canvas))

    def test_list_overflow_chains_to_outer_panel(self):
        """列表滚到边界后增量交给外层面板继续滚动。

        事件向下滚（delta<0，Windows 一格 = -120）且列表已在底部
        不可再滚时，外层面板接管同一方向的滚动。
        """
        ctk.CTkFrame(self.panel, height=2000, fg_color="transparent").grid(
            row=50, column=0, sticky="ew")
        self.root.update()
        before = self.panel._parent_canvas.yview()
        inner = self.panel._scroll_frame
        inner._mouse_wheel_all(self._event_on(inner._parent_canvas, delta=-120))
        self.root.update()
        after = self.panel._parent_canvas.yview()
        self.assertGreater(after[0], before[0])


class TestDeleteButton(unittest.TestCase):
    """删除按钮相关测试"""

    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.panel = ControlsPanel(self.root)
        self.panel.pack()
        self.panel.update_idletasks()

        self.mock_manager = MagicMock(spec=StampManager)
        self.panel.set_stamp_manager(self.mock_manager)

    def tearDown(self):
        self.root.destroy()

    def _create_mock_stamp(self, stamp_id, name="测试章"):
        stamp = MagicMock(spec=StampData)
        stamp.id = stamp_id
        stamp.name = name
        from PIL import Image
        img = Image.new("RGBA", (100, 100), color=(255, 0, 0, 255))
        stamp.get_image.return_value = img
        return stamp

    def test_cards_have_no_delete_button(self):
        stamp = self._create_mock_stamp("stamp1", "章A")
        self.mock_manager.list_stamps.return_value = [stamp]
        self.mock_manager.get_stamp.return_value = stamp
        self.panel._refresh_stamp_list()
        self.panel.update_idletasks()

        children = self.panel._scroll_frame.winfo_children()
        self.assertEqual(len(children), 1)
        self.assertFalse(any(isinstance(widget, (tk.Button, ctk.CTkButton))
                             for widget in children[0].winfo_children()))

    # @dod delete-confirm-dialog v1.0
    @patch("ui.controls_panel.messagebox.askyesno")
    def test_delete_confirm_cancel(self, mock_askyesno):
        stamp = self._create_mock_stamp("stamp1", "章A")
        self.mock_manager.list_stamps.return_value = [stamp]
        self.mock_manager.get_stamp.return_value = stamp
        self.panel._refresh_stamp_list()
        self.panel.update_idletasks()

        mock_askyesno.return_value = False

        self.assertFalse(self.panel._delete_stamp("stamp1"))
        mock_askyesno.assert_called_once()

        self.mock_manager.delete_stamp.assert_not_called()

    # @dod delete-confirm-dialog v1.0
    @patch("ui.controls_panel.messagebox.askyesno")
    def test_delete_confirm_ok(self, mock_askyesno):
        stamp = self._create_mock_stamp("stamp1", "章A")
        self.mock_manager.list_stamps.return_value = [stamp]
        self.mock_manager.get_stamp.return_value = stamp
        self.panel._refresh_stamp_list()
        self.panel.update_idletasks()

        mock_askyesno.return_value = True

        self.panel._delete_stamp("stamp1")

        self.mock_manager.delete_stamp.assert_called_once_with("stamp1")

    # @dod delete-editing-cleared v1.0
    @patch("ui.controls_panel.messagebox.askyesno")
    def test_delete_editing_stamp_clears_edit_state(self, mock_askyesno):
        stamp_a = self._create_mock_stamp("stamp1", "章A")
        stamp_b = self._create_mock_stamp("stamp2", "章B")
        self.mock_manager.list_stamps.return_value = [stamp_a, stamp_b]
        self.mock_manager.get_stamp.return_value = stamp_a
        self.panel._refresh_stamp_list()
        self.panel.update_idletasks()

        mock_askyesno.return_value = True

        # Set up editing instance for template that is being deleted
        mock_instance_manager = MagicMock()
        mock_inst = StampInstance(
            instance_id="inst1", template_id="stamp1", page_index=0
        )
        mock_instance_manager.get_instance.return_value = mock_inst
        self.panel._instance_manager = mock_instance_manager
        self.panel._editing_instance_id = "inst1"

        self.panel._delete_stamp("stamp1")

        # Editing instance should be cleared since the template was deleted
        self.assertIsNone(self.panel._editing_instance_id)

    # @dod delete-last-empty v1.0
    @patch("ui.controls_panel.messagebox.askyesno")
    def test_delete_last_stamp_empty_list(self, mock_askyesno):
        stamp = self._create_mock_stamp("stamp1", "章A")
        self.mock_manager.list_stamps.return_value = [stamp]
        self.mock_manager.get_stamp.return_value = stamp
        self.panel._refresh_stamp_list()
        self.panel.update_idletasks()

        mock_askyesno.return_value = True

        self.panel._delete_stamp("stamp1")

        self.mock_manager.list_stamps.return_value = []
        self.panel._refresh_stamp_list()


if __name__ == "__main__":
    unittest.main()
