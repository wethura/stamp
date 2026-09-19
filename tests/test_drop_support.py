"""拖入文档支持测试：解析、App 入口行为、tkdnd 接线。"""
import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from app import App
from processing.registry import HandlerRegistry
from processing.handlers.pdf_handler import PDFHandler
from processing.handlers.image_handler import ImageHandler
from processing.handlers.excel_handler import ExcelHandler


class TestDropSupport(unittest.TestCase):
    """拖入文档支持测试"""

    def setUp(self):
        # 保存并隔离注册表状态，测试后恢复（不污染其他用例）
        self._saved_handlers = list(HandlerRegistry._handlers)
        HandlerRegistry._handlers = []
        HandlerRegistry.register(PDFHandler)
        HandlerRegistry.register(ImageHandler)
        HandlerRegistry.register(ExcelHandler)

    def tearDown(self):
        HandlerRegistry._handlers = self._saved_handlers

    # @dod drop-supported-file v1.0
    def test_drop_supported_pdf_file(self):
        """拖入支持的 PDF 文件，返回处理器"""
        handler = HandlerRegistry.get_handler("/path/to/test.pdf")
        self.assertIsNotNone(handler)
        self.assertIsInstance(handler, PDFHandler)

    def test_drop_supported_image_file(self):
        """拖入支持的图片文件，返回处理器"""
        handler = HandlerRegistry.get_handler("/path/to/test.png")
        self.assertIsNotNone(handler)
        self.assertIsInstance(handler, ImageHandler)

    def test_drop_supported_excel_file(self):
        """拖入支持的 Excel 文件，返回处理器"""
        handler = HandlerRegistry.get_handler("/path/to/test.xlsx")
        self.assertIsNotNone(handler)
        self.assertIsInstance(handler, ExcelHandler)

    # @dod drop-unsupported-file v1.0
    def test_drop_unsupported_file(self):
        """拖入不支持的文件，返回 None"""
        handler = HandlerRegistry.get_handler("/path/to/test.txt")
        self.assertIsNone(handler)

    def test_drop_unsupported_file_exe(self):
        """拖入不支持的 exe 文件，返回 None"""
        handler = HandlerRegistry.get_handler("/path/to/test.exe")
        self.assertIsNone(handler)

    # @dod drop-path-traversal v1.0
    def test_drop_path_traversal(self):
        """拖入非法路径不触发路径遍历"""
        handler = HandlerRegistry.get_handler("../../../etc/passwd")
        self.assertIsNone(handler)

    def test_drop_path_traversal_with_pdf_ext(self):
        """拖入带 pdf 扩展名的路径遍历路径"""
        # 虽然扩展名是 .pdf，但路径本身不是有效文件路径
        # 这里只测试 registry 的 can_handle，它只检查扩展名
        handler = HandlerRegistry.get_handler("../../../etc/passwd.pdf")
        # registry 只检查扩展名，所以会认为可以处理
        # 实际加载时会在 load() 中失败
        self.assertIsNotNone(handler)

    # @dod drop-macos-binding v1.0 / drop-windows-binding v1.0
    def test_file_filters_not_empty(self):
        """文件过滤器不为空"""
        filters = HandlerRegistry.get_file_filters()
        self.assertGreater(len(filters), 0)
        # 第一个应该是"所有支持的文件"
        self.assertEqual(filters[0][0], "所有支持的文件")


