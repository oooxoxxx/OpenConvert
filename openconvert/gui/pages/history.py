"""轉換紀錄頁。"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...core import history
from ..utils import open_path
from ..widgets.toast import Toast


class HistoryPage(QWidget):
    def __init__(self, notify: Callable[[str, str], None], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._notify = notify
        self._entries: list[history.HistoryEntry] = []
        self._visible_entries: list[history.HistoryEntry] = []
        self._build_ui()
        self.refresh()

    # ------------------------------------------------------------------ 版面

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(26, 20, 26, 18)
        root.setSpacing(14)

        header = QHBoxLayout()
        column = QVBoxLayout()
        column.setSpacing(2)
        title = QLabel("轉換紀錄")
        title.setObjectName("H1")
        subtitle = QLabel("只保存在這台電腦上，不會上傳。")
        subtitle.setObjectName("Muted")
        column.addWidget(title)
        column.addWidget(subtitle)
        header.addLayout(column)
        header.addStretch(1)

        self._open_button = QPushButton("開啟輸出")
        self._open_button.clicked.connect(self._open_selected)
        refresh = QPushButton("重新整理")
        refresh.setObjectName("Ghost")
        refresh.clicked.connect(self.refresh)
        clear = QPushButton("清除紀錄")
        clear.setObjectName("Danger")
        clear.clicked.connect(self._clear)

        header.addWidget(self._open_button, 0, Qt.AlignmentFlag.AlignBottom)
        header.addWidget(refresh, 0, Qt.AlignmentFlag.AlignBottom)
        header.addWidget(clear, 0, Qt.AlignmentFlag.AlignBottom)
        root.addLayout(header)

        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText("搜尋檔名或格式…")
        self._search_edit.setClearButtonEnabled(True)
        self._search_edit.textChanged.connect(self.refresh)
        root.addWidget(self._search_edit)

        self._table = QTableWidget(0, 5)
        self._table.setObjectName("HistoryTable")
        self._table.setHorizontalHeaderLabels(("時間", "檔案", "目標", "結果", "耗時"))
        self._table.verticalHeader().setVisible(False)
        self._table.setShowGrid(False)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setWordWrap(False)
        self._table.setTextElideMode(Qt.TextElideMode.ElideMiddle)
        self._table.verticalHeader().setDefaultSectionSize(40)
        header_view = self._table.horizontalHeader()
        header_view.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        header_view.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header_view.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        header_view.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        header_view.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        self._table.setColumnWidth(0, 140)
        self._table.setColumnWidth(2, 110)
        self._table.setColumnWidth(3, 80)
        self._table.setColumnWidth(4, 90)
        self._table.doubleClicked.connect(self._open_selected)
        root.addWidget(self._table, 1)

        self._empty = QLabel("還沒有任何轉換紀錄。")
        self._empty.setObjectName("Muted")
        self._empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self._empty)

    # ------------------------------------------------------------------ 資料

    def refresh(self) -> None:
        self._entries = history.load_entries(limit=300)
        query = self._search_edit.text().strip().lower()
        filtered = [
            entry
            for entry in self._entries
            if not query
            or any(query in str(source).lower() for source in entry.sources)
            or query in entry.target_label.lower()
            or query in _status_label(entry.status).lower()
        ]
        self._visible_entries = filtered
        self._table.setRowCount(len(filtered))
        self._open_button.setEnabled(bool(filtered))
        self._empty.setVisible(not filtered)
        self._table.setVisible(bool(filtered))

        for row, entry in enumerate(filtered):
            self._table.setItem(row, 0, QTableWidgetItem(entry.when))
            name = "、".join(_basename(p) for p in entry.sources[:2])
            if len(entry.sources) > 2:
                name += f" 等 {len(entry.sources)} 個"
            name_item = QTableWidgetItem(name)
            name_item.setToolTip("\n".join(entry.sources))
            self._table.setItem(row, 1, name_item)
            self._table.setItem(row, 2, QTableWidgetItem(entry.target_label))

            status_item = QTableWidgetItem(_status_label(entry.status))
            status_item.setForeground(_status_color(entry.status))
            if entry.error:
                status_item.setToolTip(entry.error)
                name_item.setToolTip("\n".join(entry.sources) + f"\n\n錯誤：{entry.error}")
            self._table.setItem(row, 3, status_item)

            duration = f"{entry.duration_seconds:.1f} 秒" if entry.duration_seconds else "—"
            self._table.setItem(row, 4, QTableWidgetItem(duration))

    def _selected_entry(self) -> history.HistoryEntry | None:
        rows = sorted({index.row() for index in self._table.selectedIndexes()})
        if not rows or rows[0] >= len(self._visible_entries):
            return None
        return self._visible_entries[rows[0]]

    def _open_selected(self) -> None:
        entry = self._selected_entry()
        if entry is None:
            self._notify("請先選取一筆紀錄。", "info")
            return
        if not entry.outputs:
            self._notify("這筆紀錄沒有輸出檔案。", "warning")
            return
        target = entry.outputs[0]
        if not open_path(target):
            self._notify("找不到輸出檔案，可能已被移動或刪除。", "warning")

    def _clear(self) -> None:
        history.clear()
        self.refresh()
        Toast.show_message(self.window(), "已清除轉換紀錄。", "info")


def _basename(path: str) -> str:
    from pathlib import Path

    return Path(path).name


def _status_label(status: str) -> str:
    return {
        "done": "完成",
        "failed": "失敗",
        "cancelled": "已取消",
        "skipped": "略過",
        "pending": "等待中",
        "running": "轉換中",
    }.get(status, status)


def _status_color(status: str):
    from PySide6.QtGui import QColor

    return {
        "done": QColor("#3fb950"),
        "failed": QColor("#f85149"),
        "skipped": QColor("#d29922"),
    }.get(status, QColor("#949dae"))
