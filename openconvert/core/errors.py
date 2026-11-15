"""例外階層。

所有對使用者顯示的錯誤都應該繼承 :class:`OpenConvertError`，
並帶有可讀的 ``user_message``；技術細節放在 ``detail``。
"""

from __future__ import annotations


class OpenConvertError(Exception):
    """所有本專案例外的基底類別。"""

    def __init__(self, message: str, *, detail: str = "") -> None:
        super().__init__(message)
        self.user_message = message
        self.detail = detail

    def __str__(self) -> str:  # pragma: no cover - 簡單委派
        return self.user_message


class ConversionError(OpenConvertError):
    """轉換過程失敗（引擎回報錯誤、輸出檔不完整等）。"""


class UnsupportedFormatError(ConversionError):
    """來源檔案類型無法轉成目標格式。"""


class ConversionCancelled(OpenConvertError):
    """使用者取消了轉換。"""

    def __init__(self, message: str = "已取消") -> None:
        super().__init__(message)


class FFmpegNotFoundError(OpenConvertError):
    """系統中找不到 FFmpeg / FFprobe。"""

    def __init__(self, message: str | None = None) -> None:
        super().__init__(
            message or "找不到 FFmpeg。影片與音訊功能需要 FFmpeg，請在「設定」中指定路徑或安裝後重新啟動。"
        )


class InvalidInputError(OpenConvertError):
    """使用者輸入不合法（例如頁碼範圍格式錯誤）。"""


class OutputConflictError(ConversionError):
    """輸出位置不安全（例如會覆蓋來源檔案）。"""
