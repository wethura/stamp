"""Application entry point — CustomTkinter."""

import logging
import os
import sys
import threading
import traceback
from pathlib import Path

import customtkinter as ctk

LOG_FILE_NAME = "stamp_tool.log"


class _LogWriter:
    """把 write 导向日志（供 windowed exe 中 stdout/stderr 为 None 时顶替）。"""

    def __init__(self, level):
        self._level = level
        self._buf = ""

    def write(self, text):
        self._buf += text
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            if line.strip():
                logging.log(self._level, line)

    def flush(self):
        if self._buf.strip():
            logging.log(self._level, self._buf)
            self._buf = ""


def _setup_logging() -> Path:
    """打包版没有控制台：所有日志与未捕获异常落盘，便于用户反馈问题。"""
    log_dir = Path.home() / ".stamp_tool" / "logs"
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        log_dir = Path(os.environ.get("TEMP", "/tmp"))
    log_path = log_dir / LOG_FILE_NAME
    try:
        logging.basicConfig(
            filename=str(log_path), filemode="a", level=logging.INFO,
            format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        )
    except OSError:
        logging.basicConfig(level=logging.INFO)
    # windowed exe 的 stdout/stderr 是 None：三方库 print 会产生
    # 不可预知行为；重定向到日志，顺便多一份线索
    if sys.stdout is None:
        sys.stdout = _LogWriter(logging.INFO)
    if sys.stderr is None:
        sys.stderr = _LogWriter(logging.ERROR)
    return log_path


def _install_excepthook(log_path: Path):
    """未捕获异常落盘并在下一次启动可见——闪退不再「不知道为什么」。"""
    unattended = bool(os.environ.get("STAMPTOOL_SELFTEST"))

    def hook(exc_type, exc, tb):
        logging.critical("未捕获异常", exc_info=(exc_type, exc, tb))
        if unattended:
            # 自检/无人值守环境绝不能弹窗等待点击（会永久挂起进程）
            return
        try:
            from tkinter import messagebox
            messagebox.showerror(
                "程序遇到问题",
                f"{exc_type.__name__}: {exc}\n\n详细信息已记录到：\n{log_path}",
            )
        except Exception:  # noqa: BLE001  兜底展示失败也要留下日志
            pass

    sys.excepthook = hook
    threading.excepthook = lambda args: hook(
        args.exc_type, args.exc_value, args.exc_traceback)


def _selftest_core_pipeline() -> None:
    """打包环境下的核心链路自检：造 PDF → Handler 加载/渲染 → 盖章导出。

    只验证窗口还不够——资源缺失（字体、C 扩展）常常在真正操作时才暴露。
    失败抛异常，由调用方转为退出码。
    """
    import tempfile
    from pathlib import Path

    import fitz
    from PIL import Image

    from processing import HandlerRegistry

    tmp = Path(tempfile.mkdtemp(prefix="stamp-selftest-"))
    source = tmp / "in.pdf"
    with fitz.open() as doc:
        for _ in range(2):
            page = doc.new_page(width=595, height=842)
            page.insert_text((50, 80), "selftest")
        doc.save(str(source))

    handler = HandlerRegistry.get_handler(str(source))
    if handler is None:
        raise RuntimeError("PDF handler not registered")
    handler.load(str(source))
    try:
        if handler.page_count() != 2:
            raise RuntimeError(f"page_count={handler.page_count()}, expected 2")
        rendered = handler.render_page(0)
        if rendered.size[0] <= 0 or rendered.size[1] <= 0:
            raise RuntimeError("render_page produced empty image")
        stamp = Image.new("RGBA", (120, 120), (180, 0, 0, 200))
        out = tmp / "out.pdf"
        handler.export_with_stamp(str(out), stamp, (0.3, 0.3), 0.2, {0})
        if not out.exists():
            raise RuntimeError("export produced no file")
        with fitz.open(str(out)) as doc:
            if doc.page_count != 2:
                raise RuntimeError("exported page count mismatch")
    finally:
        handler.close()

    # App 层：双击添加印章的取值路径（曾因字段漂移在此崩溃）
    from processing.stamp_instance import StampInstanceManager
    controller = create_app_controller()
    if not hasattr(controller, "active_page"):
        raise RuntimeError("controller lacks active_page — 添加印章会崩溃")
    instance = StampInstanceManager().add_instance("selftest", controller.active_page)
    if instance.page_index != controller.active_page:
        raise RuntimeError("instance not bound to active page")


