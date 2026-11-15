"""深色 / 淺色主題。

所有顏色集中在 ``TOKENS``，QSS 以 ``@token@`` 佔位，避免在樣式表裡散落色碼。
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QFontDatabase, QGuiApplication
from PySide6.QtWidgets import QApplication

DARK = {
    "bg": "#12141a",
    "surface": "#181b22",
    "surface2": "#21252e",
    "hover": "#2a2f3a",
    "border": "#282d37",
    "border_strong": "#3a4150",
    "text": "#e8ebf1",
    "muted": "#949dae",
    "accent": "#4c8dff",
    "accent_hover": "#6ba0ff",
    "accent_soft": "#1d2b45",
    "accent_border": "#3a5f9e",
    "success": "#3fb950",
    "success_soft": "#16301c",
    "danger": "#f85149",
    "danger_soft": "#3a1a1a",
    "warning": "#d29922",
}

LIGHT = {
    "bg": "#f4f6f9",
    "surface": "#ffffff",
    "surface2": "#eef1f5",
    "hover": "#e3e8ef",
    "border": "#dde2ea",
    "border_strong": "#c3cbd8",
    "text": "#161a20",
    "muted": "#5c6675",
    "accent": "#2563eb",
    "accent_hover": "#1d4ed8",
    "accent_soft": "#e5edff",
    "accent_border": "#a9c1f5",
    "success": "#1a7f37",
    "success_soft": "#e6f5ea",
    "danger": "#cf222e",
    "danger_soft": "#ffebe9",
    "warning": "#9a6700",
}

_QSS = """
* { outline: none; }

QWidget {
    color: @text@;
    font-size: 13px;
}

QMainWindow, QWidget#Root { background: @bg@; }

QLabel { background: transparent; }
QLabel#H1 { font-size: 21px; font-weight: 700; }
QLabel#H2 { font-size: 14px; font-weight: 600; }
QLabel#Muted { color: @muted@; font-size: 12px; }
QLabel#Mono { font-family: "Cascadia Mono", "Consolas", monospace; font-size: 12px; color: @muted@; }

/* ---------------------------------------------------------------- 側邊欄 */

QFrame#Sidebar {
    background: @surface@;
    border-right: 1px solid @border@;
}
QLabel#Brand { font-size: 16px; font-weight: 700; }
QLabel#BrandSub { font-size: 11px; color: @muted@; }

QPushButton#NavButton {
    text-align: left;
    padding: 9px 12px;
    border: none;
    border-radius: 9px;
    background: transparent;
    color: @muted@;
    font-size: 13px;
}
QPushButton#NavButton:hover { background: @surface2@; color: @text@; }
QPushButton#NavButton[active="true"] {
    background: @accent_soft@;
    color: @accent@;
    font-weight: 600;
}

/* ------------------------------------------------------------------ 按鈕 */

QPushButton {
    background: @surface2@;
    color: @text@;
    border: 1px solid @border@;
    border-radius: 8px;
    padding: 7px 14px;
    min-height: 20px;
}
QPushButton:hover { background: @hover@; }
QPushButton:pressed { background: @border@; }
QPushButton:disabled { color: @muted@; background: @surface@; border-color: @border@; }

QPushButton#Primary {
    background: @accent@;
    color: #ffffff;
    border: none;
    font-weight: 600;
    padding: 9px 20px;
}
QPushButton#Primary:hover { background: @accent_hover@; }
QPushButton#Primary:disabled { background: @surface2@; color: @muted@; }

QPushButton#Ghost {
    background: transparent;
    border: none;
    color: @muted@;
    padding: 6px 10px;
}
QPushButton#Ghost:hover { color: @text@; background: @surface2@; }

QPushButton#Danger { color: @danger@; }
QPushButton#Danger:hover { background: @danger_soft@; }

QPushButton#Link {
    background: transparent;
    border: none;
    color: @accent@;
    padding: 2px 4px;
    text-align: left;
}
QPushButton#Link:hover { color: @accent_hover@; text-decoration: underline; }

/* ------------------------------------------------------------------ 輸入 */

QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {
    background: @surface2@;
    border: 1px solid @border@;
    border-radius: 8px;
    padding: 7px 10px;
    selection-background-color: @accent@;
    selection-color: #ffffff;
}
QLineEdit:hover, QComboBox:hover, QSpinBox:hover { border-color: @border_strong@; }
QLineEdit:focus, QComboBox:focus, QSpinBox:focus { border-color: @accent@; }
QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled { color: @muted@; }

QComboBox::drop-down { border: none; width: 24px; }
QComboBox QAbstractItemView {
    background: @surface@;
    border: 1px solid @border@;
    border-radius: 8px;
    padding: 4px;
    outline: none;
    selection-background-color: @accent_soft@;
    selection-color: @text@;
}
QComboBox QAbstractItemView::item { padding: 6px 10px; border-radius: 6px; min-height: 20px; }

QSpinBox::up-button, QSpinBox::down-button { width: 16px; border: none; background: transparent; }

/* ---------------------------------------------------------------- 容器 */

QFrame#Card {
    background: @surface@;
    border: 1px solid @border@;
    border-radius: 14px;
}
QFrame#Divider { background: @border@; max-height: 1px; border: none; }

QFrame#DropZone {
    background: @surface@;
    border: 2px dashed @border_strong@;
    border-radius: 16px;
}
QFrame#DropZone[dragging="true"] {
    border-color: @accent@;
    background: @accent_soft@;
}

