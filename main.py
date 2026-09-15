"""Application entry point — CustomTkinter."""

import logging
import os
import sys
import threading
from pathlib import Path

import customtkinter as ctk

LOG_FILE_NAME = "stamp_tool.log"


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
    return log_path


def _install_excepthook(log_path: Path):
    """未捕获异常落盘并在下一次启动可见——闪退不再「不知道为什么」。"""
    def hook(exc_type, exc, tb):
        logging.critical("未捕获异常", exc_info=(exc_type, exc, tb))
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


def _run_selftest(root, timeout_s: float = 25.0):
    """打包自检：窗口可用 + （full 模式）核心链路可跑。

    - `STAMPTOOL_SELFTEST=1`：窗口布局就绪即通过
    - `STAMPTOOL_SELFTEST=full`：额外跑一遍渲染 → 盖章 → 导出

    窗口"已映射"依赖真实显示会话（CI runner 通常没有），因此硬标准是
    布局就绪（宽高有效）——打包缺资源会在这里暴露；映射状态仅作标注。
    """
    import time

    mode = os.environ.get("STAMPTOOL_SELFTEST", "")
    deadline = time.monotonic() + timeout_s

    def poll():
        try:
            mapped = bool(root.winfo_ismapped())
            width, height = root.winfo_width(), root.winfo_height()
            req_w, req_h = root.winfo_reqwidth(), root.winfo_reqheight()
            # 有效布局：已映射，或有实际/请求尺寸（无显示会话时靠后者）
            laid_out = (width > 1 and height > 1) or (req_w > 1 and req_h > 1)
            if mapped or laid_out:
                if mapped:
                    print(f"SELFTEST OK: main window mapped ({width}x{height})", flush=True)
                else:
                    print(f"SELFTEST OK: window laid out "
                          f"(actual {width}x{height}, requested {req_w}x{req_h}); "
                          f"not mapped (no display session)", flush=True)
                if mode == "full":
                    _selftest_core_pipeline()
                    print("SELFTEST OK: core pipeline "
                          "(render + stamp + export)", flush=True)
                    _selftest_engine_probe()
                root.destroy()
                sys.exit(0)
            if time.monotonic() > deadline:
                print(f"SELFTEST FAIL: window never laid out — "
                      f"actual {width}x{height}, requested {req_w}x{req_h}, "
                      f"mapped={mapped}; packaging may be incomplete", flush=True)
                root.destroy()
                sys.exit(1)
        except Exception as exc:  # noqa: BLE001
            print(f"SELFTEST FAIL: {exc}", flush=True)
            sys.exit(1)
        root.after(400, poll)

    root.after(400, poll)


def create_app_controller():
    """构造 App 控制器（启动与测试共用同一入口）。

    以前这里是 App.__new__ + 手工赋值，字段名与 App.__init__ 漂移后
    双击添加印章会 AttributeError；统一走构造器消除这类风险。
    """
    from app import App
    return App()


def main():
    log_path = _setup_logging()
    _install_excepthook(log_path)
    logging.info("启动 StampTool（python=%s, frozen=%s, platform=%s）",
                 sys.version.split()[0], getattr(sys, "frozen", False), sys.platform)

    from ui.theme import init_theme
    init_theme()

    root = ctk.CTk()
    root.withdraw()

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

    # ── Close splash, show main window ────────────────────────────
    splash.close()

    from ui.main_window import MainWindow
    window = MainWindow(root, app_controller)
    app_controller.window = window
    window.controls.set_stamp_manager(app_controller.stamp_manager)

    root.deiconify()

    if os.environ.get("STAMPTOOL_SELFTEST"):
        _run_selftest(root)

    root.mainloop()


if __name__ == "__main__":
    main()

