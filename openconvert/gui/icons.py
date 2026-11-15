"""以內嵌 SVG 產生圖示，不需額外圖檔或資源編譯。"""

from __future__ import annotations

from functools import lru_cache

from PySide6.QtCore import QByteArray, QSize, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

_TEMPLATE = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
    'stroke="{color}" stroke-width="{width}" stroke-linecap="round" '
    'stroke-linejoin="round">{body}</svg>'
)

_PATHS: dict[str, str] = {
    "convert": '<path d="M4 8h13"/><polyline points="13 4 17 8 13 12"/>'
    '<path d="M20 16H7"/><polyline points="11 12 7 16 11 20"/>',
    "inspect": '<circle cx="11" cy="11" r="7"/><line x1="16.5" y1="16.5" x2="21" y2="21"/>',
    "history": '<circle cx="12" cy="12" r="9"/><polyline points="12 7 12 12 16 14"/>',
    "settings": '<line x1="4" y1="8" x2="20" y2="8"/><circle cx="9" cy="8" r="2.4"/>'
    '<line x1="4" y1="16" x2="20" y2="16"/><circle cx="15" cy="16" r="2.4"/>',
    "about": '<circle cx="12" cy="12" r="9"/><line x1="12" y1="11" x2="12" y2="16"/>'
    '<circle cx="12" cy="7.8" r="0.9" fill="{color}" stroke="none"/>',
    "plus": '<line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>',
    "trash": '<polyline points="4 7 20 7"/><path d="M9 7V4.5h6V7"/>'
    '<path d="M6 7l1 13h10l1-13"/><line x1="10" y1="11" x2="10" y2="16"/>'
    '<line x1="14" y1="11" x2="14" y2="16"/>',
    "play": '<path d="M7 4.5l12 7.5-12 7.5z"/>',
    "stop": '<rect x="6" y="6" width="12" height="12" rx="2"/>',
    "folder": '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
    "moon": '<path d="M20 14.5A8.5 8.5 0 0 1 9.5 4a8.5 8.5 0 1 0 10.5 10.5z"/>',
    "sun": '<circle cx="12" cy="12" r="4"/>'
    '<line x1="12" y1="2.5" x2="12" y2="4.5"/><line x1="12" y1="19.5" x2="12" y2="21.5"/>'
    '<line x1="2.5" y1="12" x2="4.5" y2="12"/><line x1="19.5" y1="12" x2="21.5" y2="12"/>'
    '<line x1="5.2" y1="5.2" x2="6.6" y2="6.6"/><line x1="17.4" y1="17.4" x2="18.8" y2="18.8"/>'
    '<line x1="5.2" y1="18.8" x2="6.6" y2="17.4"/><line x1="17.4" y1="6.6" x2="18.8" y2="5.2"/>',
    "check": '<polyline points="5 13 10 18 19 6"/>',
    "warning": '<path d="M12 3.5l9 16H3z"/><line x1="12" y1="9" x2="12" y2="14"/>'
    '<circle cx="12" cy="16.8" r="0.9" fill="{color}" stroke="none"/>',
    "file": '<path d="M7 3h7l5 5v13H7z"/><polyline points="14 3 14 8 19 8"/>',
    "download": '<path d="M12 3v12"/><polyline points="7 10 12 15 17 10"/><path d="M4 17.5V20h16v-2.5"/>',
    "close": '<line x1="6" y1="6" x2="18" y2="18"/><line x1="18" y1="6" x2="6" y2="18"/>',
    "refresh": '<path d="M20 11a8 8 0 1 0-2.3 6.6"/><polyline points="20 4 20 11 13 11"/>',
    "image": '<rect x="3" y="4.5" width="18" height="15" rx="2.5"/>'
    '<circle cx="8.5" cy="9.5" r="1.6"/><path d="M4 17l5-5 4 4 3-3 4 4"/>',
    "video": '<rect x="3" y="6" width="12" height="12" rx="2"/><path d="M15 10l6-3v10l-6-3z"/>',
    "audio": '<path d="M9 18V6l10-2v12"/>'
    '<circle cx="6.5" cy="18" r="2.5"/><circle cx="16.5" cy="16" r="2.5"/>',
}


def _svg(name: str, color: str, width: float) -> str:
    body = _PATHS.get(name, _PATHS["file"]).replace("{color}", color)
    return _TEMPLATE.format(color=color, width=width, body=body)


@lru_cache(maxsize=256)
def icon(name: str, color: str = "#949dae", size: int = 20) -> QIcon:
    """產生指定顏色的線條圖示。"""
    svg = _svg(name, color, 1.8)
    renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))

    scale = 2
    pixmap = QPixmap(QSize(size * scale, size * scale))
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    renderer.render(painter)
    painter.end()
    pixmap.setDevicePixelRatio(scale)

    result = QIcon(pixmap)
    return result


@lru_cache(maxsize=64)
def app_icon() -> QIcon:
    """應用程式圖示：藍底圓角方塊加上雙向箭頭。"""
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">'
        '<rect width="64" height="64" rx="14" fill="#2563eb"/>'
        '<g fill="none" stroke="#ffffff" stroke-width="4" stroke-linecap="round" '
        'stroke-linejoin="round">'
        '<path d="M16 24h26"/><polyline points="36 18 42 24 36 30"/>'
        '<path d="M48 40H22"/><polyline points="28 34 22 40 28 46"/>'
        "</g></svg>"
    )
    renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
    pixmap = QPixmap(QSize(256, 256))
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    renderer.render(painter)
    painter.end()
    result = QIcon(pixmap)
    result.addPixmap(
        pixmap.scaled(64, 64, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
    )
    return result


def clear_cache() -> None:
    """主題切換後清除快取，讓圖示換色。"""
    icon.cache_clear()
