"""轉換器基底。

轉換器只依賴標準庫、第三方引擎與 :mod:`openconvert.core`，不依賴 Qt。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..core.errors import ConversionCancelled, UnsupportedFormatError
from ..core.ffmpeg import FFmpegTools
from ..core.job import Job
from ..core.kinds import kinds_for


@dataclass
class ConvertContext:
    """一次轉換所需的全部資訊。"""

    job: Job
    output_dir: Path | None
    overwrite: bool
    tools: FFmpegTools
    progress: Callable[[float, str], None]
    log: Callable[[str], None] = lambda _msg: None
    _created: list[Path] = field(default_factory=list)

    # ------------------------------------------------------------ 便利屬性

    @property
    def sources(self) -> list[Path]:
        return self.job.sources

    @property
    def source(self) -> Path:
        return self.job.sources[0]

    @property
    def options(self) -> dict[str, Any]:
        return self.job.options

    @property
    def token(self) -> str:
        return self.job.target.token

    def option(self, key: str, default: Any = None) -> Any:
        value = self.options.get(key, default)
        return default if value is None else value

    # ------------------------------------------------------------ 取消與輸出

    @property
    def cancelled(self) -> bool:
        return self.job.cancel_event.is_set()

    def check_cancel(self) -> None:
        if self.cancelled:
            raise ConversionCancelled()

    def report(self, fraction: float, message: str = "") -> None:
        self.check_cancel()
        self.progress(fraction, message)

    def track(self, path: str | Path) -> Path:
        """登記輸出檔案，失敗時由執行者負責刪除。"""
        resolved = Path(path)
        self._created.append(resolved)
        return resolved

    def cleanup(self) -> None:
        """刪除本次轉換產生的半成品。"""
        for path in reversed(self._created):
            try:
                if path.is_dir():
                    for child in sorted(path.rglob("*"), reverse=True):
                        child.unlink(missing_ok=True) if child.is_file() else child.rmdir()
                    path.rmdir()
                else:
                    path.unlink(missing_ok=True)
            except OSError:
                pass
        self._created.clear()


class Converter(ABC):
    """所有轉換器的共同介面。"""

    #: 供註冊表使用的名稱
    name: str = "base"

    @abstractmethod
    def convert(self, ctx: ConvertContext) -> list[Path]:
        """執行轉換並回傳產生的檔案（可能多個）。"""

    def supports(self, ctx: ConvertContext) -> bool:
        """確認來源類型是否真的能轉成目標格式。"""
        return True

    # ------------------------------------------------------------ 共用工具

    @staticmethod
    def ensure_source_exists(ctx: ConvertContext) -> None:
        for path in ctx.sources:
            if not path.exists():
                raise UnsupportedFormatError(f"找不到檔案：{path}")
            if not path.is_file():
                raise UnsupportedFormatError(f"不是檔案：{path}")

    @staticmethod
    def ensure_kind(ctx: ConvertContext, allowed: set[str]) -> None:
        for path in ctx.sources:
            kinds = {k.value for k in kinds_for(path)}
            if not (kinds & allowed):
                raise UnsupportedFormatError(f"「{path.name}」的檔案類型無法轉換成 {ctx.job.target.label}。")
