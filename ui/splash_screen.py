"""Splash screen — CTkToplevel with 墨韵 theme."""

import customtkinter as ctk

from ui.theme import Colors, Fonts, Spacing


class SplashScreen(ctk.CTkToplevel):
    """Startup splash screen with title, subtitle, and progress bar."""

    def __init__(self, parent):
        super().__init__(parent)
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.resizable(False, False)

        self.title("盖章工具")
        self.geometry("440x240")
        self._center_on_screen()

        self._build_ui()
        self.update()

    def _center_on_screen(self):
        self.update_idletasks()
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        x = (sw - 440) // 2
        y = (sh - 240) // 2
        self.geometry(f"440x240+{x}+{y}")

    def _build_ui(self):
        container = ctk.CTkFrame(self, fg_color=Colors.SURFACE_BASE, corner_radius=12)
        container.pack(fill="both", expand=True, padx=2, pady=2)

        # Brand accent at top
        accent = ctk.CTkFrame(container, height=2, fg_color=Colors.PRIMARY)
        accent.place(x=40, rely=0.0, relwidth=0.8)

        # Title
        title = ctk.CTkLabel(
            container,
            text="盖章工具",
            font=(Fonts.FAMILY, Fonts.SPLASH_TITLE_SIZE, "bold"),
            text_color=Colors.TEXT_PRIMARY,
        )
        title.pack(pady=(44, Spacing.PAD_SM))

        # Subtitle
        subtitle = ctk.CTkLabel(
            container,
            text="S t a m p   T o o l",
            font=("Helvetica", Fonts.SPLASH_SUBTITLE_SIZE),
            text_color=Colors.GOLD,
        )
        subtitle.pack(pady=(0, 28))

        # Loading message
        self._loading_label = ctk.CTkLabel(
            container,
            text="正在初始化...",
            font=(Fonts.FAMILY, Fonts.SPLASH_LOADING_SIZE),
            text_color=Colors.TEXT_SECONDARY,
        )
        self._loading_label.pack(pady=(0, Spacing.PAD_MD))

        # Progress bar
        self._progress = ctk.CTkProgressBar(
            container,
            width=320,
            height=4,
            fg_color=Colors.SURFACE_OVERLAY,
            progress_color=Colors.PRIMARY,
            corner_radius=2,
        )
        self._progress.pack(padx=60)
        self._progress.set(0)

    def update_progress(self, percent: int, message: str = None):
        """Update progress bar and optional loading message."""
        if message:
            self._loading_label.configure(text=message)
        self._progress.set(percent / 100.0)
        self.update()

    def close(self):
        """Close the splash screen."""
        self.destroy()