/* ---------------------------------------------------------------- 表格 */

QTableWidget {
    background: @surface@;
    border: 1px solid @border@;
    border-radius: 12px;
    gridline-color: transparent;
    selection-background-color: @accent_soft@;
    selection-color: @text@;
}
QTableWidget::item { padding: 6px 8px; border-bottom: 1px solid @border@; }
QTableWidget::item:selected { background: @accent_soft@; color: @text@; }

QHeaderView::section {
    background: @surface@;
    color: @muted@;
    border: none;
    border-bottom: 1px solid @border@;
    padding: 9px 8px;
    font-size: 11px;
    font-weight: 600;
}
QTableCornerButton::section { background: @surface@; border: none; }

QTableWidget#HistoryTable::item { padding: 8px; }

/* ---------------------------------------------------------------- 進度 */

QProgressBar {
    background: @surface2@;
    border: none;
    border-radius: 4px;
    height: 8px;
    text-align: center;
    color: @muted@;
    font-size: 11px;
}
QProgressBar::chunk { border-radius: 4px; background: @accent@; }
QProgressBar[state="done"]::chunk { background: @success@; }
QProgressBar[state="failed"]::chunk { background: @danger@; }

/* ---------------------------------------------------------------- 勾選 */

QCheckBox { spacing: 8px; color: @text@; }
QCheckBox::indicator {
    width: 17px; height: 17px;
    border-radius: 5px;
    border: 1px solid @border_strong@;
    background: @surface2@;
}
QCheckBox::indicator:hover { border-color: @accent@; }
QCheckBox::indicator:checked { background: @accent@; border-color: @accent@; image: none; }

QRadioButton { spacing: 8px; }

/* ---------------------------------------------------------------- 捲軸 */

QScrollBar:vertical {
    background: transparent;
    width: 10px;
    margin: 2px;
}
QScrollBar::handle:vertical {
    background: @border_strong@;
    border-radius: 5px;
    min-height: 30px;
}
QScrollBar::handle:vertical:hover { background: @muted@; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }

QScrollBar:horizontal { background: transparent; height: 10px; margin: 2px; }
QScrollBar::handle:horizontal { background: @border_strong@; border-radius: 5px; min-width: 30px; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal { background: transparent; }

QScrollArea { background: transparent; border: none; }

/* ---------------------------------------------------------------- 其他 */

QToolTip {
    background: @surface2@;
    color: @text@;
    border: 1px solid @border@;
    border-radius: 6px;
    padding: 6px 8px;
}

QStatusBar { background: @surface@; border-top: 1px solid @border@; color: @muted@; }
QStatusBar::item { border: none; }

QSplitter::handle { background: transparent; }

QMenu {
    background: @surface@;
    border: 1px solid @border@;
    border-radius: 8px;
    padding: 4px;
}
QMenu::item { padding: 7px 20px; border-radius: 6px; }
QMenu::item:selected { background: @accent_soft@; }

QTextBrowser, QPlainTextEdit {
    background: @surface2@;
    border: 1px solid @border@;
    border-radius: 10px;
    padding: 8px;
    selection-background-color: @accent@;
}

QDialog { background: @bg@; }
QMessageBox { background: @bg@; }
"""

#: 依序嘗試的字型家族；第一個存在的會被採用。
#: 必須包含 CJK 字型，否則中文會變成方框。
FONT_PREFERENCES = (
    "Microsoft JhengHei UI",
    "Microsoft YaHei UI",
    "Segoe UI Variable Text",
    "Segoe UI",
    "PingFang TC",
    "Noto Sans CJK TC",
    "Noto Sans TC",
    "Source Han Sans TC",
    "DejaVu Sans",
)

BASE_POINT_SIZE = 9.75


def application_font() -> QFont:
    """挑一個系統實際存在、且支援中文的字型。"""
    try:
        available = set(QFontDatabase.families())
    except RuntimeError:  # pragma: no cover - 沒有 GUI 環境
        available = set()

    for family in FONT_PREFERENCES:
        if family in available:
            font = QFont(family)
            font.setPointSizeF(BASE_POINT_SIZE)
            return font

    font = QFont()
    font.setPointSizeF(BASE_POINT_SIZE)
    return font


def tokens_for(theme: str) -> dict[str, str]:
    """``"system"`` 會依作業系統目前的深色/淺色偏好決定。"""
    if theme == "dark":
        return DARK
    if theme == "light":
        return LIGHT
    return DARK if system_prefers_dark() else LIGHT


def system_prefers_dark() -> bool:
    try:
        hints = QGuiApplication.styleHints()
        return hints.colorScheme() == Qt.ColorScheme.Dark
    except (AttributeError, RuntimeError):  # pragma: no cover - 舊版 Qt
        return True


def build_qss(tokens: dict[str, str]) -> str:
    qss = _QSS
    for key, value in tokens.items():
        qss = qss.replace(f"@{key}@", value)
    return qss


def apply_theme(app: QApplication, theme: str) -> dict[str, str]:
    """套用主題並回傳實際使用的色票（供圖示著色使用）。"""
    tokens = tokens_for(theme)
    app.setStyleSheet(build_qss(tokens))
    return tokens


def resolve(theme: str) -> str:
    """把 ``"system"`` 解析成實際的 ``"dark"`` / ``"light"``。"""
    if theme in ("dark", "light"):
        return theme
    return "dark" if system_prefers_dark() else "light"
