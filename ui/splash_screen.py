import tkinter as tk


class SplashFrame(tk.Frame):
    """启动画面 Frame - 显示在根窗口上"""

    def __init__(self, parent):
        super().__init__(parent)

        # 设置窗口属性
        parent.title("盖章工具")
        parent.geometry("420x220")
        parent.resizable(False, False)
        parent.overrideredirect(True)  # 无边框
        parent.attributes('-topmost', True)

        # 居中显示
        parent.update_idletasks()
        width = parent.winfo_width()
        height = parent.winfo_height()
        x = (parent.winfo_screenwidth() // 2) - (width // 2)
        y = (parent.winfo_screenheight() // 2) - (height // 2)
        parent.geometry(f'{width}x{height}+{x}+{y}')

        self._build_ui()
        self.pack(fill=tk.BOTH, expand=True)
        parent.update()

    def _build_ui(self):
        # 背景
        self.configure(bg='#3b82f6')

        # 标题
        title_label = tk.Label(
            self,
            text="盖章工具",
            font=('PingFang SC', 32, 'bold'),
            fg='white',
            bg='#3b82f6'
        )
        title_label.pack(pady=(40, 10))

        # 副标题
        subtitle_label = tk.Label(
            self,
            text="Stamp Tool",
            font=('Helvetica', 12),
            fg='#93c5fd',
            bg='#3b82f6'
        )
        subtitle_label.pack(pady=(0, 25))

        # 加载文字
        self.loading_label = tk.Label(
            self,
            text="正在初始化...",
            font=('PingFang SC', 11),
            fg='#dbeafe',
            bg='#3b82f6'
        )
        self.loading_label.pack(pady=(0, 12))

        # 进度条容器
        progress_frame = tk.Frame(self, bg='#3b82f6')
        progress_frame.pack(fill=tk.X, padx=50)

        # 进度条（使用 Canvas）
        self.progress_canvas = tk.Canvas(
            progress_frame,
            height=4,
            bg='#2563eb',
            highlightthickness=0
        )
        self.progress_canvas.pack(fill=tk.X)
        self.progress_canvas.create_rectangle(
            0, 0, 0, 4,
            fill='white',
            outline='',
            tags='progress'
        )

    def update_progress(self, percent: int, message: str = None):
        """更新进度"""
        if message:
            self.loading_label.config(text=message)

        self.update_idletasks()
        canvas_width = self.progress_canvas.winfo_width()
        if canvas_width > 1:
            progress_width = int(canvas_width * percent / 100)
            self.progress_canvas.coords('progress', 0, 0, progress_width, 4)
        self.update()

    def close(self):
        """关闭启动画面"""
        # 恢复父窗口属性
        parent = self.master
        parent.overrideredirect(False)
        parent.attributes('-topmost', False)
        parent.resizable(True, True)
        self.destroy()
