"""輕量提示訊息（不阻斷操作）。"""

from __future__ import annotations

from typing import ClassVar

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QGraphicsOpacityEffect, QLabel, QWidget

_KIND_COLORS = {
    "info": ("#4c8dff", "#141a26"),
    "success": ("#3fb950", "#12200f"),
    "warning": ("#d29922", "#241d0c"),
    "error": ("#f85149", "#2a1315"),
}


class Toast(QLabel):
    """顯示在視窗底部的短暫訊息。"""

    _active: ClassVar[list[Toast]] = []

    def __init__(self, parent: QWidget, text: str, kind: str = "info") -> None:
        super().__init__(parent)
        color, background = _KIND_COLORS.get(kind, _KIND_COLORS["info"])
        self.setWordWrap(True)
        self.setText(text)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet(
            f"QLabel {{ background: {background}; color: {color};"
            f" border: 1px solid {color}66; border-radius: 10px;"
            f" padding: 10px 18px; font-size: 13px; }}"
        )
        self.setGraphicsEffect(QGraphicsOpacityEffect(self))
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        self.adjustSize()
        self._reposition()
        self.show()
        self.raise_()

        QTimer.singleShot(3200, self._fade_out)

    @classmethod
    def show_message(cls, parent: QWidget, text: str, kind: str = "info") -> Toast:
        for existing in list(cls._active):
            existing._dispose()
        toast = cls(parent, text, kind)
        cls._active.append(toast)
        return toast

    # ------------------------------------------------------------ 版面

    def _reposition(self) -> None:
        parent = self.parentWidget()
        if parent is None:
            return
        limit = min(560, max(240, parent.width() - 120))
        self.setMaximumWidth(limit)
        # 讓提示框只佔文字需要的寬度，避免蓋住底部狀態列的文字。
        self.setFixedWidth(min(limit, max(200, self.sizeHint().width())))
        self.adjustSize()
        x = (parent.width() - self.width()) // 2
        y = parent.height() - self.height() - 36
        self.move(max(12, x), max(12, y))

    def _fade_out(self) -> None:
        effect = self.graphicsEffect()
        if isinstance(effect, QGraphicsOpacityEffect):
            effect.setOpacity(0.0)
        self._dispose()

    def _dispose(self) -> None:
        if self in Toast._active:
            Toast._active.remove(self)
        self.hide()
        self.deleteLater()
