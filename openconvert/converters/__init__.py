"""轉換器註冊表。"""

from __future__ import annotations

from ..core.errors import UnsupportedFormatError
from .archive import ArchiveConverter
from .base import ConvertContext, Converter
from .data import DataConverter
from .document import DocumentConverter
from .ebook import EbookConverter
from .font import FontConverter
from .image import ImageConverter
from .media import MediaConverter
from .pdf import PdfConverter
from .subtitle import SubtitleConverter

_INSTANCES: dict[str, Converter] = {
    MediaConverter.name: MediaConverter(),
    ImageConverter.name: ImageConverter(),
    PdfConverter.name: PdfConverter(),
    EbookConverter.name: EbookConverter(),
    DocumentConverter.name: DocumentConverter(),
    DataConverter.name: DataConverter(),
    SubtitleConverter.name: SubtitleConverter(),
    FontConverter.name: FontConverter(),
    ArchiveConverter.name: ArchiveConverter(),
}


def get_converter(name: str) -> Converter:
    try:
        return _INSTANCES[name]
    except KeyError as exc:
        raise UnsupportedFormatError(f"沒有可用的轉換器：{name}") from exc


def converter_names() -> list[str]:
    return sorted(_INSTANCES)


__all__ = [
    "ArchiveConverter",
    "ConvertContext",
    "Converter",
    "DataConverter",
    "DocumentConverter",
    "EbookConverter",
    "FontConverter",
    "ImageConverter",
    "MediaConverter",
    "PdfConverter",
    "SubtitleConverter",
    "converter_names",
    "get_converter",
]
