"""主視窗：側邊欄 + 頁面堆疊 + 狀態列。"""

from __future__ import annotations

from PySide6.QtCore import QByteArray
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QStackedWidget,
    QWidget,
)

from .. import __version__
from ..core.ffmpeg import FFmpegTools, discover, version_of
from ..core.settings import Settings
from ..runner import ConversionQueue
from . import icons, theme
from .pages.about import AboutPage
from .pages.convert import ConvertPage
from .pages.history import HistoryPage
from .pages.inspect import InspectPage
from .pages.settings import SettingsPage
from .widgets.sidebar import Sidebar
from .widgets.toast import Toast


class MainWindow(QMainWindow):
    def __init__(self, settings: Settings, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._settings = settings
        self._tools: FFmpegTools = discover(settings.ffmpeg_path, settings.ffprobe_path)
        self._queue = ConversionQueue(settings, self)

        self.setWindowTitle(f"OpenConvert {__version__}")
        self.setWindowIcon(icons.app_icon())
        self.setMinimumSize(980, 640)
        self.resize(1180, 760)

        self._build_ui()
        self._connect_signals()
        self._apply_theme()
        self._update_status()
        self._restore_geometry()

    # ------------------------------------------------------------------ 版面

    def _build_ui(self) -> None:
        central = QWidget()
        central.setObjectName("Root")
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._sidebar = Sidebar()
        self._stack = QStackedWidget()

        self._convert_page = ConvertPage(self._settings, self._tools, self._queue, self.notify)
        self._inspect_page = InspectPage(self._tools, self.notify)
        self._history_page = HistoryPage(self.notify)
        self._settings_page = SettingsPage(self._settings, self._tools, self.notify)
        self._about_page = AboutPage()

        for page in (
            self._convert_page,
            self._inspect_page,
            self._history_page,
            self._settings_page,
            self._about_page,
        ):
            self._stack.addWidget(page)

        layout.addWidget(self._sidebar)
        layout.addWidget(self._stack, 1)
        self.setCentralWidget(central)

        self._status_label = QLabel()
        self._status_label.setObjectName("Muted")
        self.statusBar().addPermanentWidget(self._status_label)
        self.statusBar().setSizeGripEnabled(True)

    def _connect_signals(self) -> None:
        self._sidebar.navigate.connect(self._navigate)
        self._sidebar.themeToggleRequested.connect(self._toggle_theme)
        self._convert_page.historyChanged.connect(self._history_page.refresh)
        self._settings_page.settingsChanged.connect(self._on_settings_changed)
        self._settings_page.toolsChanged.connect(self._on_tools_changed)

    # ------------------------------------------------------------------ 導覽

    def _navigate(self, index: int) -> None:
        if not 0 <= index < self._stack.count():
            return
        self._stack.setCurrentIndex(index)
        self._sidebar.set_active(index)
        if index == 2:
            self._history_page.refresh()
        self._settings.last_page = index
        self._settings.save()

    def _toggle_theme(self) -> None:
        current = theme.resolve(self._settings.theme)
        self._settings.theme = "light" if current == "dark" else "dark"
        self._settings.save()
        self._apply_theme()
        self._settings_page.refresh_from_settings(self._settings)

    def _apply_theme(self) -> None:
        app = QApplication.instance()
        if app is None:
            return
        icons.clear_cache()
        tokens = theme.apply_theme(app, self._settings.theme)
        self._sidebar.apply_colors(tokens, theme.resolve(self._settings.theme) == "dark")
        self.setWindowIcon(icons.app_icon())

    # ------------------------------------------------------------------ 設定

    def _on_settings_changed(self, settings: Settings) -> None:
        self._settings = settings
        self._queue.apply_settings(settings)
        self._convert_page.apply_settings(settings)
        self._apply_theme()

    def _on_tools_changed(self, tools: FFmpegTools) -> None:
        self._tools = tools
        self._convert_page.set_tools(tools)
        self._inspect_page.set_tools(tools)
        self._update_status()

    # ------------------------------------------------------------------ 狀態列

    def _update_status(self) -> None:
        if self._tools.available:
            version = version_of(self._tools.ffmpeg) or ""
            short = version.split(" Copyright")[0].replace("ffmpeg version ", "")
            text = f"FFmpeg 已就緒（{short}）" if short else "FFmpeg 已就緒"
        else:
            text = "找不到 FFmpeg — 影片與音訊功能不可用"
        self._status_label.setText(text)
        self._status_label.setToolTip(
            str(self._tools.ffmpeg) if self._tools.ffmpeg else "請到「設定」指定 FFmpeg 路徑"
        )

    # ------------------------------------------------------------------ 提示

    def notify(self, message: str, kind: str = "info") -> None:
        Toast.show_message(self, message, kind)

    # ------------------------------------------------------------------ 視窗狀態

    def _restore_geometry(self) -> None:
        stored = self._settings.window_geometry
        if not stored:
            return
        try:
            data = QByteArray.fromBase64(stored.encode("ascii"))
            self.restoreGeometry(data)
        except (ValueError, TypeError):  # pragma: no cover - 損壞的設定
            pass

    def closeEvent(self, event) -> None:
        try:
            geometry = bytes(self.saveGeometry().toBase64()).decode("ascii")
            self._settings.window_geometry = geometry
            self._settings.save()
        except (ValueError, RuntimeError):  # pragma: no cover
            pass
        if self._convert_page.has_running_jobs:
            self._queue.cancel_all()
        super().closeEvent(event)
