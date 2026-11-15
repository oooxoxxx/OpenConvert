"""轉換佇列表格。

每一列對應一個 :class:`~openconvert.core.job.Job`。表格只負責顯示，
不執行任何轉換邏輯；操作按鈕以訊號回報給頁面。
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QWidget,
)

from ...core.job import Job, JobStatus
from ...core.kinds import kind_label

_HEADERS = ("檔案", "類型", "目標", "狀態", "進度", "操作")

_MUTED = QColor("#949dae")


@dataclass
class _Row:
    job: Job
    progress: QProgressBar
    button: QPushButton


class JobTable(QTableWidget):
    """顯示工作清單並回報使用者的取消 / 開啟動作。"""

    cancelRequested = Signal(str)
    openRequested = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(0, len(_HEADERS), parent)
        self.setHorizontalHeaderLabels(_HEADERS)
        self.verticalHeader().setVisible(False)
        self.setShowGrid(False)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setWordWrap(False)
        self.setTextElideMode(Qt.TextElideMode.ElideMiddle)
        self.verticalHeader().setDefaultSectionSize(48)

        header = self.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for column, width in ((1, 68), (2, 118), (3, 76), (4, 128), (5, 88)):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.Fixed)
            self.setColumnWidth(column, width)

        self._rows: dict[str, _Row] = {}
        self._order: list[str] = []

    # ------------------------------------------------------------------ 建表

    def set_jobs(self, jobs: list[Job]) -> None:
        self.clear_jobs()
        for job in jobs:
            self.append_job(job)

    def append_job(self, job: Job) -> None:
        index = self.rowCount()
        self.insertRow(index)
        self._build_row(index, job)
        self._order.append(job.id)

    def clear_jobs(self) -> None:
        self._rows.clear()
        self._order.clear()
        self.clearContents()
        self.setRowCount(0)

    def _build_row(self, index: int, job: Job) -> None:
        name_item = QTableWidgetItem(job.display_name)
        name_item.setToolTip("\n".join(str(p) for p in job.sources))
        self.setItem(index, 0, name_item)

        kind_item = QTableWidgetItem(kind_label(job.source))
        kind_item.setForeground(_MUTED)
        self.setItem(index, 1, kind_item)

        self.setItem(index, 2, QTableWidgetItem(job.target.label))

        status_item = QTableWidgetItem(job.status.label)
        self.setItem(index, 3, status_item)

        progress = QProgressBar()
        progress.setRange(0, 1000)
        progress.setValue(0)
        progress.setTextVisible(False)
        progress.setFixedHeight(8)
        progress_wrap = QWidget()
        wrap_layout = QHBoxLayout(progress_wrap)
        wrap_layout.setContentsMargins(8, 0, 14, 0)
        wrap_layout.addWidget(progress)
        self.setCellWidget(index, 4, progress_wrap)

        button = QPushButton("取消")
        button.setObjectName("Ghost")
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.clicked.connect(lambda _checked=False, jid=job.id: self._on_action(jid))
        action_wrap = QWidget()
        action_layout = QHBoxLayout(action_wrap)
        action_layout.setContentsMargins(2, 0, 6, 0)
        action_layout.addWidget(button)
        self.setCellWidget(index, 5, action_wrap)

        self._rows[job.id] = _Row(job=job, progress=progress, button=button)
        self._refresh_row(job)

    # ------------------------------------------------------------------ 更新

    def update_job(self, job: Job) -> None:
        if job.id not in self._rows:
            return
        self._refresh_row(job)

    def _refresh_row(self, job: Job) -> None:
        row = self._rows.get(job.id)
        if row is None:
            return
        row.job = job
        index = self._index_of(job.id)
        if index < 0:
            return

        status_item = self.item(index, 3)
        if status_item is not None:
            status_item.setText(job.status.label)
            status_item.setForeground(self._status_color(job))

        if job.status is JobStatus.DONE:
            row.progress.setValue(1000)
        elif job.status is JobStatus.RUNNING:
            row.progress.setValue(int(job.progress * 1000))

        state = {JobStatus.DONE: "done", JobStatus.FAILED: "failed"}.get(job.status, "idle")
        if row.progress.property("state") != state:
            row.progress.setProperty("state", state)
            row.progress.style().unpolish(row.progress)
            row.progress.style().polish(row.progress)

        name_item = self.item(index, 0)
        if name_item is not None:
            tooltip = "\n".join(str(p) for p in job.sources)
            if job.error:
                tooltip += f"\n\n錯誤：{job.error}"
            elif job.message:
                tooltip += f"\n\n{job.message}"
            name_item.setToolTip(tooltip)

        if job.status in (JobStatus.PENDING, JobStatus.RUNNING):
            row.button.setText("取消")
            row.button.setEnabled(True)
        elif job.status is JobStatus.DONE:
            row.button.setText("開啟")
            row.button.setEnabled(True)
        else:
            row.button.setText("—")
            row.button.setEnabled(False)

    @staticmethod
    def _status_color(job: Job) -> QColor:
        return {
            JobStatus.DONE: QColor("#3fb950"),
            JobStatus.FAILED: QColor("#f85149"),
            JobStatus.RUNNING: QColor("#4c8dff"),
            JobStatus.SKIPPED: QColor("#d29922"),
        }.get(job.status, _MUTED)

    # ------------------------------------------------------------------ 查詢

    def _index_of(self, job_id: str) -> int:
        try:
            return self._order.index(job_id)
        except ValueError:
            return -1

    def selected_job_ids(self) -> list[str]:
        result: list[str] = []
        for index in sorted({i.row() for i in self.selectedIndexes()}):
            if 0 <= index < len(self._order):
                result.append(self._order[index])
        return result

    def job_ids(self) -> list[str]:
        return list(self._order)

    # ------------------------------------------------------------------ 互動

    def _on_action(self, job_id: str) -> None:
        row = self._rows.get(job_id)
        if row is None:
            return
        if row.job.status in (JobStatus.PENDING, JobStatus.RUNNING):
            self.cancelRequested.emit(job_id)
        elif row.job.status is JobStatus.DONE:
            self.openRequested.emit(job_id)
