"""Application entry point — CustomTkinter."""

import customtkinter as ctk


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
    from app import App
    app_controller = App.__new__(App)
    app_controller.handler = None
    app_controller.doc_path = None
    app_controller.pages = []
    app_controller.instance_manager = None
    app_controller.current_preview_page = 0
    app_controller._selected_instance_id = None
    app_controller.stamp_manager = StampManager()

    splash.update_progress(80, "正在初始化章管理器...")
    splash.update_progress(100, "加载完成!")

    # ── Close splash, show main window ────────────────────────────
    splash.close()

    from ui.main_window import MainWindow
    window = MainWindow(root, app_controller)
    app_controller.window = window
    window.controls.set_stamp_manager(app_controller.stamp_manager)

    root.deiconify()
    root.mainloop()


if __name__ == "__main__":
    main()
