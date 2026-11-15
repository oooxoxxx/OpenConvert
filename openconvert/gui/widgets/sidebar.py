"""側邊導覽列。"""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from ... import __version__
from .. import icons

NAV_ITEMS: tuple[tuple[str, str], ...] = (
    ("convert", "轉換檔案"),
    ("inspect", "檔案資訊"),
    ("history", "轉換紀錄"),
    ("settings", "設定"),
    ("about", "關於"),
)

NAV_ICONS: tuple[str, ...] = ("convert", "inspect", "history", "settings", "about")


class Sidebar(QFrame):
    navigate = Signal(int)
    themeToggleRequested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("Sidebar")
        self.setFixedWidth(212)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 18, 14, 14)
        layout.setSpacing(4)

        layout.addLayout(self._build_brand())
        layout.addSpacing(18)

        self._buttons: list[QPushButton] = []
        for index, (_key, label) in enumerate(NAV_ITEMS):
            button = QPushButton(label)
            button.setObjectName("NavButton")
            button.setCheckable(False)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setProperty("active", index == 0)
            button.setIconSize(QSize(18, 18))
            button.setMinimumHeight(38)
            button.clicked.connect(lambda _checked=False, i=index: self.navigate.emit(i))
            self._buttons.append(button)
            layout.addWidget(button)

        layout.addStretch(1)

        divider = QFrame()
        divider.setObjectName("Divider")
        divider.setFrameShape(QFrame.Shape.HLine)
        layout.addWidget(divider)
        layout.addSpacing(8)

        self._theme_button = QPushButton("淺色模式")
        self._theme_button.setObjectName("Ghost")
        self._theme_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._theme_button.setMinimumHeight(32)
        self._theme_button.clicked.connect(self.themeToggleRequested.emit)
        layout.addWidget(self._theme_button)

        version = QLabel(f"版本 {__version__}")
        version.setObjectName("Muted")
        version.setContentsMargins(6, 4, 0, 0)
        layout.addWidget(version)

        self._colors = {"nav": "#949dae", "accent": "#4c8dff", "muted": "#949dae"}

    # ------------------------------------------------------------------ 品牌

    def _build_brand(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(9)
        row.setContentsMargins(4, 0, 0, 0)

        logo = QLabel()
        logo.setPixmap(icons.app_icon().pixmap(34, 34))
        logo.setFixedSize(QSize(34, 34))

        text_column = QVBoxLayout()
        text_column.setSpacing(0)
        name = QLabel("OpenConvert")
        name.setObjectName("Brand")
        subtitle = QLabel("免費 · 離線 · 開源")
        subtitle.setObjectName("BrandSub")
        text_column.addWidget(name)
        text_column.addWidget(subtitle)

        row.addWidget(logo)
        row.addLayout(text_column)
        row.addStretch(1)
        return row

    # ------------------------------------------------------------------ 主題

    def apply_colors(self, tokens: dict[str, str], dark: bool) -> None:
        self._colors = tokens
        for index, button in enumerate(self._buttons):
            button.setIcon(icons.icon(NAV_ICONS[index], tokens["muted"], 18))
        self._theme_button.setIcon(icons.icon("sun" if dark else "moon", tokens["muted"], 16))
        self._theme_button.setText("淺色模式" if dark else "深色模式")
        self._refresh_active_icons()

    def set_active(self, index: int) -> None:
        for position, button in enumerate(self._buttons):
            button.setProperty("active", position == index)
            button.style().unpolish(button)
            button.style().polish(button)
        self._refresh_active_icons()

    def _refresh_active_icons(self) -> None:
        for index, button in enumerate(self._buttons):
            color = self._colors["accent"] if button.property("active") else self._colors["muted"]
            button.setIcon(icons.icon(NAV_ICONS[index], color, 18))

    @property
    def buttons(self) -> list[QPushButton]:
        return list(self._buttons)
