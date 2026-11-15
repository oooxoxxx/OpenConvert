"""關於頁。"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from ... import __version__
from .. import icons

HOMEPAGE = "https://github.com/"


class AboutPage(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(26, 20, 26, 18)
        root.setSpacing(14)

        header = QHBoxLayout()
        logo = QLabel()
        logo.setPixmap(icons.app_icon().pixmap(56, 56))
        logo.setFixedSize(56, 56)

        column = QVBoxLayout()
        column.setSpacing(0)
        title = QLabel("OpenConvert")
        title.setObjectName("H1")
        subtitle = QLabel(f"版本 {__version__} · MIT License")
        subtitle.setObjectName("Muted")
        column.addWidget(title)
        column.addWidget(subtitle)

        header.addWidget(logo)
        header.addSpacing(12)
        header.addLayout(column)
        header.addStretch(1)
        root.addLayout(header)

        browser = QTextBrowser()
        browser.setOpenExternalLinks(False)
        browser.anchorClicked.connect(lambda url: QDesktopServices.openUrl(url))
        browser.setHtml(_ABOUT_HTML)
        root.addWidget(browser, 1)

        footer = QHBoxLayout()
        license_button = QPushButton("檢視授權條款")
        license_button.setObjectName("Ghost")
        license_button.clicked.connect(self._open_license)
        footer.addWidget(license_button)
        footer.addStretch(1)
        root.addLayout(footer)

    def _open_license(self) -> None:
        candidates = [
            Path(__file__).resolve().parents[3] / "LICENSE",
            Path.cwd() / "LICENSE",
        ]
        for candidate in candidates:
            if candidate.exists():
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(candidate)))
                return


_ABOUT_HTML = """
<div style="font-size:13px; line-height:1.7;">
  <p>
    <b>OpenConvert</b> 是一個免費、開源、跨平台的檔案轉換工具。
    它把成熟的開源引擎包進一個簡單的介面，
    讓一般使用者不需要記住命令列參數，也能完成轉檔。
  </p>

  <h3 style="font-size:14px; margin-top:18px;">核心原則</h3>
  <ul>
    <li>完全免費，沒有付費功能、沒有廣告。</li>
    <li>轉換全部在你的電腦上完成，檔案不會被上傳。</li>
    <li>支援離線使用。</li>
    <li>不會覆蓋你的原始檔案。</li>
    <li>原始碼公開，任何人都可以檢查與改進。</li>
  </ul>

  <h3 style="font-size:14px; margin-top:18px;">使用的開源元件</h3>
  <table cellpadding="4" style="border-collapse:collapse;">
    <tr><td><b>Python</b></td><td>應用程式語言</td><td>PSF License</td></tr>
    <tr><td><b>PySide6 / Qt</b></td><td>圖形介面</td><td>LGPL-3.0</td></tr>
    <tr><td><b>FFmpeg</b></td><td>影片與音訊編解碼（需自行安裝）</td><td>LGPL-2.1+ / GPL-2.0+</td></tr>
    <tr><td><b>Pillow</b></td><td>圖片讀寫</td><td>MIT-CMU</td></tr>
    <tr><td><b>pypdf</b></td><td>PDF 結構處理</td><td>BSD-3-Clause</td></tr>
    <tr><td><b>pypdfium2</b></td><td>PDF 點陣化（PDFium）</td><td>BSD-3-Clause / Apache-2.0</td></tr>
  </table>

  <h3 style="font-size:14px; margin-top:18px;">授權</h3>
  <p>
    OpenConvert 本身以 MIT License 釋出。你可以自由使用、修改與再散布，
    但需保留著作權聲明。隨附或引用之第三方元件各自適用其原授權條款。
  </p>

  <h3 style="font-size:14px; margin-top:18px;">隱私</h3>
  <p>
    本程式不含遙測、不含分析工具、不會連線到任何伺服器。
    唯一的網路行為是你主動點擊外部連結（例如 FFmpeg 下載頁）時，
    由系統瀏覽器開啟該網頁。
  </p>
</div>
"""