def _selftest_docx_pipeline() -> None:
    """打包环境下走一遍用户的真实路径：打开 docx → 转换 → 盖章 → 导出。

    用桩引擎替代外部办公软件（CI 无 Office），覆盖的是应用自身链路：
    DOCX 前置校验 → 引擎调度 → PDFHandler 渲染/盖章/导出。
    用户报告的「打开 Word 文档闪退」正是这条路径。
    """
    import tempfile
    import zipfile
    from pathlib import Path

    import fitz
    from PIL import Image

    from processing.handlers.word_handler import WordHandler
    from processing.word_support.engines import EngineInfo
    from processing.word_support.service import ConversionService

    class _StubEngine:
        engine_id = "selftest-stub"
        NAME = "Selftest Stub"

        def probe(self):
            return EngineInfo(self.engine_id, self.NAME, True, version="stub")

        def convert(self, work_copy, out_pdf, timeout_s=120.0, cancel_event=None):
            with fitz.open() as doc:
                for _ in range(2):
                    page = doc.new_page(width=595, height=842)
                    page.insert_text((50, 80), "docx pipeline selftest")
                doc.save(str(out_pdf))
            return {"ok": True, "pdf_path": str(out_pdf)}

    tmp = Path(tempfile.mkdtemp(prefix="stamp-docx-selftest-"))
    source = tmp / "sample.docx"
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("word/document.xml", "<document/>")

    service = ConversionService(engines=[_StubEngine()],
                                preference_path=str(tmp / "pref.json"))
    handler = WordHandler(service=service)
    try:
        handler.load(str(source))
        if handler.page_count() != 2:
            raise RuntimeError(f"docx pipeline page_count={handler.page_count()}")
        rendered = handler.render_page(0)
        if rendered.size[0] <= 0:
            raise RuntimeError("docx pipeline render failed")
        stamp = Image.new("RGBA", (100, 100), (180, 0, 0, 200))
        out = tmp / "out.pdf"
        handler.export_with_stamp(str(out), stamp, (0.3, 0.3), 0.2, {0})
        if not out.exists():
            raise RuntimeError("docx pipeline export produced no file")
    finally:
        handler.close()


def _selftest_engine_probe() -> None:
    """打包环境下引擎探测必须可用。

    Windows 上 COM 检测依赖 winreg；实测它可能未被 PyInstaller 收录，
    届时探测会降级成「无法读取注册表」——不再闪退（已防御），但功能受损。
    这里在打包产物上直接断言，让这类打包缺失在 CI 就被抓出来。
    """
    from processing.word_support.service import get_shared_service

    infos = get_shared_service().probe_all(refresh=True)
    if not infos:
        raise RuntimeError("engine probe returned no results")
    if sys.platform == "win32":
        broken = [i for i in infos.values()
                  if "注册表" in i.detail or "winreg" in i.detail.lower()]
        if broken:
            detail = "; ".join(f"{i.engine_id}: {i.detail}" for i in broken)
            raise RuntimeError(f"winreg 未被打包，Office/WPS 检测失效 → {detail}")
    print(f"SELFTEST OK: engine probe ({len(infos)} engines)", flush=True)


def _selftest_headless() -> None:
    """无头自检：不创建任何 Tk 窗口，纯链路验证（CI 专用）。

    Windows runner 上 GUI 窗口的创建/轮询行为不可控（曾让自检步骤
    10 分钟无输出超时），而发布真正要守护的是「核心链路 + 引擎探测」
    ——这些完全不依赖 GUI。窗口可见性由真实启动门禁单独验证。
    """
    _selftest_core_pipeline()
    print("SELFTEST OK: core pipeline (render + stamp + export)", flush=True)
    _selftest_docx_pipeline()
    print("SELFTEST OK: docx pipeline "
          "(precheck + convert + stamp + export)", flush=True)
    _selftest_engine_probe()