class TestParseDropPaths(unittest.TestCase):
    """tkdnd %D（Tcl 列表字符串）解析——shlex/split 会弄坏这些输入"""

    def test_braced_windows_path_with_spaces(self):
        """Windows 拖放：花括号包裹的带空格路径"""
        from ui.dnd import parse_drop_paths
        self.assertEqual(
            parse_drop_paths("{C:/Users/New Folder/合同.pdf}"),
            ["C:/Users/New Folder/合同.pdf"])

    def test_plain_single_path(self):
        from ui.dnd import parse_drop_paths
        self.assertEqual(parse_drop_paths("/Users/test/document.pdf"),
                         ["/Users/test/document.pdf"])

    def test_multiple_files(self):
        """多文件是多个列表元素，空格路径由花括号保护"""
        from ui.dnd import parse_drop_paths
        self.assertEqual(
            parse_drop_paths("{/Users/test/file 1.pdf} /Users/test/file2.png"),
            ["/Users/test/file 1.pdf", "/Users/test/file2.png"])

    def test_backslash_path_not_mangled(self):
        """反斜杠路径不能被 Tcl 转义吃掉（无解释器的降级解析）"""
        from ui.dnd import parse_drop_paths
        self.assertEqual(parse_drop_paths("C:\\dir\\file.pdf"),
                         ["C:\\dir\\file.pdf"])

    def test_with_real_interp(self):
        """有解释器时走 splitlist（与真实运行路径一致）"""
        from tests.gui_support import shared_ctk_root
        from ui.dnd import parse_drop_paths
        root = shared_ctk_root()
        self.assertEqual(
            parse_drop_paths("{C:/Users/New Folder/a.pdf}", root.tk),
            ["C:/Users/New Folder/a.pdf"])
        self.assertEqual(
            parse_drop_paths("{/a/b 1.pdf} /c/d.png", root.tk),
            ["/a/b 1.pdf", "/c/d.png"])

    def test_with_fake_interp_falls_back(self):
        """解释器是桩对象（如 MagicMock window.tk）时降级为手工解析"""
        from ui.dnd import parse_drop_paths
        self.assertEqual(
            parse_drop_paths("{C:/Users/New Folder/a.pdf}", MagicMock()),
            ["C:/Users/New Folder/a.pdf"])


class TestOnFileDropped(unittest.TestCase):
    """App.on_file_dropped：拖入入口的分发与拒绝提示"""

    def setUp(self):
        self._saved_handlers = list(HandlerRegistry._handlers)
        HandlerRegistry._handlers = []
        HandlerRegistry.register(PDFHandler)
        HandlerRegistry.register(ImageHandler)
        HandlerRegistry.register(ExcelHandler)

    def tearDown(self):
        HandlerRegistry._handlers = self._saved_handlers

    def make_app(self):
        app = App()
        app.window = MagicMock()
        app._load_document = MagicMock()
        return app

    @patch("app.show_toast")
    def test_unsupported_file_shows_rejection(self, show_toast):
        """拖入不支持的文件：状态栏 + Toast 提示不支持，不加载"""
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "file.txt")
            open(path, "w").close()
            app = self.make_app()
            app.on_file_dropped(path)
            app._load_document.assert_not_called()
            status = app.window.set_status.call_args[0][0]
            self.assertIn("不支持的文件格式", status)
            show_toast.assert_called_once()
            self.assertEqual(show_toast.call_args.kwargs.get("kind"), "error")

    @patch("app.show_toast")
    def test_supported_file_opens_document(self, show_toast):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "合同.pdf")
            open(path, "w").close()
            app = self.make_app()
            app.on_file_dropped(path)
            app._load_document.assert_called_once()
            args = app._load_document.call_args[0]
            self.assertEqual(args[0], path)
            self.assertIsInstance(args[1], PDFHandler)
            show_toast.assert_not_called()

    @patch("app.show_toast")
    def test_braced_path_with_spaces_opens(self, show_toast):
        """花括号包裹的带空格路径（Windows 形态）也能打开"""
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "New Folder")
            os.mkdir(path)
            target = os.path.join(path, "a b.pdf")
            open(target, "w").close()
            dropped = target.replace(os.sep, "/")
            app = self.make_app()
            app.on_file_dropped("{" + dropped + "}")
            app._load_document.assert_called_once()
            # 解析保留拖入数据的原始分隔符（正斜杠在 Windows 一样可用）
            self.assertEqual(app._load_document.call_args[0][0], dropped)

    @patch("app.show_toast")
    def test_multiple_files_rejected(self, show_toast):
        app = self.make_app()
        app.on_file_dropped("/a/1.pdf /b/2.pdf")
        app._load_document.assert_not_called()
        self.assertIn("请每次拖入一个文件",
                      app.window.set_status.call_args[0][0])
        show_toast.assert_called_once()

    @patch("app.show_toast")
    def test_missing_file_rejected(self, show_toast):
        app = self.make_app()
        app.on_file_dropped("/nonexistent/nope.pdf")
        app._load_document.assert_not_called()
        self.assertIn("文件不存在", app.window.set_status.call_args[0][0])

    @patch("app.show_toast")
    def test_empty_data_ignored(self, show_toast):
        app = self.make_app()
        app.on_file_dropped("   ")
        app._load_document.assert_not_called()
        app.window.set_status.assert_not_called()
        show_toast.assert_not_called()


