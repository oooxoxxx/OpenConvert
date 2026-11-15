"""GUI 啟動流程。"""

from __future__ import annotations

import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from . import APP_NAME, __version__
from .core.settings import Settings
from .gui import icons, theme
from .gui.main_window import MainWindow


def create_application(argv: list[str] | None = None) -> QApplication:
    """建立並設定 QApplication（供測試與 main 共用）。"""
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_DontUseNativeMenuBar, False)
    app = QApplication(argv if argv is not None else sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_NAME)
    app.setApplicationVersion(__version__)
    app.setOrganizationName("OpenConvert")
    app.setDesktopFileName("openconvert")
    app.setStyle("Fusion")
    app.setFont(theme.application_font())
    app.setWindowIcon(icons.app_icon())
    return app


def main(argv: list[str] | None = None) -> int:
    """啟動圖形介面。"""
    if sys.platform == "win32":  # pragma: no cover - 平台相依
        try:
            import ctypes

            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(  # type: ignore[attr-defined]
                "io.github.openconvert.app"
            )
        except (AttributeError, OSError):
            pass

    app = create_application(argv)
    settings = Settings.load()
    window = MainWindow(settings)
    window.show()
    return app.exec()