def _finish(code: int):
    """自检收尾：冲刷日志缓冲后直接终止进程（绕过 mainloop/钩子语义）。"""
    try:
        logging.shutdown()
    except Exception:  # noqa: BLE001
        pass
    os._exit(code)


def _selftest_windowed(root, timeout_s: float = 25.0):
    """窗口自检（本机人工验证用）：等待主窗口完成布局后收尾退出。"""
    import time

    deadline = time.monotonic() + timeout_s

    def poll():
        try:
            mapped = bool(root.winfo_ismapped())
            width, height = root.winfo_width(), root.winfo_height()
            req_w, req_h = root.winfo_reqwidth(), root.winfo_reqheight()
            laid_out = (width > 1 and height > 1) or (req_w > 1 and req_h > 1)
            if mapped or laid_out:
                if mapped:
                    print(f"SELFTEST OK: main window mapped ({width}x{height})", flush=True)
                else:
                    print(f"SELFTEST OK: window laid out "
                          f"(actual {width}x{height}, requested {req_w}x{req_h}); "
                          f"not mapped (no display session)", flush=True)
                _finish(0)
            if time.monotonic() > deadline:
                print(f"SELFTEST FAIL: window never laid out — "
                      f"actual {width}x{height}, requested {req_w}x{req_h}, "
                      f"mapped={mapped}; packaging may be incomplete", flush=True)
                _finish(1)
        except Exception as exc:  # noqa: BLE001
            print(f"SELFTEST FAIL: {exc}", flush=True)
            _finish(1)
        root.after(400, poll)

    root.after(400, poll)


def create_app_controller():
    """构造 App 控制器（启动与测试共用同一入口）。

    以前这里是 App.__new__ + 手工赋值，字段名与 App.__init__ 漂移后
    双击添加印章会 AttributeError；统一走构造器消除这类风险。
    """
    from app import App
    return App()


def _install_tk_callback_logging(root):
    """Tkinter 回调异常在 windowed exe 里默认打到 None stderr——被静默吞掉。

    重定向到日志，补上这个观察黑洞（sys.excepthook 只覆盖主流程，
    覆盖不到 Tk 事件/after 回调）。
    """
    shown_errors = set()

    def report(exc_type, exc, tb, *_args):
        logging.critical("Tk 回调异常", exc_info=(exc_type, exc, tb))
        # 同一异常只弹一次窗：滚轮等高频回调每格都触发，重复模态框会
        # 连环轰炸用户到应用不可操作（Windows 无上限装到 customtkinter
        # 6.0.0 时实况）。后续同款异常仍落日志，不再打扰。
        key = (exc_type, str(exc))
        if key in shown_errors:
            return
        shown_errors.add(key)
        try:
            from tkinter import messagebox
            messagebox.showerror(
                "程序遇到问题",
                f"{exc_type.__name__}: {exc}\n\n详细信息已记录到日志。")
            import logging as _l
            _l.getLogger(__name__).info(
                "日志位置见启动记录或 ~/.stamp_tool/logs/stamp_tool.log")
        except Exception:  # noqa: BLE001
            pass

    try:
        root.report_callback_exception = report
    except Exception:  # noqa: BLE001
        pass


def _guard_window_visibility(root, attempts: int = 4):
    """主窗口可见性看门狗：若窗口不可见，多机制强制拉起并记日志。

    Windows 打包版曾出现主循环在跑、进程活着、窗口不可见。deiconify
    单独无效时，依次叠加 wm_state(normal)/lift/focus_force。多数隐形
    场景可被直接救回；救不回也有日志证据。
    """
    import time

    def check(attempt):
        try:
            viewable = bool(root.winfo_viewable())
            logging.info("窗口可见性检查 %d/%d: viewable=%s geometry=%s state=%s",
                         attempt, attempts, viewable, root.geometry(),
                         root.state())
            if viewable:
                return
            if attempt > attempts:
                logging.error("主窗口在 %d 次强制拉起后仍不可见", attempts)
                return
            logging.warning("主窗口不可见，尝试强制拉起（第 %d 次）", attempt)
            # 多机制：不同 Tk/WM 组合下生效的接口不同
            try:
                root.wm_state("normal")
            except Exception:  # noqa: BLE001
                pass
            root.deiconify()
            root.lift()
            try:
                root.focus_force()
            except Exception:  # noqa: BLE001
                pass
            root.attributes("-topmost", True)
            root.after(250, lambda: root.attributes("-topmost", False))
        except Exception:  # noqa: BLE001
            logging.exception("可见性检查失败")
            return
        root.after(600, lambda: check(attempt + 1))

    root.after(500, lambda: check(1))


