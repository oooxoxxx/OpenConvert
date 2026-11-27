"""轉換佇列表格。

每一列對應一個 :class:`~openconvert.core.job.Job`。表格只負責顯示，
不執行任何轉換邏輯；操作按鈕與每列的目標下拉以訊號回報給頁面。
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QDropEvent
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QMenu,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QWidget,
)

from ...core.job import Job, JobStatus
from ...core.kinds import kind_label
from ...core.targets import TargetSpec

_HEADERS = ("檔案", "類型", "目標", "狀態", "進度", "操作")

_MUTED = QColor("#949dae")


@dataclass
class _Row:
    job: Job
    progress: QProgressBar
    button: QPushButton
    combo: QComboBox | None = None


class JobTable(QTableWidget):
    """顯示工作清單並回報使用者的取消 / 開啟 / 重試 / 換目標動作。"""

    cancelRequested = Signal(str)
    openRequested = Signal(str)
    retryRequested = Signal(str)
    removeRequested = Signal(str)
    moveUp = Signal(str)
    moveDown = Signal(str)
    orderChanged = Signal(list)  # 拖放後的 job_id 順序
    targetChanged = Signal(str, str)  # job_id, token

    def __init__(self, parent=None) -> None:
        super().__init__(0, len(_HEADERS), parent)
        self.setHorizontalHeaderLabels(_HEADERS)
        self.verticalHeader().setVisible(False)
        self.setShowGrid(False)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setDragDropOverwriteMode(False)
        self.setDropIndicatorShown(True)
        self._reordering_enabled = True
        self.setDragEnabled(True)
        self.setWordWrap(False)
        self.setTextElideMode(Qt.TextElideMode.ElideMiddle)
        self.verticalHeader().setDefaultSectionSize(48)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

        header = self.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for column, width in ((1, 68), (2, 168), (3, 76), (4, 128), (5, 96)):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.Fixed)
            self.setColumnWidth(column, width)

        self._rows: dict[str, _Row] = {}
        self._order: list[str] = []
        self._target_specs: list[TargetSpec] = []

    # ------------------------------------------------------------------ 建表

    def set_target_specs(self, specs: list[TargetSpec]) -> None:
        self._target_specs = list(specs)

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

    def _targets_for(self, job: Job) -> list[TargetSpec]:
        """這個工作可以選的目標：對所有來源都適用的格式。"""
        candidates = [spec for spec in self._target_specs if all(spec.accepts(src) for src in job.sources)]
        if all(spec.token != job.target.token for spec in candidates):
            candidates.append(job.target)
        return candidates

    def _build_row(self, index: int, job: Job) -> None:
        name_item = QTableWidgetItem(job.display_name)
        name_item.setToolTip("\n".join(str(p) for p in job.sources))
        self.setItem(index, 0, name_item)

        kind_item = QTableWidgetItem(kind_label(job.source))
        kind_item.setForeground(_MUTED)
        self.setItem(index, 1, kind_item)

        combo: QComboBox | None = None
        if job.status is JobStatus.PENDING:
            combo = QComboBox()
            for spec in self._targets_for(job):
                combo.addItem(spec.label, spec.token)
            combo.setCurrentIndex(max(0, combo.findData(job.target.token)))
            combo.currentIndexChanged.connect(
                lambda _index, jid=job.id, box=combo: self._on_target_changed(jid, box)
            )
            self.setCellWidget(index, 2, combo)
        else:
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

        self._rows[job.id] = _Row(job=job, progress=progress, button=button, combo=combo)
        self._refresh_row(job)

    def _on_target_changed(self, job_id: str, combo: QComboBox) -> None:
        token = combo.currentData()
        if token:
            self.targetChanged.emit(job_id, token)

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
        elif job.status is JobStatus.FAILED:
            row.button.setText("重試")
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

    # ------------------------------------------------------------------ 拖放排序

    def set_reordering_enabled(self, enabled: bool) -> None:
        self._reordering_enabled = enabled
        self.setDragEnabled(enabled)

    def dropEvent(self, event: QDropEvent) -> None:
        """自行計算新順序，不交給 Qt 移動項目，避免 cell widget 與工作列錯位。"""
        if not self._reordering_enabled or event.source() is not self:
            event.ignore()
            return

        selected = self.selected_job_ids()
        if not selected:
            event.ignore()
            return

        row = self.indexAt(event.position().toPoint()).row()
        position = self.dropIndicatorPosition()
        if row < 0 or position == QAbstractItemView.DropIndicatorPosition.OnViewport:
            target = len(self._order)
        else:
            target = row + int(position == QAbstractItemView.DropIndicatorPosition.BelowItem)

        order = self._order_after_drop(selected, target)
        if order == self._order:
            event.ignore()
            return

        event.setDropAction(Qt.DropAction.MoveAction)
        event.accept()
        self.orderChanged.emit(order)

    def _order_after_drop(self, selected: list[str], target: int) -> list[str]:
        """回傳把選取列插到 target 前的順序；target 以拖曳前的列號計算。"""
        moving = set(selected)
        moved = [job_id for job_id in self._order if job_id in moving]
        if not moved:
            return list(self._order)

        target = max(0, min(len(self._order), target))
        removed_before = sum(
            1 for index, job_id in enumerate(self._order) if index < target and job_id in moving
        )
        remaining = [job_id for job_id in self._order if job_id not in moving]
        insertion = max(0, min(len(remaining), target - removed_before))
        return remaining[:insertion] + moved + remaining[insertion:]

    # ------------------------------------------------------------------ 互動

    def _on_action(self, job_id: str) -> None:
        row = self._rows.get(job_id)
        if row is None:
            return
        if row.job.status in (JobStatus.PENDING, JobStatus.RUNNING):
            self.cancelRequested.emit(job_id)
        elif row.job.status is JobStatus.DONE:
            self.openRequested.emit(job_id)
        elif row.job.status is JobStatus.FAILED:
            self.retryRequested.emit(job_id)

    def _show_context_menu(self, position) -> None:
        index = self.indexAt(position)
        if index.row() < 0 or index.row() >= len(self._order):
            return
        job_id = self._order[index.row()]
        row = self._rows.get(job_id)
        if row is None:
            return

        menu = QMenu(self)
        if row.job.outputs:
            menu.addAction("開啟輸出資料夾", lambda: self.openRequested.emit(job_id))
        if row.job.status is JobStatus.FAILED:
            menu.addAction("重試", lambda: self.retryRequested.emit(job_id))
        if row.job.status is not JobStatus.RUNNING:
            menu.addAction("上移", lambda: self.moveUp.emit(job_id))
            menu.addAction("下移", lambda: self.moveDown.emit(job_id))
            menu.addSeparator()
            menu.addAction("移除工作", lambda: self.removeRequested.emit(job_id))
        if menu.isEmpty():
            return
        menu.exec(self.viewport().mapToGlobal(position))
