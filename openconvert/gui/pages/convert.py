"""轉換主頁。"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ...core.ffmpeg import FFmpegTools
from ...core.job import Job, JobStatus
from ...core.kinds import SUPPORTED_EXTENSIONS, extension_of
from ...core.office import discover as discover_office
from ...core.settings import Settings
from ...core.targets import (
    TargetSpec,
    available_targets,
    plan_groups,
    preferred_target,
    target_by_token,
)
from ...runner import ConversionQueue
from .. import icons
from ..utils import open_outputs
from ..widgets.drop_zone import DropZone
from ..widgets.job_table import JobTable

QUALITY_OPTIONS: tuple[tuple[str, str], ...] = (
    ("高品質（檔案較大）", "high"),
    ("平衡（建議）", "balanced"),
    ("小檔案（畫質較低）", "small"),
)

SIZE_OPTIONS: tuple[tuple[str, int], ...] = (
    ("原始尺寸", 0),
    ("最大 2160 px（4K）", 2160),
    ("最大 1440 px", 1440),
    ("最大 1080 px", 1080),
    ("最大 720 px", 720),
    ("最大 480 px", 480),
)

DPI_OPTIONS: tuple[tuple[str, int], ...] = (
    ("72 dpi（螢幕預覽）", 72),
    ("150 dpi（建議）", 150),
    ("300 dpi（列印）", 300),
    ("600 dpi（高細節）", 600),
)


def _file_filter() -> str:
    patterns = " ".join(f"*.{ext}" for ext in sorted(SUPPORTED_EXTENSIONS))
    return f"支援的檔案 ({patterns});;所有檔案 (*)"


class ConvertPage(QWidget):
    """拖放 → 選格式 → 開始。"""

    historyChanged = Signal()

    def __init__(
        self,
        settings: Settings,
        tools: FFmpegTools,
        queue: ConversionQueue,
        notify: Callable[[str, str], None],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._settings = settings
        self._tools = tools
        self._queue = queue
        self._notify = notify

        self._files: list[Path] = []
        self._jobs: list[Job] = []
        self._run_jobs: list[Job] = []
        self._tokens: list[str | None] = []
        self._running = False
        self._last_dir = ""

        self.setAcceptDrops(True)
        self._build_ui()
        self._connect_queue()
        self._refresh_targets()
        self._update_state()

    # ------------------------------------------------------------------ 版面

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(26, 20, 26, 18)
        root.setSpacing(14)

        root.addLayout(self._build_header())
        root.addWidget(self._build_stack(), 1)
        root.addWidget(self._build_options())
        root.addLayout(self._build_footer())

    def _build_header(self) -> QHBoxLayout:
        header = QHBoxLayout()
        header.setSpacing(8)

        column = QVBoxLayout()
        column.setSpacing(2)
        title = QLabel("轉換檔案")
        title.setObjectName("H1")
        subtitle = QLabel("拖放檔案進來，選好格式就能開始。所有轉換都在你的電腦上完成。")
        subtitle.setObjectName("Muted")
        column.addWidget(title)
        column.addWidget(subtitle)

        header.addLayout(column)
        header.addStretch(1)

        self._remove_button = QPushButton("移除選取")
        self._remove_button.setObjectName("Ghost")
        self._remove_button.clicked.connect(self._remove_selected)

        self._clear_button = QPushButton("清空")
        self._clear_button.setObjectName("Ghost")
        self._clear_button.clicked.connect(self._clear_all)

        self._add_button = QPushButton("加入檔案")
        self._add_button.setIcon(icons.icon("plus", "#4c8dff", 16))
        self._add_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._add_button.clicked.connect(self._browse)

        header.addWidget(self._remove_button, 0, Qt.AlignmentFlag.AlignBottom)
        header.addWidget(self._clear_button, 0, Qt.AlignmentFlag.AlignBottom)
        header.addSpacing(6)
        header.addWidget(self._add_button, 0, Qt.AlignmentFlag.AlignBottom)
        return header

    def _build_stack(self) -> QWidget:
        self._drop = DropZone(
            "拖放檔案到這裡",
            "支援影片、音訊、圖片、PDF、電子書、文件、資料表、字幕、字型與壓縮，也可以直接拖入整個資料夾。",
            icon_name="plus",
            action_text="選擇檔案",
        )
        self._drop.filesDropped.connect(self.add_paths)
        self._drop.browseRequested.connect(self._browse)

        self._table = JobTable()
        self._table.cancelRequested.connect(self._queue.cancel)
        self._table.openRequested.connect(self._open_job)

        self._stack = QStackedWidget()
        self._stack.addWidget(self._drop)
        self._stack.addWidget(self._table)
        return self._stack

    def _build_options(self) -> QWidget:
        self._card = QFrame()
        self._card.setObjectName("Card")
        grid = QGridLayout(self._card)
        grid.setContentsMargins(18, 14, 18, 14)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(10)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(3, 1)

        self._target_combo = QComboBox()
        self._target_combo.setMinimumWidth(200)
        self._target_combo.currentIndexChanged.connect(self._on_target_changed)

        self._quality_combo = QComboBox()
        for label, value in QUALITY_OPTIONS:
            self._quality_combo.addItem(label, value)

        self._size_combo = QComboBox()
        for label, value in SIZE_OPTIONS:
            self._size_combo.addItem(label, value)

        self._image_quality_spin = QSpinBox()
        self._image_quality_spin.setRange(1, 100)
        self._image_quality_spin.setValue(90)
        self._image_quality_spin.setSuffix(" %")
        self._image_quality_spin.setToolTip("JPEG 與 WebP 的有損壓縮品質，數字越大檔案越大。")

        self._gif_fps_spin = QSpinBox()
        self._gif_fps_spin.setRange(5, 30)
        self._gif_fps_spin.setValue(12)
        self._gif_fps_spin.setSuffix(" fps")

        self._fps_spin = QSpinBox()
        self._fps_spin.setRange(1, 60)
        self._fps_spin.setValue(30)
        self._fps_spin.setSuffix(" fps")
        self._fps_spin.setToolTip("抽出影格或圖片轉影片時使用的影格率。")

        self._sheet_edit = QLineEdit()
        self._sheet_edit.setPlaceholderText("工作表名稱（留空表示第一個工作表）")

        self._pages_edit = QLineEdit()
        self._pages_edit.setPlaceholderText("例如 1-3,7（留空表示全部頁面）")

        self._dpi_combo = QComboBox()
        for label, value in DPI_OPTIONS:
            self._dpi_combo.addItem(label, value)
        self._dpi_combo.setCurrentIndex(1)

        self._output_edit = QLineEdit()
        self._output_edit.setPlaceholderText("與來源檔案相同資料夾")
        self._output_edit.setReadOnly(True)

        output_browse = QPushButton("選擇…")
        output_browse.clicked.connect(self._choose_output_dir)
        output_reset = QPushButton("還原")
        output_reset.setObjectName("Ghost")
        output_reset.clicked.connect(self._reset_output_dir)

        self._opt: dict[str, tuple[QWidget, ...]] = {}

        grid.addWidget(QLabel("目標格式"), 0, 0)
        grid.addWidget(self._target_combo, 0, 1, 1, 3)

        label_quality = QLabel("品質")
        label_quality.setObjectName("Muted")
        label_size = QLabel("最大尺寸")
        label_size.setObjectName("Muted")
        grid.addWidget(label_quality, 1, 0)
        grid.addWidget(self._quality_combo, 1, 1)
        grid.addWidget(label_size, 1, 2)
        grid.addWidget(self._size_combo, 1, 3)
        self._opt["quality"] = (label_quality, self._quality_combo)
        self._opt["size"] = (label_size, self._size_combo)

        label_jpeg = QLabel("影像品質")
        label_jpeg.setObjectName("Muted")
        label_gif = QLabel("GIF 影格率")
        label_gif.setObjectName("Muted")
        grid.addWidget(label_jpeg, 2, 0)
        grid.addWidget(self._image_quality_spin, 2, 1)
        grid.addWidget(label_gif, 2, 2)
        grid.addWidget(self._gif_fps_spin, 2, 3)
        self._opt["image_quality"] = (label_jpeg, self._image_quality_spin)
        self._opt["gif"] = (label_gif, self._gif_fps_spin)

        label_pages = QLabel("頁碼範圍")
        label_pages.setObjectName("Muted")
        grid.addWidget(label_pages, 3, 0)
        grid.addWidget(self._pages_edit, 3, 1, 1, 3)
        self._opt["pages"] = (label_pages, self._pages_edit)

        label_dpi = QLabel("PDF 解析度")
        label_dpi.setObjectName("Muted")
        grid.addWidget(label_dpi, 4, 0)
        grid.addWidget(self._dpi_combo, 4, 1)
        self._opt["dpi"] = (label_dpi, self._dpi_combo)

        label_fps = QLabel("影格率")
        label_fps.setObjectName("Muted")
        grid.addWidget(label_fps, 4, 2)
        grid.addWidget(self._fps_spin, 4, 3)
        self._opt["fps"] = (label_fps, self._fps_spin)

        label_sheet = QLabel("工作表")
        label_sheet.setObjectName("Muted")
        grid.addWidget(label_sheet, 5, 0)
        grid.addWidget(self._sheet_edit, 5, 1, 1, 3)
        self._opt["sheet"] = (label_sheet, self._sheet_edit)

        label_output = QLabel("輸出資料夾")
        label_output.setObjectName("Muted")
        grid.addWidget(label_output, 6, 0)
        grid.addWidget(self._output_edit, 6, 1, 1, 1)
        grid.addWidget(output_browse, 6, 2)
        grid.addWidget(output_reset, 6, 3)

        return self._card

    def _build_footer(self) -> QHBoxLayout:
        footer = QHBoxLayout()
        footer.setSpacing(12)

        self._summary = QLabel("尚未加入檔案")
        self._summary.setObjectName("Muted")

        self._overall = QProgressBar()
        self._overall.setRange(0, 1000)
        self._overall.setValue(0)
        self._overall.setTextVisible(False)
        self._overall.setFixedHeight(8)
        self._overall.setFixedWidth(200)
        self._overall.setVisible(False)

        self._cancel_all_button = QPushButton("全部取消")
        self._cancel_all_button.setObjectName("Danger")
        self._cancel_all_button.setVisible(False)
        self._cancel_all_button.clicked.connect(self._cancel_all)

        self._start_button = QPushButton("開始轉換")
        self._start_button.setObjectName("Primary")
        self._start_button.setMinimumWidth(140)
        self._start_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._start_button.clicked.connect(self._start)

        footer.addWidget(self._summary)
        footer.addStretch(1)
        footer.addWidget(self._overall)
        footer.addWidget(self._cancel_all_button)
        footer.addWidget(self._start_button)
        return footer

    # ------------------------------------------------------------------ 連線

    def _connect_queue(self) -> None:
        self._queue.job_started.connect(self._on_job_started)
        self._queue.job_progress.connect(self._on_job_progress)
        self._queue.job_finished.connect(self._on_job_finished)
        self._queue.all_finished.connect(self._on_all_finished)

    # ------------------------------------------------------------------ 外部

    def apply_settings(self, settings: Settings) -> None:
        self._settings = settings
        self._queue.apply_settings(settings)
        self._update_output_edit()

    def set_tools(self, tools: FFmpegTools) -> None:
        self._tools = tools

    # ------------------------------------------------------------------ 檔案

    def add_paths(self, paths: list[Path]) -> None:
        if self._running:
            self._notify("轉換進行中，請等待完成或先取消。", "warning")
            return

        collected: list[Path] = []
        skipped = 0
        for raw in paths:
            path = Path(raw)
            if path.is_dir():
                for child in sorted(path.rglob("*")):
                    if child.is_file() and extension_of(child) in SUPPORTED_EXTENSIONS:
                        collected.append(child)
            elif path.is_file():
                if extension_of(path) in SUPPORTED_EXTENSIONS:
                    collected.append(path)
                else:
                    skipped += 1

        existing = {p.resolve() for p in self._files}
        added: list[Path] = []
        for path in collected:
            try:
                resolved = path.resolve()
            except OSError:
                resolved = path
            if resolved in existing:
                continue
            existing.add(resolved)
            added.append(path)

        if not added:
            if skipped:
                self._notify("這些檔案類型目前不支援。", "warning")
            return

        self._files.extend(added)
        self._refresh_targets()
        self._replan()

        message = f"已加入 {len(added)} 個檔案"
        if skipped:
            message += f"，略過 {skipped} 個不支援的檔案"
        self._notify(message, "info" if not skipped else "warning")

    def _browse(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(self, "選擇要轉換的檔案", self._last_dir, _file_filter())
        if files:
            self._last_dir = str(Path(files[0]).parent)
            self.add_paths([Path(f) for f in files])

    # ------------------------------------------------------------------ 目標

    def _refresh_targets(self) -> None:
        specs = available_targets(self._files)
        previous = self._settings.last_format

        self._target_combo.blockSignals(True)
        self._target_combo.clear()
        self._tokens = []

        if not specs:
            self._target_combo.addItem("請先加入檔案", None)
            self._tokens.append(None)

        current_category = ""
        for spec in specs:
            if spec.category != current_category:
                self._target_combo.addItem(f"—— {spec.category} ——", None)
                self._tokens.append(None)
                current_category = spec.category
            self._target_combo.addItem(spec.label, spec.token)
            self._tokens.append(spec.token)

        for index, token in enumerate(self._tokens):
            if token is None:
                item = self._target_combo.model().item(index)
                if item is not None:
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEnabled)

        chosen = preferred_target(self._files, previous)
        index = self._tokens.index(chosen.token) if chosen is not None else -1
        if index < 0:
            index = self._first_real_index()
        if index >= 0:
            self._target_combo.setCurrentIndex(index)
        self._target_combo.blockSignals(False)

        self._target_combo.setEnabled(bool(specs) and not self._running)
        self._update_visibility()
        self._update_target_tooltip()

    def _first_real_index(self) -> int:
        for index, token in enumerate(self._tokens):
            if token is not None:
                return index
        return -1

    def _current_token(self) -> str | None:
        data = self._target_combo.currentData()
        return data if isinstance(data, str) else None

    def _current_spec(self) -> TargetSpec | None:
        token = self._current_token()
        return target_by_token(token) if token else None

    def _on_target_changed(self, _index: int) -> None:
        token = self._current_token()
        if token is None:
            index = self._first_real_index()
            if index >= 0:
                self._target_combo.blockSignals(True)
                self._target_combo.setCurrentIndex(index)
                self._target_combo.blockSignals(False)
                token = self._current_token()
        if token is None:
            return
        self._settings.last_format = token
        self._settings.save()
        self._update_visibility()
        self._update_target_tooltip()
        self._replan()

    def _update_target_tooltip(self) -> None:
        spec = self._current_spec()
        text = ""
        if spec is not None:
            text = spec.description or ""
            if spec.group_kinds:
                text += "\n此格式會把符合條件的檔案合併成一個輸出。"
        self._target_combo.setToolTip(text)

    def _update_visibility(self) -> None:
        spec = self._current_spec()
        converter = spec.converter if spec else ""
        token = spec.token if spec else ""

        visible = {
            "quality": converter == "media" and token not in ("video-gif", "video-frames"),
            "size": converter in ("media", "image"),
            "image_quality": converter == "image" and token in ("jpg", "webp", "avif", "heic"),
            "gif": token == "video-gif",
            "fps": token in ("video-frames", "images-video"),
            "pages": token == "pdf-extract",
            "dpi": token in ("pdf-png", "pdf-jpg", "pdf-cbz"),
            "sheet": converter == "data" and self._has_sheet_source(),
        }
        for key, widgets in self._opt.items():
            for widget in widgets:
                widget.setVisible(visible.get(key, False))

    def _has_sheet_source(self) -> bool:
        return any(path.suffix.lower() in (".xlsx", ".xlsm") for path in self._files)

    # ------------------------------------------------------------------ 規劃

    def _collect_options(self) -> dict:
        return {
            "quality": self._quality_combo.currentData() or "balanced",
            "quality_jpeg": self._image_quality_spin.value(),
            "max_dimension": self._size_combo.currentData() or 0,
            "pages": self._pages_edit.text().strip(),
            "dpi": self._dpi_combo.currentData() or 150,
            "gif_fps": self._gif_fps_spin.value(),
            "frame_fps": self._fps_spin.value(),
            "video_fps": self._fps_spin.value(),
            "frame_seconds": 2.0,
            "sheet": self._sheet_edit.text().strip(),
        }

    def _replan(self) -> None:
        terminal = [job for job in self._jobs if job.status.is_terminal]
        spec = self._current_spec()

        if not self._files or spec is None:
            self._jobs = terminal
            self._table.set_jobs(self._jobs)
            self._update_state()
            return

        options = self._collect_options()
        pending: list[Job] = []
        for group in plan_groups(spec, self._files):
            pending.append(Job.create(group, spec, options))

        self._jobs = terminal + pending
        self._table.set_jobs(self._jobs)
        self._update_state()

    # ------------------------------------------------------------------ 執行

    def _start(self) -> None:
        if self._running:
            return

        pending = [job for job in self._jobs if job.status is JobStatus.PENDING]
        if not pending:
            self._notify("沒有待轉換的工作。", "warning")
            return

        if any(job.target.needs_ffmpeg for job in pending) and not self._tools.available:
            self._notify(
                "找不到 FFmpeg，無法轉換影片或音訊。請到「設定」指定 FFmpeg 路徑。",
                "error",
            )
            return

        if any(job.target.needs_office for job in pending):
            office_tools = discover_office(self._settings.office_path)
            if not office_tools.available:
                self._notify(
                    "找不到 LibreOffice，無法轉換 Office 文件。請安裝 LibreOffice，"
                    "或到「設定」指定 soffice 路徑。",
                    "error",
                )
                return

        self._queue.apply_settings(self._settings)
        self._files.clear()
        if not self._queue.start_jobs(pending, self._tools):
            self._notify("無法開始轉換。", "error")
            return

        self._running = True
        self._run_jobs = pending
        self._overall.setValue(0)
        self._overall.setVisible(True)
        self._update_state()

    def _cancel_all(self) -> None:
        self._queue.cancel_all()
        self._notify("正在取消…", "warning")

    def _on_job_started(self, job: Job) -> None:
        self._table.update_job(job)

    def _on_job_progress(self, job: Job) -> None:
        self._table.update_job(job)
        self._update_overall()

    def _on_job_finished(self, job: Job) -> None:
        self._table.update_job(job)
        self._update_overall()

    def _on_all_finished(self) -> None:
        self._running = False
        self._overall.setVisible(False)
        self._update_state()
        self.historyChanged.emit()

        done = sum(1 for job in self._run_jobs if job.status is JobStatus.DONE)
        failed = sum(1 for job in self._run_jobs if job.status is JobStatus.FAILED)
        cancelled = sum(1 for job in self._run_jobs if job.status is JobStatus.CANCELLED)
        skipped = sum(1 for job in self._run_jobs if job.status is JobStatus.SKIPPED)

        parts = []
        if done:
            parts.append(f"完成 {done}")
        if failed:
            parts.append(f"失敗 {failed}")
        if cancelled:
            parts.append(f"取消 {cancelled}")
        if skipped:
            parts.append(f"略過 {skipped}")
        summary = "、".join(parts) or "沒有工作"

        if failed or (not done):
            kind = "error" if not done else "warning"
        elif cancelled or skipped:
            kind = "warning"
        else:
            kind = "success"
        self._notify(summary, kind)
        self._run_jobs = []

    def _update_overall(self) -> None:
        if not self._run_jobs:
            self._overall.setValue(0)
            return
        total = sum(job.progress for job in self._run_jobs)
        self._overall.setValue(int(total / len(self._run_jobs) * 1000))

    # ------------------------------------------------------------------ 狀態

    def _update_state(self) -> None:
        pending = [job for job in self._jobs if job.status is JobStatus.PENDING]

        self._start_button.setEnabled(bool(pending) and not self._running)
        self._start_button.setText(f"開始轉換（{len(pending)}）" if pending else "開始轉換")
        self._cancel_all_button.setVisible(self._running)
        self._add_button.setEnabled(not self._running)
        self._remove_button.setEnabled(bool(self._jobs) and not self._running)
        self._clear_button.setEnabled(bool(self._jobs) and not self._running)
        self._target_combo.setEnabled(bool(self._tokens) and not self._running)
        self._card.setEnabled(not self._running)

        self._stack.setCurrentIndex(1 if self._jobs else 0)
        self._update_summary()

    def _update_summary(self) -> None:
        total = len(self._jobs)
        if not total:
            self._summary.setText("尚未加入檔案")
            return
        counts: dict[JobStatus, int] = {}
        for job in self._jobs:
            counts[job.status] = counts.get(job.status, 0) + 1
        parts = [f"共 {total} 個工作"]
        for status, label in (
            (JobStatus.PENDING, "待轉換"),
            (JobStatus.RUNNING, "進行中"),
            (JobStatus.DONE, "完成"),
            (JobStatus.FAILED, "失敗"),
            (JobStatus.SKIPPED, "略過"),
        ):
            if counts.get(status):
                parts.append(f"{label} {counts[status]}")
        self._summary.setText(" · ".join(parts))

    def _update_output_edit(self) -> None:
        self._output_edit.setText(self._settings.output_dir or "")
        self._output_edit.setPlaceholderText("與來源檔案相同資料夾")

    # ------------------------------------------------------------------ 輸出設定

    def _choose_output_dir(self) -> None:
        start = self._settings.output_dir or self._last_dir or str(Path.home())
        directory = QFileDialog.getExistingDirectory(self, "選擇輸出資料夾", start)
        if directory:
            self._settings.output_dir = directory
            self._settings.save()
            self._update_output_edit()

    def _reset_output_dir(self) -> None:
        self._settings.output_dir = None
        self._settings.save()
        self._update_output_edit()

    # ------------------------------------------------------------------ 清單操作

    def _remove_selected(self) -> None:
        if self._running:
            return
        ids = set(self._table.selected_job_ids())
        if not ids:
            self._notify("請先選取要移除的工作。", "info")
            return

        removed_files: set[Path] = set()
        for job in self._jobs:
            if job.id in ids and job.status is JobStatus.PENDING:
                removed_files.update(job.sources)

        self._jobs = [job for job in self._jobs if job.id not in ids]
        self._files = [path for path in self._files if path not in removed_files]
        self._refresh_targets()
        self._replan()

    def _clear_all(self) -> None:
        if self._running:
            return
        self._files.clear()
        self._jobs.clear()
        self._table.clear_jobs()
        self._refresh_targets()
        self._update_state()

    def _open_job(self, job_id: str) -> None:
        job = next((item for item in self._jobs if item.id == job_id), None)
        if job is None or not job.outputs:
            return
        open_outputs(job.outputs)

    # ------------------------------------------------------------------ 拖放

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls() and not self._running:
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:
        paths = [Path(url.toLocalFile()) for url in event.mimeData().urls() if url.isLocalFile()]
        if paths:
            event.acceptProposedAction()
            self.add_paths(paths)

    # ------------------------------------------------------------------ 對外查詢

    @property
    def has_running_jobs(self) -> bool:
        return self._running
