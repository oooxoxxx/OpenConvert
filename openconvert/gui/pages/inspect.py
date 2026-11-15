"""檔案資訊頁：唯讀檢視媒體 / 圖片 / PDF / 電子書的中繼資料。"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStackedWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from ...core.errors import OpenConvertError
from ...core.ffmpeg import FFmpegTools
from ...core.inspect import FileSummary, describe
from ...core.kinds import SUPPORTED_EXTENSIONS
from .. import icons
from ..utils import reveal_in_folder
from ..widgets.drop_zone import DropZone


class InspectPage(QWidget):
    def __init__(
        self, tools: FFmpegTools, notify: Callable[[str, str], None], parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._tools = tools
        self._notify = notify
        self._summary: FileSummary | None = None
        self._last_dir = ""

        self.setAcceptDrops(True)
        self._build_ui()

    # ------------------------------------------------------------------ 版面

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(26, 20, 26, 18)
        root.setSpacing(14)

        header = QHBoxLayout()
        column = QVBoxLayout()
        column.setSpacing(2)
        title = QLabel("檔案資訊")
        title.setObjectName("H1")
        subtitle = QLabel("檢視影片、音訊、圖片、PDF 與電子書的詳細資訊，不會修改任何檔案。")
        subtitle.setObjectName("Muted")
        column.addWidget(title)
        column.addWidget(subtitle)
        header.addLayout(column)
        header.addStretch(1)

        self._pick_button = QPushButton("選擇檔案")
        self._pick_button.setIcon(icons.icon("inspect", "#4c8dff", 16))
        self._pick_button.clicked.connect(self._browse)
        header.addWidget(self._pick_button, 0, Qt.AlignmentFlag.AlignBottom)
        root.addLayout(header)

        self._drop = DropZone(
            "拖放檔案以檢視資訊",
            "支援影片、音訊、圖片、PDF、EPUB 與 CBZ。",
            icon_name="inspect",
            action_text="選擇檔案",
        )
        self._drop.setMinimumHeight(260)
        self._drop.filesDropped.connect(self._on_dropped)
        self._drop.browseRequested.connect(self._browse)

        self._viewer = QTextBrowser()
        self._viewer.setOpenExternalLinks(True)
        self._viewer.setFrameShape(QTextBrowser.Shape.NoFrame)

        self._stack = QStackedWidget()
        self._stack.addWidget(self._drop)
        self._stack.addWidget(self._viewer)
        root.addWidget(self._stack, 1)

        footer = QHBoxLayout()
        self._status = QLabel("尚未選擇檔案")
        self._status.setObjectName("Muted")
        self._reveal_button = QPushButton("在資料夾中顯示")
        self._reveal_button.setObjectName("Ghost")
        self._reveal_button.setEnabled(False)
        self._reveal_button.clicked.connect(self._reveal)
        footer.addWidget(self._status)
        footer.addStretch(1)
        footer.addWidget(self._reveal_button)
        root.addLayout(footer)

    # ------------------------------------------------------------------ 載入

    def set_tools(self, tools: FFmpegTools) -> None:
        self._tools = tools

    def _on_dropped(self, paths: list[Path]) -> None:
        if paths:
            self.load(paths[0])

    def _browse(self) -> None:
        patterns = " ".join(f"*.{ext}" for ext in sorted(SUPPORTED_EXTENSIONS))
        filename, _ = QFileDialog.getOpenFileName(
            self, "選擇檔案", self._last_dir, f"支援的檔案 ({patterns});;所有檔案 (*)"
        )
        if filename:
            self._last_dir = str(Path(filename).parent)
            self.load(Path(filename))

    def load(self, path: Path) -> None:
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            summary = describe(path, self._tools)
        except OpenConvertError as exc:
            self._notify(exc.user_message, "error")
            return
        except Exception as exc:  # 不讓檢視頁把整個程式拖垮
            self._notify(f"無法讀取檔案資訊：{exc}", "error")
            return
        finally:
            QApplication.restoreOverrideCursor()

        self._summary = summary
        self._viewer.setHtml(self._render(summary))
        self._stack.setCurrentIndex(1)
        self._status.setText(f"{summary.path.name} · {len(summary.rows)} 項資訊")
        self._reveal_button.setEnabled(True)

    def _reveal(self) -> None:
        if self._summary is not None:
            reveal_in_folder(self._summary.path)

    # ------------------------------------------------------------------ 繪製

    def _render(self, summary: FileSummary) -> str:
        rows = "".join(
            f"<tr>"
            f"<td style='padding:7px 18px 7px 0; color:#7b8597; white-space:nowrap;'>{_escape(row.label)}</td>"
            f"<td style='padding:7px 0; color:inherit;'>{_escape(row.value)}</td>"
            f"</tr>"
            for row in summary.rows
        )

        streams_html = ""
        if summary.streams:
            items = "".join(
                f"<tr>"
                f"<td style='padding:6px 24px 6px 0; color:#7b8597;'>#{stream.index}</td>"
                f"<td style='padding:6px 24px 6px 0;'>{_escape(_stream_type(stream.codec_type))}</td>"
                f"<td style='padding:6px 0;'>{_escape(stream.summary)}</td>"
                f"</tr>"
                for stream in summary.streams
            )
            streams_html = (
                "<h3 style='margin-top:22px; font-size:14px;'>串流</h3>"
                f"<table style='border-collapse:collapse;'>{items}</table>"
            )

        warnings = "".join(
            f"<p style='color:#c08a1e; margin:4px 0;'>⚠ {_escape(text)}</p>" for text in summary.warnings
        )

        return f"""
        <div style="font-size:13px;">
          <h2 style="margin:0 0 2px 0; font-size:17px;">{_escape(summary.path.name)}</h2>
          <p style="color:#7b8597; margin:0 0 16px 0; font-size:11px;">{_escape(str(summary.path))}</p>
          <table style="border-collapse:collapse;">{rows}</table>
          {streams_html}
          {warnings}
        </div>
        """


def _stream_type(codec_type: str) -> str:
    return {"video": "視訊", "audio": "音訊", "subtitle": "字幕", "data": "資料"}.get(
        codec_type, codec_type or "其他"
    )


def _escape(text: str) -> str:
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
