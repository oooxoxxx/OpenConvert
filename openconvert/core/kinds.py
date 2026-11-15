"""檔案類型判定。

一個副檔名可能對應多種處理方式（例如 ``.gif`` 既可以是動畫圖片，
也可以是影片來源），因此這裡提供「候選類型」而非單一答案。
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path


class MediaKind(str, Enum):
    VIDEO = "video"
    AUDIO = "audio"
    IMAGE = "image"
    PDF = "pdf"
    EPUB = "epub"
    CBZ = "cbz"
    UNKNOWN = "unknown"


VIDEO_EXTENSIONS = frozenset({"mp4", "mkv", "webm", "mov", "avi", "m4v", "flv", "wmv", "ts", "mpg", "mpeg"})
AUDIO_EXTENSIONS = frozenset({"mp3", "m4a", "aac", "wav", "flac", "ogg", "opus", "wma", "aiff", "alac"})
IMAGE_EXTENSIONS = frozenset(
    {"png", "jpg", "jpeg", "webp", "bmp", "tif", "tiff", "gif", "ico", "avif", "heic"}
)
BOOK_IMAGE_EXTENSIONS = frozenset({"png", "jpg", "jpeg", "webp", "bmp", "tif", "tiff", "gif"})

#: 這些副檔名同時是「圖片」也是「影片」來源。
AMBIGUOUS_EXTENSIONS = frozenset({"gif"})

KIND_LABELS: dict[MediaKind, str] = {
    MediaKind.VIDEO: "影片",
    MediaKind.AUDIO: "音訊",
    MediaKind.IMAGE: "圖片",
    MediaKind.PDF: "PDF",
    MediaKind.EPUB: "EPUB 電子書",
    MediaKind.CBZ: "CBZ 漫畫",
    MediaKind.UNKNOWN: "未知",
}


def extension_of(path: str | Path) -> str:
    """回傳小寫、不含點的副檔名；沒有副檔名時回傳空字串。"""
    suffix = Path(path).suffix
    return suffix[1:].lower() if suffix else ""


def kinds_for_extension(extension: str) -> tuple[MediaKind, ...]:
    """依副檔名回傳候選類型，可能性高的排在前面。"""
    ext = extension.lower().lstrip(".")
    if ext in AMBIGUOUS_EXTENSIONS:
        return (MediaKind.IMAGE, MediaKind.VIDEO)
    if ext in VIDEO_EXTENSIONS:
        return (MediaKind.VIDEO,)
    if ext in AUDIO_EXTENSIONS:
        return (MediaKind.AUDIO,)
    if ext in IMAGE_EXTENSIONS:
        return (MediaKind.IMAGE,)
    if ext == "pdf":
        return (MediaKind.PDF,)
    if ext == "epub":
        return (MediaKind.EPUB,)
    if ext == "cbz":
        return (MediaKind.CBZ,)
    return (MediaKind.UNKNOWN,)


def kinds_for(path: str | Path) -> tuple[MediaKind, ...]:
    return kinds_for_extension(extension_of(path))


def primary_kind(path: str | Path) -> MediaKind:
    return kinds_for(path)[0]


def kind_label(path_or_kind: str | Path | MediaKind) -> str:
    kind = path_or_kind if isinstance(path_or_kind, MediaKind) else primary_kind(path_or_kind)
    return KIND_LABELS.get(kind, KIND_LABELS[MediaKind.UNKNOWN])


def is_supported(path: str | Path) -> bool:
    return primary_kind(path) is not MediaKind.UNKNOWN


SUPPORTED_EXTENSIONS: frozenset[str] = frozenset(
    VIDEO_EXTENSIONS | AUDIO_EXTENSIONS | IMAGE_EXTENSIONS | {"pdf", "epub", "cbz"}
)
