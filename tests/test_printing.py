"""printing 模块单元测试：把文件交给系统打印管线的平台分支（系统调用全部桩掉）。"""
import os
import subprocess
import sys
import unittest
from unittest.mock import MagicMock, patch

from processing import printing


def completed(stdout="", stderr="", returncode=0):
    return subprocess.CompletedProcess([], returncode, stdout=stdout,
                                       stderr=stderr)


class TestPrintMacos(unittest.TestCase):
    """macOS：唤起 Preview → 轮询文档就位 → 打印已打开的文档对象。

    真机教训（2026-09-19）：文档已开时按文件路径再打印会报
    「未能打开文稿以进行打印」，必须打 first document whose path。
    """

    def _osascript_proc(self, **kwargs):
        proc = MagicMock()
        for key, value in kwargs.items():
            setattr(proc, key, value)
        return proc

    def _hanging_dialog_proc(self):
        """面板持续打开的 osascript：首次 communicate 超时（事件已送达），
        kill 后第二次 communicate 正常回收。"""
        proc = self._osascript_proc()
        proc.communicate.side_effect = [
            subprocess.TimeoutExpired("osascript", 5), ("", "")]
        return proc

    def _run_side(self, probe_stdout):
        """按命令区分的 _run 桩：open → 成功；osascript 探测 → 指定 stdout。"""
        def side(cmd, timeout=None):
            if cmd[:2] == ["open", "-a"]:
                return completed(returncode=0)
            if cmd[0] == "osascript":
                return completed(stdout=probe_stdout)
            return completed()
        return side

    def _patch_pipeline(self, proc, probe_stdout="1"):
        """桩掉 open/探测（_run）与打印 osascript（Popen）；返回两个 mock。

        必须用 start()/stop()（本机 3.10.20 实测：__enter__()+stop()
        不会还原被补丁的属性，会跨用例泄漏 MagicMock）。
        """
        run_patcher = patch.object(printing, "_run")
        popen_patcher = patch("processing.printing.subprocess.Popen")
        run_mock = run_patcher.start()
        popen_mock = popen_patcher.start()
        run_mock.side_effect = self._run_side(probe_stdout)
        popen_mock.return_value = proc
        self.addCleanup(run_patcher.stop)
        self.addCleanup(popen_patcher.stop)
        return run_mock, popen_mock

    def _fast_forward_clock(self):
        """让轮询立即超时：monotonic 每次快进 3 秒，sleep 无操作。"""
        import itertools
        fake_time = MagicMock()
        fake_time.monotonic.side_effect = itertools.count(step=3)
        fake_time.sleep = MagicMock()
        clock = patch.object(printing, "time", fake_time)
        clock.start()
        self.addCleanup(clock.stop)

    def test_document_ready_prints_open_document_object(self):
        proc = self._hanging_dialog_proc()
        run_mock, popen = self._patch_pipeline(proc, probe_stdout="1")
        outcome = printing._print_macos("/tmp/合同-已盖章.pdf")
        # 唤起 + 探测都发生了
        open_calls = [c[0][0] for c in run_mock.call_args_list
                      if c[0][0][:2] == ["open", "-a"]]
        self.assertTrue(open_calls, "应先 open 唤起 Preview")
        script = popen.call_args[0][0][2]
        self.assertIn("first document whose path is", script)
        # 期望值须与代码同构地转义（Windows CI 上 realpath 产生反斜杠，
        # 脚本里是双反斜杠，直接比对 realpath 必挂）
        expected = (os.path.realpath("/tmp/合同-已盖章.pdf")
                    .replace("\\", "\\\\").replace('"', '\\"'))
        self.assertIn(expected, script)
        self.assertIn("with print dialog", script)
        self.assertTrue(outcome.ok)
        self.assertEqual(outcome.kind, "dialog")
        proc.kill.assert_called_once()

    def test_document_never_ready_falls_back_to_file_print(self):
        proc = self._hanging_dialog_proc()
        self._fast_forward_clock()
        _, popen = self._patch_pipeline(proc, probe_stdout="0")
        outcome = printing._print_macos("/tmp/a.pdf")
        script = popen.call_args[0][0][2]
        self.assertIn("print POSIX file", script)
        self.assertNotIn("first document", script)
        self.assertEqual(outcome.kind, "dialog")

    def test_path_with_quotes_escaped(self):
        proc = self._hanging_dialog_proc()
        _, popen = self._patch_pipeline(proc, probe_stdout="1")
        printing._print_macos('/tmp/报告"-final-已盖章.pdf')
        script = popen.call_args[0][0][2]
        self.assertIn('\\"-final', script)

    def test_quick_confirm_reports_queued(self):
        proc = self._osascript_proc(returncode=0)
        proc.communicate.return_value = ("", "")
        self._patch_pipeline(proc, probe_stdout="1")
        outcome = printing._print_macos("/tmp/a.pdf")
        self.assertEqual(outcome.kind, "queued")

    def test_user_cancel_is_not_error(self):
        proc = self._osascript_proc(returncode=1)
        proc.communicate.return_value = (
            "", "57:84: execution error: Preview got an error: User canceled. (-128)")
        self._patch_pipeline(proc, probe_stdout="1")
        outcome = printing._print_macos("/tmp/a.pdf")
        self.assertTrue(outcome.ok)
        self.assertEqual(outcome.kind, "cancelled")

    def test_event_failure_falls_back_to_open(self):
        proc = self._osascript_proc(returncode=1)
        proc.communicate.return_value = ("", "osascript: some failure")
        self._patch_pipeline(proc, probe_stdout="1")
        with patch.object(printing, "_open_with_default_app_posix") as fb:
            fb.return_value = printing.PrintOutcome(True, "opened", "已打开")
            outcome = printing._print_macos("/tmp/a.pdf")
            fb.assert_called_once_with("/tmp/a.pdf")
            self.assertEqual(outcome.kind, "opened")

    def test_busy_preview_error_retries_once(self):
        """-10000（Preview 被残留弹窗占住）：间隔重试一次再判失败。"""
        refused = self._osascript_proc(returncode=1)
        refused.communicate.return_value = (
            "", 'execution error: "Preview"遇到一个错误：AppleEvent处理程序失败。(-10000)')
        ok = self._osascript_proc(returncode=0)
        ok.communicate.return_value = ("", "")
        self._patch_pipeline(None, probe_stdout="1")
        with patch("processing.printing.subprocess.Popen",
                   side_effect=[refused, ok]) as popen, \
             patch.object(printing.time, "sleep") as sleep:
            outcome = printing._print_macos("/tmp/a.pdf")
        self.assertEqual(popen.call_count, 2)
        sleep.assert_called()
        self.assertEqual(outcome.kind, "queued")

    @patch.object(printing, "_open_with_default_app_posix")
    def test_office_format_opens_with_default_app(self, open_default):
        open_default.return_value = printing.PrintOutcome(
            True, "opened", "已打开")
        outcome = printing._print_macos("/tmp/报表-已盖章.xlsx")
        open_default.assert_called_once_with("/tmp/报表-已盖章.xlsx")
        self.assertEqual(outcome.kind, "opened")


