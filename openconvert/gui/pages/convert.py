"""轉換主頁。

設計原則：
- 格式選擇兩段式（類別 → 格式）加上搜尋，95 個目標不再靠捲動尋找。
- 選項面板依「目前會執行的轉換」動態重建，只顯示需要的欄位，不留空位。
- 輸出資料夾與「開始轉換」放在同一區，動線一氣呵成。
- 表格中每個工作可以個別改目標（覆寫全域設定），失敗可重試。
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDoubleSpinBox,
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

from ...core import modules
from ...core.ffmpeg import FFmpegTools
from ...core.ffmpeg import discover as discover_ffmpeg
from ...core.job import Job, JobStatus
from ...core.kinds import SUPPORTED_EXTENSIONS, extension_of
from ...core.office import discover as discover_office
from ...core.settings import Settings
from ...core.targets import TARGETS, TargetSpec, plan_groups, preferred_target, target_by_token
from ...runner import ConversionQueue
from .. import icons
from ..utils import open_outputs
from ..widgets.drop_zone import DropZone
from ..widgets.job_table import JobTable
from ..widgets.module_dialog import ModuleInstallDialog

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

ROTATE_OPTIONS: tuple[tuple[str, str], ...] = (
    ("順時針 90°", "90"),
    ("180°", "180"),
    ("順時針 270°", "270"),
    ("水平翻轉", "h"),
    ("垂直翻轉", "v"),
)

CROP_OPTIONS: tuple[tuple[str, str], ...] = (
    ("16:9", "16:9"),
    ("4:3", "4:3"),
    ("1:1（正方形）", "1:1"),
    ("3:2", "3:2"),
)

#: 各目標需要哪些選項欄位（出現在選項面板的順序也依此決定）
_OPTION_DEFAULTS: dict[str, object] = {
    "quality": "balanced",
    "max_dimension": 0,
    "image_quality": 90,
    "gif_fps": 12,
    "frame_fps": 30,
    "frame_seconds": 2.0,
    "rotate_mode": "90",
    "rotate_degrees": 90,
    "flip_axis": "h",
    "crop_ratio": "16:9",
    "split_start": "",
    "split_end": "",
    "pages": "",
    "dpi": 150,
    "pdf_password": "",
    "sheet": "",
}

_OPTION_LABELS: dict[str, str] = {
    "quality": "品質",
    "max_dimension": "最大尺寸",
    "image_quality": "影像品質",
    "gif_fps": "GIF 影格率",
    "frame_fps": "影格率",
    "frame_seconds": "每張停留",
    "rotate_mode": "旋轉／翻轉",
    "rotate_degrees": "旋轉角度",
    "flip_axis": "翻轉方向",
    "crop_ratio": "裁切比例",
    "split": "片段起訖",
    "pages": "頁碼範圍",
    "dpi": "PDF 解析度",
    "pdf_password": "PDF 密碼",
    "sheet": "工作表",
}


def _option_keys_for(spec: TargetSpec) -> list[str]:
    """這個目標需要哪些選項欄位。"""
    token = spec.token
    converter = spec.converter
    keys: list[str] = []
    if converter == "media" and token not in ("video-gif", "video-frames"):
        keys.append("quality")
    if converter in ("media", "image"):
        keys.append("max_dimension")
    if converter == "image" and token in ("jpg", "webp", "avif", "heic"):
        keys.append("image_quality")
    if token == "video-gif":
        keys.append("gif_fps")
    if token in ("video-frames", "images-video"):
        keys.append("frame_fps")
    if token == "images-video":
        keys.append("frame_seconds")
    if token == "video-rotate":
        keys.append("rotate_mode")
    if token == "img-rotate":
        keys.append("rotate_degrees")
    if token == "img-flip":
        keys.append("flip_axis")
    if token == "img-crop":
        keys.append("crop_ratio")
    if token == "video-split":
        keys.append("split")
    if token == "pdf-extract":
        keys.append("pages")
    if token in ("pdf-png", "pdf-jpg", "pdf-cbz"):
        keys.append("dpi")
    if token in ("pdf-encrypt", "pdf-decrypt"):
        keys.append("pdf_password")
    if converter == "data":
        keys.append("sheet")
    return keys


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
        self._file_targets: dict[Path, str | None] = {}
        self._explicit_files: set[Path] = set()
        self._jobs: list[Job] = []
        self._run_jobs: list[Job] = []
        self._tokens: list[str | None] = []
        self._option_widgets: dict[str, object] = {}
        self._global_token: str | None = None
        self._running = False
        self._last_dir = ""

        self.setAcceptDrops(True)
        self._build_ui()
        self._connect_queue()
        self._refresh_format_combo()
        self._update_state()

    # ------------------------------------------------------------------ 版面

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(26, 20, 26, 18)
        root.setSpacing(12)

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

        self._add_folder_button = QPushButton("加入資料夾")
        self._add_folder_button.setObjectName("Ghost")
        self._add_folder_button.clicked.connect(self._browse_folder)

        self._add_button = QPushButton("加入檔案")
        self._add_button.setIcon(icons.icon("plus", "#4c8dff", 16))
        self._add_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._add_button.clicked.connect(self._browse)

        header.addWidget(self._remove_button, 0, Qt.AlignmentFlag.AlignBottom)
        header.addWidget(self._clear_button, 0, Qt.AlignmentFlag.AlignBottom)
        header.addWidget(self._add_folder_button, 0, Qt.AlignmentFlag.AlignBottom)
        header.addSpacing(6)
        header.addWidget(self._add_button, 0, Qt.AlignmentFlag.AlignBottom)
        return header

    def _build_stack(self) -> QWidget:
        self._drop = DropZone(
            "拖放檔案或資料夾到這裡",
            "支援影片、音訊、圖片、PDF、電子書、文件、資料表、字幕、字型與壓縮。",
            icon_name="plus",
            action_text="選擇檔案",
        )
        self._drop.filesDropped.connect(self.add_paths)
        self._drop.browseRequested.connect(self._browse)

        self._table = JobTable()
        self._table.set_target_specs(list(TARGETS))
        self._table.cancelRequested.connect(self._queue.cancel)
        self._table.openRequested.connect(self._open_job)
        self._table.retryRequested.connect(self._retry_job)
        self._table.removeRequested.connect(self._remove_job)
        self._table.targetChanged.connect(self._on_job_target_changed)

        self._stack = QStackedWidget()
        self._stack.addWidget(self._drop)
        self._stack.addWidget(self._table)
        return self._stack

    def _build_options(self) -> QWidget:
        self._card = QFrame()
        self._card.setObjectName("Card")
        outer = QVBoxLayout(self._card)
        outer.setContentsMargins(18, 14, 18, 14)
        outer.setSpacing(10)

        picker = QGridLayout()
        picker.setHorizontalSpacing(12)
        picker.setVerticalSpacing(10)
        picker.setColumnStretch(1, 1)
        picker.setColumnStretch(3, 1)

        label_category = QLabel("類別")
        label_category.setObjectName("Muted")
        self._category_combo = QComboBox()
        self._category_combo.addItem("全部類別", None)
        for category in ("影片", "音訊", "圖片", "PDF", "電子書", "文件", "資料", "字幕", "字型", "壓縮"):
            self._category_combo.addItem(category, category)
        self._category_combo.currentIndexChanged.connect(self._refresh_format_combo)

        label_search = QLabel("搜尋")
        label_search.setObjectName("Muted")
        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText("輸入文字過濾格式，例如 pdf、word")
        self._search_edit.setClearButtonEnabled(True)
        self._search_edit.textChanged.connect(self._refresh_format_combo)

        picker.addWidget(label_category, 0, 0)
        picker.addWidget(self._category_combo, 0, 1)
        picker.addWidget(label_search, 0, 2)
        picker.addWidget(self._search_edit, 0, 3)

        label_target = QLabel("目標格式")
        self._target_combo = QComboBox()
        self._target_combo.setMinimumWidth(200)
        self._target_combo.currentIndexChanged.connect(self._on_format_changed)
        picker.addWidget(label_target, 1, 0)
        picker.addWidget(self._target_combo, 1, 1, 1, 3)

        outer.addLayout(picker)

        self._target_desc = QLabel(" ")
        self._target_desc.setObjectName("Muted")
        self._target_desc.setWordWrap(True)
        outer.addWidget(self._target_desc)

        self._options_host = QWidget()
        self._options_grid = QGridLayout(self._options_host)
        self._options_grid.setContentsMargins(0, 0, 0, 0)
        self._options_grid.setHorizontalSpacing(12)
        self._options_grid.setVerticalSpacing(10)
        self._options_grid.setColumnMinimumWidth(0, 92)
        self._options_grid.setColumnMinimumWidth(2, 92)
        self._options_grid.setColumnStretch(1, 1)
        self._options_grid.setColumnStretch(3, 1)
        outer.addWidget(self._options_host)
        outer.addStretch(1)

        return self._card

    def _build_footer(self) -> QVBoxLayout:
        footer = QVBoxLayout()
        footer.setSpacing(8)

        row1 = QHBoxLayout()
        row1.setSpacing(12)
        self._summary = QLabel("尚未加入檔案")
        self._summary.setObjectName("Muted")
        self._overall = QProgressBar()
        self._overall.setRange(0, 1000)
        self._overall.setValue(0)
        self._overall.setTextVisible(False)
        self._overall.setFixedHeight(8)
        self._overall.setFixedWidth(200)
        self._overall.setVisible(False)
        row1.addWidget(self._summary)
        row1.addStretch(1)
        row1.addWidget(self._overall)
        footer.addLayout(row1)

        row2 = QHBoxLayout()
        row2.setSpacing(8)
        label_output = QLabel("輸出資料夾")
        label_output.setObjectName("Muted")
        self._output_edit = QLineEdit()
        self._output_edit.setPlaceholderText("與來源檔案相同資料夾")
        self._output_edit.setReadOnly(True)
        output_browse = QPushButton("選擇…")
        output_browse.clicked.connect(self._choose_output_dir)
        output_reset = QPushButton("還原")
        output_reset.setObjectName("Ghost")
        output_reset.clicked.connect(self._reset_output_dir)

        self._cancel_all_button = QPushButton("全部取消")
        self._cancel_all_button.setObjectName("Danger")
        self._cancel_all_button.setVisible(False)
        self._cancel_all_button.clicked.connect(self._cancel_all)

        self._start_button = QPushButton("開始轉換")
        self._start_button.setObjectName("Primary")
        self._start_button.setMinimumWidth(140)
        self._start_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._start_button.clicked.connect(self._start)

        row2.addWidget(label_output)
        row2.addWidget(self._output_edit, 1)
        row2.addWidget(output_browse)
        row2.addWidget(output_reset)
        row2.addSpacing(12)
        row2.addWidget(self._cancel_all_button)
        row2.addWidget(self._start_button)
        footer.addLayout(row2)
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
        for path in added:
            self._file_targets[path] = None  # 跟隨全域設定
        self._auto_select_format()
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

    def _browse_folder(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "選擇要加入的資料夾", self._last_dir)
        if directory:
            self._last_dir = directory
            self.add_paths([Path(directory)])

    # ------------------------------------------------------------------ 格式選擇

    def _auto_select_format(self) -> None:
        """加入檔案後，依檔案類型與上次使用習慣挑選預設格式與類別。"""
        spec = preferred_target(self._files, self._settings.last_format)
        if spec is None:
            return
        index = self._category_combo.findData(spec.category)
        if index >= 0:
            self._category_combo.blockSignals(True)
            self._category_combo.setCurrentIndex(index)
            self._category_combo.blockSignals(False)
        self._refresh_format_combo()
        self._select_format_token(spec.token)

    def _refresh_format_combo(self) -> None:
        """依類別與搜尋文字重建格式清單；上次使用的格式固定排在最上面。"""
        category = self._category_combo.currentData()
        query = self._search_edit.text().strip().lower()

        self._target_combo.blockSignals(True)
        self._target_combo.clear()
        self._tokens = []

        candidates = [
            spec
            for spec in TARGETS
            if (category is None or spec.category == category)
            and (not query or query in spec.label.lower() or query in spec.token.lower())
        ]

        last = self._settings.last_format
        if last and any(spec.token == last for spec in candidates):
            last_spec = target_by_token(last)
            if last_spec is not None:
                self._target_combo.addItem(f"{last_spec.label}（上次使用）", last_spec.token)
                self._tokens.append(last_spec.token)

        for spec in candidates:
            group_hint = "（合併）" if spec.group_kinds else ""
            self._target_combo.addItem(f"{spec.label}{group_hint}", spec.token)
            self._tokens.append(spec.token)

        if not self._tokens:
            self._target_combo.addItem("沒有符合的格式", None)
            self._tokens.append(None)

        selected = self._global_token or last
        index = self._tokens.index(selected) if selected in self._tokens else 0
        if self._tokens[index] is None:
            index = self._first_real_index()
        self._target_combo.setCurrentIndex(index)
        self._target_combo.blockSignals(False)
        self._global_token = self._current_token()
        self._update_target_tooltip()
        self._replan()

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

    def _select_format_token(self, token: str) -> None:
        index = self._tokens.index(token) if token in self._tokens else -1
        if index >= 0:
            self._target_combo.setCurrentIndex(index)

    def _on_format_changed(self, _index: int) -> None:
        token = self._current_token()
        if token is None:
            return
        self._global_token = token
        if token != self._settings.last_format:
            self._settings.last_format = token
            self._settings.save()
        self._update_target_tooltip()
        self._replan()

    def _update_target_tooltip(self) -> None:
        spec = self._current_spec()
        text = " "
        if spec is not None:
            text = spec.description or " "
            if spec.group_kinds:
                text += "\n此格式會把符合條件的檔案合併成一個輸出。"
        self._target_desc.setText(text)
        self._target_combo.setToolTip(text)

    # ------------------------------------------------------------------ 選項面板

    def _rebuild_options(self, specs: list[TargetSpec]) -> None:
        """依「目前會執行的轉換」重建選項面板，只顯示需要的欄位。"""
        while self._options_grid.count():
            item = self._options_grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        self._option_widgets = {}
        keys: list[str] = []
        for spec in specs:
            for key in _option_keys_for(spec):
                if key not in keys:
                    keys.append(key)

        row = 0
        for key in keys:
            label_text = _OPTION_LABELS[key]
            label = QLabel(label_text)
            label.setObjectName("Muted")
            label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            row += 1
            if key == "quality":
                widget = self._make_combo(QUALITY_OPTIONS, "balanced")
            elif key == "max_dimension":
                widget = self._make_combo(SIZE_OPTIONS, 0)
            elif key == "image_quality":
                widget = self._make_spin(1, 100, 90, " %")
            elif key == "gif_fps":
                widget = self._make_spin(5, 30, 12, " fps")
            elif key == "frame_fps":
                widget = self._make_spin(1, 60, 30, " fps")
            elif key == "frame_seconds":
                widget = self._make_double_spin(0.1, 60.0, 2.0, " 秒")
            elif key == "rotate_mode":
                widget = self._make_combo(ROTATE_OPTIONS, "90")
            elif key == "rotate_degrees":
                widget = self._make_combo((("順時針 90°", 90), ("180°", 180), ("順時針 270°", 270)), 90)
            elif key == "flip_axis":
                widget = self._make_combo((("水平翻轉", "h"), ("垂直翻轉", "v")), "h")
            elif key == "crop_ratio":
                widget = self._make_combo(CROP_OPTIONS, "16:9")
            elif key == "split":
                start = QLineEdit()
                start.setPlaceholderText("開始（秒或 1:30）")
                end = QLineEdit()
                end.setPlaceholderText("結束（秒或 1:30）")
                self._options_grid.addWidget(label, row, 0)
                self._options_grid.addWidget(start, row, 1)
                self._options_grid.addWidget(end, row, 2, 1, 2)
                self._option_widgets[key] = (start, end)
                continue
            elif key == "pages":
                widget = QLineEdit()
                widget.setPlaceholderText("例如 1-3,7（留空表示全部頁面）")
            elif key == "dpi":
                widget = self._make_combo(DPI_OPTIONS, 150)
            elif key == "pdf_password":
                widget = QLineEdit()
                widget.setEchoMode(QLineEdit.EchoMode.Password)
                widget.setPlaceholderText("輸入密碼")
            elif key == "sheet":
                widget = QLineEdit()
                widget.setPlaceholderText("工作表名稱（留空表示第一個工作表）")
            else:  # pragma: no cover - 選項定義已窮舉
                continue

            self._options_grid.addWidget(label, row, 0)
            self._options_grid.addWidget(widget, row, 1, 1, 3)
            self._option_widgets[key] = widget

        if not keys:
            empty = QLabel("此格式沒有額外選項。")
            empty.setObjectName("Muted")
            self._options_grid.addWidget(empty, 0, 0)

    def _make_combo(self, options, default) -> QComboBox:
        combo = QComboBox()
        for label, value in options:
            combo.addItem(label, value)
        index = combo.findData(default)
        combo.setCurrentIndex(max(0, index))
        return combo

    def _make_spin(self, low: int, high: int, value: int, suffix: str) -> QSpinBox:
        spin = QSpinBox()
        spin.setRange(low, high)
        spin.setValue(value)
        spin.setSuffix(suffix)
        return spin

    def _make_double_spin(self, low: float, high: float, value: float, suffix: str) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(low, high)
        spin.setDecimals(1)
        spin.setValue(value)
        spin.setSuffix(suffix)
        return spin

    def _collect_options(self) -> dict:
        options = dict(_OPTION_DEFAULTS)
        widgets = self._option_widgets
        if "quality" in widgets:
            options["quality"] = widgets["quality"].currentData() or "balanced"
        if "max_dimension" in widgets:
            options["max_dimension"] = widgets["max_dimension"].currentData() or 0
        if "image_quality" in widgets:
            options["image_quality"] = widgets["image_quality"].value()
        if "gif_fps" in widgets:
            options["gif_fps"] = widgets["gif_fps"].value()
        if "frame_fps" in widgets:
            options["frame_fps"] = widgets["frame_fps"].value()
        if "frame_seconds" in widgets:
            options["frame_seconds"] = widgets["frame_seconds"].value()
        if "rotate_mode" in widgets:
            options["rotate_mode"] = widgets["rotate_mode"].currentData() or "90"
        if "rotate_degrees" in widgets:
            options["rotate_degrees"] = widgets["rotate_degrees"].currentData() or 90
        if "flip_axis" in widgets:
            options["flip_axis"] = widgets["flip_axis"].currentData() or "h"
        if "crop_ratio" in widgets:
            options["crop_ratio"] = widgets["crop_ratio"].currentData() or "16:9"
        if "split" in widgets:
            start, end = widgets["split"]
            options["split_start"] = start.text().strip()
            options["split_end"] = end.text().strip()
        if "pages" in widgets:
            options["pages"] = widgets["pages"].text().strip()
        if "dpi" in widgets:
            options["dpi"] = widgets["dpi"].currentData() or 150
        if "pdf_password" in widgets:
            options["pdf_password"] = widgets["pdf_password"].text()
        if "sheet" in widgets:
            options["sheet"] = widgets["sheet"].text().strip()
        return options

    # ------------------------------------------------------------------ 規劃

    def _effective_token(self, path: Path) -> str | None:
        return self._file_targets.get(path) or self._global_token

    def _replan(self) -> None:
        if self._running:
            return

        terminal = [job for job in self._jobs if job.status.is_terminal]

        tokens: list[str] = []
        for path in self._files:
            token = self._effective_token(path)
            if token and token not in tokens:
                tokens.append(token)

        specs = [target_by_token(token) for token in tokens if target_by_token(token) is not None]
        self._rebuild_options([spec for spec in specs if spec is not None])
        options = self._collect_options()

        pending: list[Job] = []
        for token in tokens:
            spec = target_by_token(token)
            if spec is None:
                continue
            files = [path for path in self._files if self._effective_token(path) == token]
            for group in plan_groups(spec, files):
                job = Job.create(group, spec, options)
                if spec.group_kinds:
                    eligible = sum(1 for source in group if spec.is_group(source))
                    if eligible < spec.group_min:
                        job.skip(f"需要至少 {spec.group_min} 個符合的檔案（目前 {eligible} 個）")
                pending.append(job)

        self._jobs = terminal + pending
        self._table.set_jobs(self._jobs)
        self._update_state()

    def _on_job_target_changed(self, job_id: str, token: str) -> None:
        if self._running:
            self._notify("轉換進行中，無法變更目標。", "warning")
            return
        job = next((item for item in self._jobs if item.id == job_id), None)
        if job is None:
            return
        for source in job.sources:
            self._file_targets[source] = token
            self._explicit_files.add(source)
        self._replan()

    # ------------------------------------------------------------------ 執行

    def _start(self) -> None:
        if self._running:
            return

        pending = [job for job in self._jobs if job.status is JobStatus.PENDING]
        if not pending:
            self._notify("沒有待轉換的工作。", "warning")
            return

        if not self._ensure_modules(pending):
            return

        options = self._collect_options()
        for job in pending:
            job.options.update(options)

        self._queue.apply_settings(self._settings)
        self._files.clear()
        for job in pending:
            for source in job.sources:
                self._file_targets.pop(source, None)
                self._explicit_files.discard(source)
        if not self._queue.start_jobs(pending, self._tools):
            self._notify("無法開始轉換。", "error")
            return

        self._running = True
        self._run_jobs = pending
        self._overall.setValue(0)
        self._overall.setVisible(True)
        self._update_state()

    def _ensure_modules(self, pending: list[Job]) -> bool:
        """需要引擎但尚未安裝時，詢問使用者要不要現在下載。"""
        if any(job.target.needs_ffmpeg for job in pending) and not self._tools.available:
            if not self._offer_module("ffmpeg"):
                return False
            self._tools = discover_ffmpeg()
            if not self._tools.available:
                return False

        if any(job.target.needs_office for job in pending):
            office_tools = discover_office(self._settings.office_path)
            if not office_tools.available and not self._offer_module("libreoffice"):
                return False
        return True

    def _offer_module(self, module_id: str) -> bool:
        spec = modules.get_module(module_id)
        if spec is None:
            label = "FFmpeg" if module_id == "ffmpeg" else "LibreOffice"
            self._notify(
                f"找不到 {label}，這個平台也沒有提供下載模組。請自行安裝，或到「設定」指定路徑。",
                "error",
            )
            return False

        dialog = ModuleInstallDialog(module_id, self)
        accepted = dialog.exec() == QDialog.DialogCode.Accepted
        if accepted:
            self._notify(f"{spec.label} 模組已安裝，繼續轉換。", "success")
        return accepted

    def _cancel_all(self) -> None:
        self._queue.cancel_all()
        self._notify("正在取消…", "warning")

    def _retry_job(self, job_id: str) -> None:
        job = next((item for item in self._jobs if item.id == job_id), None)
        if job is None or job.status is not JobStatus.FAILED:
            return
        if self._running or self._queue.is_running:
            self._notify("轉換進行中，請等待完成後再重試。", "warning")
            return

        new_job = Job.create(job.sources, job.target, job.options)
        self._jobs = [item for item in self._jobs if item.id != job_id] + [new_job]
        self._table.set_jobs(self._jobs)
        self._running = True
        self._run_jobs = [new_job]
        self._overall.setValue(0)
        self._overall.setVisible(True)
        self._update_state()
        if not self._queue.start_jobs([new_job], self._tools):
            self._running = False
            self._notify("無法開始轉換。", "error")

    def _remove_job(self, job_id: str) -> None:
        if self._running:
            self._notify("轉換進行中，無法移除工作。", "warning")
            return
        job = next((item for item in self._jobs if item.id == job_id), None)
        if job is None:
            return
        self._forget_files(job.sources)
        self._jobs = [item for item in self._jobs if item.id != job_id]
        self._table.set_jobs(self._jobs)
        self._refresh_format_combo()
        self._replan()

    def _forget_files(self, sources: list[Path]) -> None:
        for source in sources:
            self._files = [path for path in self._files if path.resolve() != Path(source).resolve()]
            self._file_targets.pop(source, None)
            self._explicit_files.discard(source)

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
        self._add_folder_button.setEnabled(not self._running)
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
            if job.id in ids and job.status is not JobStatus.RUNNING:
                removed_files.update(job.sources)

        self._jobs = [job for job in self._jobs if job.id not in ids]
        self._forget_files(list(removed_files))
        self._refresh_format_combo()
        self._replan()

    def _clear_all(self) -> None:
        if self._running:
            return
        self._files.clear()
        self._file_targets.clear()
        self._explicit_files.clear()
        self._jobs.clear()
        self._table.clear_jobs()
        self._refresh_format_combo()
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
