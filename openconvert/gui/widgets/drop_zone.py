"""拖放區。"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QDragEnterEvent, QDragLeaveEvent, QDropEvent
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from .. import icons


class DropZone(QFrame):
    """可拖放檔案的區域，也提供「選擇檔案」按鈕。"""

    filesDropped = Signal(list)
    browseRequested = Signal()

    def __init__(
        self,
        title: str,
        subtitle: str,
        *,
        icon_name: str = "plus",
        action_text: str = "選擇檔案",
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("DropZone")
        self.setAcceptDrops(True)
        self.setProperty("dragging", False)
        self.setMinimumHeight(210)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(10)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._icon = QLabel()
        self._icon.setPixmap(icons.icon(icon_name, "#5c6675", 40).pixmap(40, 40))
        self._icon.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._title = QLabel(title)
        self._title.setObjectName("H2")
        self._title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._subtitle = QLabel(subtitle)
        self._subtitle.setObjectName("Muted")
        self._subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._subtitle.setWordWrap(True)

        self._button = QPushButton(action_text)
        self._button.setObjectName("Primary")
        self._button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._button.clicked.connect(self.browseRequested.emit)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        button_row.addWidget(self._button)
        button_row.addStretch(1)

        layout.addWidget(self._icon)
        layout.addWidget(self._title)
        layout.addWidget(self._subtitle)
        layout.addSpacing(6)
        layout.addLayout(button_row)

    # ------------------------------------------------------------ 狀態

    def set_icon(self, name: str, color: str) -> None:
        self._icon.setPixmap(icons.icon(name, color, 40).pixmap(40, 40))

    def set_texts(self, title: str, subtitle: str, action_text: str | None = None) -> None:
        self._title.setText(title)
        self._subtitle.setText(subtitle)
        if action_text is not None:
            self._button.setText(action_text)

    def _set_dragging(self, active: bool) -> None:
        if self.property("dragging") == active:
            return
        self.setProperty("dragging", active)
        style = self.style()
        style.unpolish(self)
        style.polish(self)
        self.update()

    # ------------------------------------------------------------ 事件

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self._set_dragging(True)
        else:
            event.ignore()

    def dragLeaveEvent(self, event: QDragLeaveEvent) -> None:
        self._set_dragging(False)
        super().dragLeaveEvent(event)

    def dropEvent(self, event: QDropEvent) -> None:
        self._set_dragging(False)
        paths = [Path(url.toLocalFile()) for url in event.mimeData().urls() if url.isLocalFile()]
        if paths:
            event.acceptProposedAction()
            self.filesDropped.emit(paths)
        else:
            event.ignore()
