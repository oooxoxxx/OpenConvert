"""轉換器註冊表。"""

from __future__ import annotations

from ..core.errors import UnsupportedFormatError
from .base import ConvertContext, Converter
from .ebook import EbookConverter
from .image import ImageConverter
from .media import MediaConverter
from .pdf import PdfConverter

_INSTANCES: dict[str, Converter] = {
    MediaConverter.name: MediaConverter(),
    ImageConverter.name: ImageConverter(),
    PdfConverter.name: PdfConverter(),
    EbookConverter.name: EbookConverter(),
}


def get_converter(name: str) -> Converter:
    try:
        return _INSTANCES[name]
    except KeyError as exc:
        raise UnsupportedFormatError(f"沒有可用的轉換器：{name}") from exc


def converter_names() -> list[str]:
    return sorted(_INSTANCES)


__all__ = [
    "ConvertContext",
    "Converter",
    "EbookConverter",
    "ImageConverter",
    "MediaConverter",
    "PdfConverter",
    "converter_names",
    "get_converter",
]
