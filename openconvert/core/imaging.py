"""Pillow 影像引擎初始化。

HEIC/HEIF 由 ``pillow-heif`` 提供；未安裝時對應的目標格式會回報清楚的錯誤，
而不是在啟動時崩潰。
"""

from __future__ import annotations

HEIC_SUPPORTED = False

try:  # pragma: no cover - 取決於環境是否安裝 pillow-heif
    from pillow_heif import register_heif_opener

    register_heif_opener()
    HEIC_SUPPORTED = True
except Exception:  # 任何載入失敗都不該讓程式無法啟動
    HEIC_SUPPORTED = False


def heic_available() -> bool:
    return HEIC_SUPPORTED
