"""設定頁。"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ...core.ffmpeg import FFmpegTools, discover, version_of
from ...core.office import discover as discover_office
from ...core.office import version_of as office_version
from ...core.resources import tools_dir
from ...core.settings import Settings, config_dir
from ..utils import open_path
from ..widgets.toast import Toast

THEME_LABELS: tuple[tuple[str, str], ...] = (
    ("跟隨系統", "system"),
    ("深色", "dark"),
    ("淺色", "light"),
)

FFMPEG_DOWNLOAD_URL = "https://ffmpeg.org/download.html"
LIBREOFFICE_DOWNLOAD_URL = "https://www.libreoffice.org/download/download/"


class SettingsPage(QWidget):
    settingsChanged = Signal(object)  # Settings
    toolsChanged = Signal(object)  # FFmpegTools

    def __init__(
        self,
        settings: Settings,
        tools: FFmpegTools,
        notify: Callable[[str, str], None],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._settings = settings
        self._tools = tools
        self._notify = notify
        self._loading = True
        self._build_ui()
        self._load_values()
        self._loading = False

    # ------------------------------------------------------------------ 版面

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(26, 20, 26, 18)
        outer.setSpacing(12)

        title = QLabel("設定")
        title.setObjectName("H1")
        subtitle = QLabel("所有設定都儲存在這台電腦上。")
        subtitle.setObjectName("Muted")
        outer.addWidget(title)
        outer.addWidget(subtitle)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.viewport().setAutoFillBackground(False)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        container = QWidget()
        column = QVBoxLayout(container)
        column.setContentsMargins(0, 8, 6, 8)
        column.setSpacing(12)

        column.addWidget(self._appearance_card())
        column.addWidget(self._behaviour_card())
        column.addWidget(self._output_card())
        column.addWidget(self._ffmpeg_card())
        column.addWidget(self._office_card())
        column.addWidget(self._privacy_card())
        column.addStretch(1)

        scroll.setWidget(container)
        outer.addWidget(scroll, 1)

    def _card(self, title: str, subtitle: str = "") -> tuple[QFrame, QVBoxLayout]:
        frame = QFrame()
        frame.setObjectName("Card")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)

        heading = QLabel(title)
        heading.setObjectName("H2")
        layout.addWidget(heading)
        if subtitle:
            hint = QLabel(subtitle)
            hint.setObjectName("Muted")
            hint.setWordWrap(True)
            layout.addWidget(hint)
        return frame, layout

    def _row(self, label: str, widget: QWidget, hint: str = "") -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(3)
        caption = QLabel(label)
        caption.setObjectName("Muted")
        layout.addWidget(caption)
        layout.addWidget(widget)
        if hint:
            note = QLabel(hint)
            note.setObjectName("Muted")
            note.setWordWrap(True)
            layout.addWidget(note)
        return container

    # ------------------------------------------------------------------ 卡片

    def _appearance_card(self) -> QWidget:
        frame, layout = self._card("外觀", "主題會立即套用。")
        self._theme_combo = QComboBox()
        for label, value in THEME_LABELS:
            self._theme_combo.addItem(label, value)
        self._theme_combo.currentIndexChanged.connect(self._save)
        layout.addWidget(self._row("主題", self._theme_combo))
        return frame

    def _behaviour_card(self) -> QWidget:
        frame, layout = self._card("轉換行為")
        self._concurrency = QSpinBox()
        self._concurrency.setRange(1, 8)
        self._concurrency.setSuffix(" 個")
        self._concurrency.valueChanged.connect(self._save)
        layout.addWidget(
            self._row(
                "同時轉換數量",
                self._concurrency,
                "數值越高速度可能越快，但也更耗用 CPU 與記憶體。一般建議 2。",
            )
        )

        self._overwrite = QCheckBox("允許覆蓋同名的輸出檔案")
        self._overwrite.setToolTip("無論是否開啟，都不會覆蓋原始檔案。")
        self._overwrite.stateChanged.connect(self._save)
        layout.addWidget(self._overwrite)
        return frame

    def _output_card(self) -> QWidget:
        frame, layout = self._card("輸出位置", "留空表示把結果放在來源檔案旁邊。")

        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(8)
        self._output_edit = QLineEdit()
        self._output_edit.setReadOnly(True)
        self._output_edit.setPlaceholderText("與來源檔案相同資料夾")
        choose = QPushButton("選擇…")
        choose.clicked.connect(self._choose_output)
        reset = QPushButton("還原")
        reset.setObjectName("Ghost")
        reset.clicked.connect(self._reset_output)
        row_layout.addWidget(self._output_edit, 1)
        row_layout.addWidget(choose)
        row_layout.addWidget(reset)
        layout.addWidget(row)

        self._open_output_button = QPushButton("開啟輸出資料夾")
        self._open_output_button.setObjectName("Ghost")
        self._open_output_button.clicked.connect(self._open_output_dir)
        layout.addWidget(self._open_output_button, 0, Qt.AlignmentFlag.AlignLeft)
        return frame

    def _ffmpeg_card(self) -> QWidget:
        frame, layout = self._card(
            "FFmpeg（影片與音訊）",
            "OpenConvert 不內建 FFmpeg。若系統中找不到，圖片、PDF 與電子書功能仍可正常使用。",
        )

        self._ffmpeg_status = QLabel()
        self._ffmpeg_status.setWordWrap(True)
        layout.addWidget(self._ffmpeg_status)

        status_row = QHBoxLayout()
        recheck = QPushButton("重新偵測")
        recheck.setObjectName("Ghost")
        recheck.clicked.connect(self._recheck)
        download = QPushButton("開啟 FFmpeg 下載頁")
        download.setObjectName("Ghost")
        download.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(FFMPEG_DOWNLOAD_URL)))
        tools_button = QPushButton("開啟工具資料夾")
        tools_button.setObjectName("Ghost")
        tools_button.clicked.connect(self._open_tools_dir)
        status_row.addWidget(recheck)
        status_row.addWidget(download)
        status_row.addWidget(tools_button)
        status_row.addStretch(1)
        layout.addLayout(status_row)

        self._ffmpeg_edit = QLineEdit()
        self._ffmpeg_edit.setPlaceholderText("自動偵測（可留空）")
        self._ffmpeg_edit.editingFinished.connect(self._save)
        layout.addWidget(self._row("FFmpeg 執行檔路徑", self._ffmpeg_edit))

        self._ffprobe_edit = QLineEdit()
        self._ffprobe_edit.setPlaceholderText("自動偵測（可留空）")
        self._ffprobe_edit.editingFinished.connect(self._save)
        layout.addWidget(self._row("FFprobe 執行檔路徑", self._ffprobe_edit))

        browse_row = QHBoxLayout()
        pick_ffmpeg = QPushButton("選擇 FFmpeg…")
        pick_ffmpeg.setObjectName("Ghost")
        pick_ffmpeg.clicked.connect(lambda: self._browse_binary(self._ffmpeg_edit))
        pick_ffprobe = QPushButton("選擇 FFprobe…")
        pick_ffprobe.setObjectName("Ghost")
        pick_ffprobe.clicked.connect(lambda: self._browse_binary(self._ffprobe_edit))
        browse_row.addWidget(pick_ffmpeg)
        browse_row.addWidget(pick_ffprobe)
        browse_row.addStretch(1)
        layout.addLayout(browse_row)
        return frame

    def _office_card(self) -> QWidget:
        frame, layout = self._card(
            "LibreOffice（Office 文件）",
            "OpenConvert 不內建 LibreOffice。若系統中找不到，其他格式仍可正常使用。",
        )

        self._office_status = QLabel()
        self._office_status.setWordWrap(True)
        layout.addWidget(self._office_status)

        status_row = QHBoxLayout()
        recheck = QPushButton("重新偵測")
        recheck.setObjectName("Ghost")
        recheck.clicked.connect(self._recheck_office)
        download = QPushButton("開啟 LibreOffice 下載頁")
        download.setObjectName("Ghost")
        download.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(LIBREOFFICE_DOWNLOAD_URL)))
        status_row.addWidget(recheck)
        status_row.addWidget(download)
        status_row.addStretch(1)
        layout.addLayout(status_row)

        self._office_edit = QLineEdit()
        self._office_edit.setPlaceholderText("自動偵測（可留空）")
        self._office_edit.editingFinished.connect(self._save)
        layout.addWidget(self._row("soffice 執行檔路徑", self._office_edit))

        browse_row = QHBoxLayout()
        pick = QPushButton("選擇 soffice…")
        pick.setObjectName("Ghost")
        pick.clicked.connect(lambda: self._browse_binary(self._office_edit))
        browse_row.addWidget(pick)
        browse_row.addStretch(1)
        layout.addLayout(browse_row)
        return frame

    def _privacy_card(self) -> QWidget:
        frame, layout = self._card("隱私與紀錄", "OpenConvert 不會上傳你的檔案，也沒有任何遙測。")

        self._keep_history = QCheckBox("保留轉換紀錄（只存在本機）")
        self._keep_history.stateChanged.connect(self._save)
        layout.addWidget(self._keep_history)

        self._play_sound = QCheckBox("轉換完成時發出提示音")
        self._play_sound.stateChanged.connect(self._save)
        layout.addWidget(self._play_sound)

        buttons = QHBoxLayout()
        open_config = QPushButton("開啟設定資料夾")
        open_config.setObjectName("Ghost")
        open_config.clicked.connect(lambda: open_path(config_dir()))
        buttons.addWidget(open_config)
        buttons.addStretch(1)
        layout.addLayout(buttons)
        return frame

    # ------------------------------------------------------------------ 載入

    def _load_values(self) -> None:
        settings = self._settings
        index = self._theme_combo.findData(settings.theme)
        self._theme_combo.setCurrentIndex(max(0, index))
        self._concurrency.setValue(settings.concurrency)
        self._overwrite.setChecked(settings.overwrite)
        self._output_edit.setText(settings.output_dir or "")
        self._ffmpeg_edit.setText(settings.ffmpeg_path or "")
        self._ffprobe_edit.setText(settings.ffprobe_path or "")
        self._office_edit.setText(settings.office_path or "")
        self._keep_history.setChecked(settings.keep_history)
        self._play_sound.setChecked(settings.play_sound)
        self._update_status()

    def refresh_from_settings(self, settings: Settings) -> None:
        self._settings = settings
        self._loading = True
        self._load_values()
        self._loading = False

    def set_tools(self, tools: FFmpegTools) -> None:
        self._tools = tools
        self._update_status()

    def _update_status(self) -> None:
        if self._tools.available:
            version = version_of(self._tools.ffmpeg) or "FFmpeg"
            short = version.split(" Copyright")[0]
            color = "#3fb950"
            origin = "（內附）" if self._tools.bundled else ""
            self._ffmpeg_status.setText(f"● 已找到 FFmpeg{origin}　{short}")
        else:
            color = "#d29922"
            self._ffmpeg_status.setText("● 找不到 FFmpeg。影片與音訊轉換目前無法使用。")
        self._ffmpeg_status.setStyleSheet(f"color: {color}; font-size: 12px;")
        self._update_office_status()

    def _update_office_status(self) -> None:
        tools = discover_office(self._settings.office_path)
        if tools.available:
            version = office_version(tools.soffice) or "LibreOffice"
            short = version.split(" Copyright")[0]
            color = "#3fb950"
            origin = "（內附）" if tools.bundled else ""
            self._office_status.setText(f"● 已找到 LibreOffice{origin}　{short}")
        else:
            color = "#d29922"
            self._office_status.setText("● 找不到 LibreOffice。Office 文件轉換目前無法使用。")
        self._office_status.setStyleSheet(f"color: {color}; font-size: 12px;")

    # ------------------------------------------------------------------ 儲存

    def _save(self, *_args) -> None:
        if self._loading:
            return
        settings = self._settings
        settings.theme = self._theme_combo.currentData() or "system"
        settings.concurrency = self._concurrency.value()
        settings.overwrite = self._overwrite.isChecked()
        settings.ffmpeg_path = self._ffmpeg_edit.text().strip() or None
        settings.ffprobe_path = self._ffprobe_edit.text().strip() or None
        settings.office_path = self._office_edit.text().strip() or None
        settings.keep_history = self._keep_history.isChecked()
        settings.play_sound = self._play_sound.isChecked()
        settings.save()

        self._tools = discover(settings.ffmpeg_path, settings.ffprobe_path)
        self._update_status()
        self.toolsChanged.emit(self._tools)
        self.settingsChanged.emit(settings)

    # ------------------------------------------------------------------ 動作

    def _choose_output(self) -> None:
        directory = QFileDialog.getExistingDirectory(
            self, "選擇輸出資料夾", self._settings.output_dir or str(Path.home())
        )
        if directory:
            self._settings.output_dir = directory
            self._settings.save()
            self._output_edit.setText(directory)
            self.settingsChanged.emit(self._settings)

    def _reset_output(self) -> None:
        self._settings.output_dir = None
        self._settings.save()
        self._output_edit.clear()
        self.settingsChanged.emit(self._settings)

    def _open_output_dir(self) -> None:
        target = self._settings.output_dir
        if not target:
            self._notify("目前沒有設定輸出資料夾，輸出會放在來源檔案旁邊。", "info")
            return
        open_path(target)

    def _browse_binary(self, target: QLineEdit) -> None:
        filename, _ = QFileDialog.getOpenFileName(self, "選擇執行檔", "", "執行檔 (*.exe);;所有檔案 (*)")
        if filename:
            target.setText(filename)
            self._save()

    def _recheck(self) -> None:
        self._tools = discover(self._settings.ffmpeg_path, self._settings.ffprobe_path)
        self._update_status()
        self.toolsChanged.emit(self._tools)
        if self._tools.available:
            Toast.show_message(self.window(), "已找到 FFmpeg。", "success")
        else:
            Toast.show_message(self.window(), "仍找不到 FFmpeg。", "warning")

    def _recheck_office(self) -> None:
        self._update_office_status()
        tools = discover_office(self._settings.office_path)
        if tools.available:
            Toast.show_message(self.window(), "已找到 LibreOffice。", "success")
        else:
            Toast.show_message(self.window(), "仍找不到 LibreOffice。", "warning")

    def _open_tools_dir(self) -> None:
        directory = tools_dir()
        directory.mkdir(parents=True, exist_ok=True)
        open_path(directory)
