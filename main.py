"""Application entry point — CustomTkinter."""

import os
import sys

import customtkinter as ctk


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


def _run_selftest(root, timeout_s: float = 20.0):
    """打包自检：确认主窗口真的完成映射（比「进程存活」强的发布门禁）。

    STAMPTOOL_SELFTEST=1 检查窗口；=full 额外跑一遍核心链路。
    由 CI 与发布验证使用，以退出码反馈结果。
    """
    import time

    mode = os.environ.get("STAMPTOOL_SELFTEST", "")
    deadline = time.monotonic() + timeout_s

    def poll():
        try:
            if root.winfo_ismapped():
                print(f"SELFTEST OK: main window mapped "
                      f"({root.winfo_width()}x{root.winfo_height()})", flush=True)
                if mode == "full":
                    _selftest_core_pipeline()
                    print("SELFTEST OK: core pipeline "
                          "(render + stamp + export)", flush=True)
                root.destroy()
                sys.exit(0)
            if time.monotonic() > deadline:
                print("SELFTEST FAIL: main window never mapped", flush=True)
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