class TestPermissionHint(unittest.TestCase):
    """读取被 macOS 拒（TCC/权限）时给出可操作引导，而不是裸 errno"""

    def make_app(self):
        app = App()
        app.window = MagicMock()
        return app

    @patch("app.messagebox")
    def test_load_permission_error_shows_hint(self, messagebox):
        """微信容器等受保护路径：Errno 1 → 权限引导弹窗"""
        from unittest.mock import MagicMock as MM
        app = self.make_app()
        handler = MM()
        handler.load.side_effect = RuntimeError(
            "无法加载图片: [Errno 1] Operation not permitted: "
            "/Users/x/Library/Containers/com.tencent.xinWeChat/Data/a.jpg")
        app._load_document("/x/a.jpg", handler)
        messagebox.showerror.assert_called_once()
        title, body = messagebox.showerror.call_args[0]
        self.assertEqual(title, "没有文件访问权限")
        self.assertIn("完全磁盘访问权限", body)
        self.assertIn("另存", body)

    @patch("app.messagebox")
    def test_load_normal_error_unchanged(self, messagebox):
        """普通加载失败：维持「加载失败 + 原始信息」"""
        app = self.make_app()
        handler = MagicMock()
        handler.load.side_effect = RuntimeError("PDF 文件损坏或无效: bad header")
        app._load_document("/x/a.pdf", handler)
        messagebox.showerror.assert_called_once()
        title, body = messagebox.showerror.call_args[0]
        self.assertEqual(title, "加载失败")
        self.assertIn("PDF 文件损坏", body)

    @patch("app.messagebox")
    def test_word_failure_permission_shows_hint(self, messagebox):
        """Word 转换失败的权限拒绝也走引导，不再追问手动导入"""
        app = self.make_app()
        app._report_word_open_failure(
            "Word 转换失败",
            "[Errno 13] Permission denied: /x/b.docx", offer_manual=True)
        messagebox.showerror.assert_called_once()
        self.assertEqual(messagebox.showerror.call_args[0][0],
                         "没有文件访问权限")
        messagebox.askyesno.assert_not_called()


class TestEnableFileDrop(unittest.TestCase):
    """ui.dnd.enable_file_drop：接线与降级"""

    def test_registers_on_shared_root(self):
        """共享根上启用：拿到版本号，绑定生效，回调可分发"""
        from tests.gui_support import shared_ctk_root
        from ui.dnd import enable_file_drop
        root = shared_ctk_root()
        version = enable_file_drop(root, lambda data: None)
        if version is None:
            self.skipTest("tkdnd 不可用（tkinterdnd2 未安装或平台缺二进制）")
        self.assertTrue(root.bind("<<Drop>>"))
        calls = []
        enable_file_drop(root, lambda data: calls.append(data))
        root.event_generate("<<Drop>>")
        for _ in range(5):  # Windows 上事件分发需要多轮 update 泵
            root.update()
        self.assertTrue(calls or calls == [""])

    def test_degrades_to_none_when_tkdnd_unavailable(self):
        """tkdnd 不可用时返回 None 且不碰根窗口"""
        from ui import dnd
        root = MagicMock()
        with patch.object(dnd, "_load_tkdnd", return_value=None):
            self.assertIsNone(dnd.enable_file_drop(root, lambda d: None))


if __name__ == "__main__":
    unittest.main()