class TestPrintPosix(unittest.TestCase):
    @patch("processing.printing.subprocess.run")
    def test_pdf_goes_to_lp(self, run):
        run.return_value = completed()
        outcome = printing._print_posix("/tmp/stamp dir/合同-已盖章.pdf")
        cmd = run.call_args[0][0]
        self.assertEqual(cmd, ["lp", "/tmp/stamp dir/合同-已盖章.pdf"])
        self.assertEqual(outcome.kind, "queued")

    @patch("processing.printing.subprocess.run")
    def test_lp_error_reports_detail(self, run):
        run.return_value = completed(stderr="lp: printer not available\n",
                                     returncode=1)
        outcome = printing._print_posix("/tmp/a.pdf")
        self.assertFalse(outcome.ok)
        self.assertIn("printer not available", outcome.message)

    @patch("processing.printing.subprocess.run")
    def test_office_format_opens_with_default_app(self, run):
        run.return_value = completed()
        outcome = printing._print_posix("/tmp/报表-已盖章.xlsx")
        cmd = run.call_args[0][0]
        self.assertIn(cmd[0], ("open", "xdg-open"))
        self.assertEqual(outcome.kind, "opened")


class TestPrintWindows(unittest.TestCase):
    def _win32api(self, shell_result):
        mock = MagicMock()
        mock.ShellExecute.return_value = shell_result
        return mock

    def test_print_verb_delegates_to_system(self):
        api = self._win32api(33)
        with patch.dict(sys.modules, {"win32api": api}):
            outcome = printing._print_windows(r"C:\tmp\a.pdf")
        args = api.ShellExecute.call_args[0]
        self.assertEqual(args[1], "print")
        self.assertEqual(outcome.kind, "queued")

    def test_verb_failure_falls_back_to_open(self):
        api = self._win32api(31)  # SE_ERR_NOASSOC：关联程序未注册 print 动词
        with patch.dict(sys.modules, {"win32api": api}), \
             patch("os.startfile", create=True) as startfile:
            outcome = printing._print_windows(r"C:\tmp\a.pdf")
        startfile.assert_called_once_with(r"C:\tmp\a.pdf")
        self.assertEqual(outcome.kind, "opened")


class TestPrintFileGuard(unittest.TestCase):
    def test_missing_file_never_raises(self):
        outcome = printing.print_file("/nonexistent/x.pdf")
        self.assertFalse(outcome.ok)
        self.assertEqual(outcome.kind, "error")

    @patch.object(printing, "_print_macos", side_effect=OSError("boom"))
    @patch.object(printing, "_print_windows", side_effect=OSError("boom"))
    @patch.object(printing, "_print_posix", side_effect=OSError("boom"))
    def test_inner_failure_becomes_error_outcome(self, _posix, _win, _mac):
        import tempfile
        fd, path = tempfile.mkstemp(suffix=".pdf")
        os.close(fd)
        try:
            outcome = printing.print_file(path)
        finally:
            os.unlink(path)
        self.assertFalse(outcome.ok)
        self.assertEqual(outcome.kind, "error")


if __name__ == "__main__":
    unittest.main()