def _show_main_window(root, window, app_controller):
    """显示主窗并加载印章库：先显示再加载数据，加载再慢也不「黑屏」。

    旧顺序在 splash 关闭后先同步加载印章库再 deiconify——库大/损坏时
    应用处于「零可见窗口」状态，正是「加载完成后消失」的形态。
    """
    root.deiconify()
    root.lift()
    _guard_window_visibility(root)

    try:
        app_controller.window = window
        window.set_status("正在加载印章库…")
        root.update_idletasks()
        window.controls.set_stamp_manager(app_controller.stamp_manager)
    except Exception:  # noqa: BLE001  印章库损坏不得阻断主界面
        logging.exception("印章库加载失败（已跳过）")
    finally:
        window.set_status("就绪 · 打开文档后，双击右侧印章即可添加")


def main():
    log_path = _setup_logging()
    _install_excepthook(log_path)
    logging.info("启动 StampTool（python=%s, frozen=%s, platform=%s）",
                 sys.version.split()[0], getattr(sys, "frozen", False), sys.platform)

    selftest_mode = os.environ.get("STAMPTOOL_SELFTEST", "")

    if selftest_mode == "headless":
        # CI：完全不创建 Tk（Windows runner 上窗口行为不可控曾挂死自检）
        try:
            _selftest_headless()
        except BaseException:  # noqa: BLE001
            # 无人值守时 excepthook 只把异常落盘不打屏——曾在 Windows CI 上
            # 表现为「退出码 1 且零输出」。自检必须把真实堆栈打到 stderr。
            if sys.stderr is not None:
                traceback.print_exc(file=sys.stderr)
                sys.stderr.flush()
            else:
                logging.exception("自检失败")
            _finish(1)
        _finish(0)

    from ui.theme import init_theme
    init_theme()

    # 不 withdraw 根窗口：Windows 打包版上「withdraw 后 deiconify」不可靠
    # （实测 viewable 始终 False、系统窗口句柄为 0，进程活着但无界面）。
    # 主窗直接显示，splash 作为置顶浮层盖在其上；init 完成后销毁浮层。
    root = ctk.CTk()
    _install_tk_callback_logging(root)

    # ── Splash screen ─────────────────────────────────────────────
    from ui.splash_screen import SplashScreen
    splash = SplashScreen(root)

    splash.update_progress(20, "正在加载文档处理器...")
    from processing import HandlerRegistry

    splash.update_progress(40, "正在初始化界面组件...")
    from processing.stamp_manager import StampManager

    splash.update_progress(60, "正在创建应用...")

    # ── Create App controller ─────────────────────────────────────
    app_controller = create_app_controller()

    splash.update_progress(80, "正在初始化章管理器...")
    splash.update_progress(100, "加载完成!")

    # ── Close splash, build + show main window ────────────────────
    splash.close()

    from ui.main_window import MainWindow
    window = MainWindow(root, app_controller)
    logging.info("主窗口构建完成")

    # OS 文件拖入：整个主窗口注册为拖放目标（tkdnd 不可用时降级为无拖拽）
    from ui.dnd import enable_file_drop
    dnd_version = enable_file_drop(root, app_controller.on_file_dropped)
    if selftest_mode == "full" and not dnd_version:
        # 打包版必须有拖拽：tkinterdnd2 漏打包时在这里拦下发布
        print("SELFTEST FAIL: 文件拖入不可用（tkinterdnd2/tkdnd 未正确打包）",
              flush=True)
        _finish(1)

    _show_main_window(root, window, app_controller)
    logging.info("主窗口已显示，进入主循环")

    if selftest_mode:
        _selftest_windowed(root)

    root.mainloop()


if __name__ == "__main__":
    main()

