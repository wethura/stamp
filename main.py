import tkinter as tk


def main():
    # 创建根窗口（用于启动画面）
    root = tk.Tk()

    # 显示启动画面
    from ui.splash_screen import SplashFrame
    splash = SplashFrame(root)

    # 加载阶段 1: 导入模块
    splash.update_progress(20, "正在加载文档处理器...")
    from processing import HandlerRegistry

    splash.update_progress(40, "正在初始化界面组件...")
    from processing.stamp_manager import StampManager

    splash.update_progress(60, "正在创建应用...")

    # 加载阶段 2: 创建应用
    from app import App
    app = App.__new__(App)

    splash.update_progress(80, "正在初始化章管理器...")
    app.handler = None
    app.doc_path = None
    app.pages = []
    app.selected_stamps = []
    app.selected_pages = set()
    app.current_preview_page = 0
    app.stamp_manager = StampManager()

    splash.update_progress(100, "加载完成!")
    root.update()
    root.after(200)

    # 关闭启动画面（恢复窗口属性并销毁 Frame）
    splash.close()

    # 创建主窗口组件（使用同一个根窗口）
    from ui.main_window import MainFrame
    main_frame = MainFrame(root, app)
    app.window = main_frame

    # 设置章管理器
    main_frame.controls.set_stamp_manager(app.stamp_manager)

    # 显示主窗口
    root.deiconify()

    # 运行主应用
    root.mainloop()


if __name__ == "__main__":
    main()
