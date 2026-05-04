"""ControlsPanel 测试"""
import unittest
import tkinter as tk
from unittest.mock import MagicMock, patch

from ui.controls_panel import ControlsPanel, StampSelection
from processing.stamp_manager import StampManager, StampData


class TestDeleteButton(unittest.TestCase):
    """删除按钮相关测试"""

    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.panel = ControlsPanel(self.root)
        self.panel.pack()
        self.panel.update_idletasks()

        # 创建 mock stamp manager
        self.mock_manager = MagicMock(spec=StampManager)
        self.panel.set_stamp_manager(self.mock_manager)

    def tearDown(self):
        self.root.destroy()

    def _create_mock_stamp(self, stamp_id, name="测试章"):
        """创建 mock stamp 数据"""
        stamp = MagicMock(spec=StampData)
        stamp.id = stamp_id
        stamp.name = name
        stamp.size_ratio = 0.2
        stamp.pos_x = 0.7
        stamp.pos_y = 0.7
        stamp.opacity = 1.0
        # 创建一个小图片
        from PIL import Image
        img = Image.new("RGBA", (100, 100), color=(255, 0, 0, 255))
        stamp.get_image.return_value = img
        return stamp

    # @dod delete-btn-visible v1.0
    def test_delete_button_visible(self):
        """删除按钮可见且不被遮挡"""
        stamp = self._create_mock_stamp("stamp1", "章A")
        self.mock_manager.list_stamps.return_value = [stamp]
        self.panel._refresh_stamp_list()
        self.panel.update_idletasks()

        # 检查每个章项底部是否有删除按钮
        children = self.panel._stamp_inner.winfo_children()
        self.assertEqual(len(children), 1)

        container = children[0]
        container_children = container.winfo_children()

        # 查找删除按钮（应为 tk.Button 或 tk.Label，text="删除"）
        delete_btn = None
        for w in container_children:
            if isinstance(w, (tk.Button, tk.Label)) and w.cget("text") == "删除":
                delete_btn = w
                break

        self.assertIsNotNone(delete_btn, "应存在 text='删除' 的按钮")
        self.assertEqual(delete_btn.cget("fg"), "red")

    # @dod delete-confirm-dialog v1.0
    @patch("ui.controls_panel.messagebox.askyesno")
    def test_delete_confirm_cancel(self, mock_askyesno):
        """点击删除后取消，章仍在列表中"""
        stamp = self._create_mock_stamp("stamp1", "章A")
        self.mock_manager.list_stamps.return_value = [stamp]
        self.panel._refresh_stamp_list()
        self.panel.update_idletasks()

        mock_askyesno.return_value = False

        # 模拟点击删除按钮
        container = self.panel._stamp_inner.winfo_children()[0]
        for w in container.winfo_children():
            if isinstance(w, (tk.Button, tk.Label)) and w.cget("text") == "删除":
                # 触发点击事件
                w.event_generate("<Button-1>")
                break

        # 取消后不应调用 delete_stamp
        self.mock_manager.delete_stamp.assert_not_called()

    # @dod delete-confirm-dialog v1.0
    @patch("ui.controls_panel.messagebox.askyesno")
    def test_delete_confirm_ok(self, mock_askyesno):
        """点击删除后确认，章被移除"""
        stamp = self._create_mock_stamp("stamp1", "章A")
        self.mock_manager.list_stamps.return_value = [stamp]
        self.panel._refresh_stamp_list()
        self.panel.update_idletasks()

        mock_askyesno.return_value = True

        # 直接调用 _delete_stamp 方法（模拟点击删除按钮后的行为）
        self.panel._delete_stamp("stamp1")

        self.mock_manager.delete_stamp.assert_called_once_with("stamp1")

    # @dod delete-sync-selected v1.0
    @patch("ui.controls_panel.messagebox.askyesno")
    def test_delete_sync_selected_state(self, mock_askyesno):
        """删除章A后，章B仍保持选中状态"""
        stamp_a = self._create_mock_stamp("stamp1", "章A")
        stamp_b = self._create_mock_stamp("stamp2", "章B")
        self.mock_manager.list_stamps.return_value = [stamp_a, stamp_b]
        self.panel._refresh_stamp_list()
        self.panel.update_idletasks()

        # 选中两个章
        self.panel._selected_stamp_ids = {"stamp1", "stamp2"}
        self.panel._update_all_dots()

        mock_askyesno.return_value = True

        # 删除章A
        self.panel._delete_stamp("stamp1")

        # 章B应仍被选中
        self.assertIn("stamp2", self.panel._selected_stamp_ids)
        self.assertNotIn("stamp1", self.panel._selected_stamp_ids)

    # @dod delete-editing-cleared v1.0
    @patch("ui.controls_panel.messagebox.askyesno")
    def test_delete_editing_stamp_clears_edit_state(self, mock_askyesno):
        """删除正在编辑的章后，编辑状态清空"""
        stamp_a = self._create_mock_stamp("stamp1", "章A")
        stamp_b = self._create_mock_stamp("stamp2", "章B")
        self.mock_manager.list_stamps.return_value = [stamp_a, stamp_b]
        self.panel._refresh_stamp_list()
        self.panel.update_idletasks()

        mock_askyesno.return_value = True

        # 设置章A为编辑状态（不调用 _update_edit_controls 避免 MagicMock 格式化问题）
        self.panel._editing_stamp_id = "stamp1"

        # 删除章A
        self.panel._delete_stamp("stamp1")

        # 编辑状态应被清空
        self.assertIsNone(self.panel._editing_stamp_id)
        # 滑块应 disabled
        self.assertEqual(str(self.panel._size_slider.cget("state")), "disabled")

    # @dod delete-last-empty v1.0
    @patch("ui.controls_panel.messagebox.askyesno")
    def test_delete_last_stamp_empty_list(self, mock_askyesno):
        """删除最后一个章后列表为空"""
        stamp = self._create_mock_stamp("stamp1", "章A")
        self.mock_manager.list_stamps.return_value = [stamp]
        self.panel._refresh_stamp_list()
        self.panel.update_idletasks()

        # 设置为选中和编辑状态
        self.panel._selected_stamp_ids = {"stamp1"}
        self.panel._editing_stamp_id = "stamp1"

        mock_askyesno.return_value = True

        # 删除最后一个章
        self.panel._delete_stamp("stamp1")

        # 列表为空
        self.mock_manager.list_stamps.return_value = []
        self.panel._refresh_stamp_list()

        # 选中状态为空
        self.assertEqual(len(self.panel._selected_stamp_ids), 0)
        # 编辑状态清空
        self.assertIsNone(self.panel._editing_stamp_id)


if __name__ == "__main__":
    unittest.main()
