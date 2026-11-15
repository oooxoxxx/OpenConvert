"""字型格式轉換（fontTools）。

WOFF 與 WOFF2 只是 sfnt（TTF／OTF）的壓縮容器，因此可以無損互轉。
OTF 的 CFF 輪廓無法直接變成 TTF 的 TrueType 輪廓，遇到時會給出明確訊息，
而不是產出一個副檔名騙人的檔案。
"""

from __future__ import annotations

from pathlib import Path

from ..core.errors import ConversionError
from ..core.paths import resolve_output
from .base import ConvertContext, Converter

FLAVORS: dict[str, str | None] = {
    "font-woff": "woff",
    "font-woff2": "woff2",
    "font-ttf": None,
}


def _load(path: Path):
    try:
        from fontTools.ttLib import TTFont
    except ImportError as exc:  # pragma: no cover - 依賴缺失
        raise ConversionError("缺少 fontTools，無法轉換字型。") from exc

    try:
        return TTFont(str(path), recalcBBoxes=False, recalcTimestamp=False)
    except Exception as exc:  # fontTools 的例外種類很多
        raise ConversionError(
            f"無法讀取字型「{path.name}」，檔案可能已損毀或不是有效的字型。",
            detail=str(exc),
        ) from exc


class FontConverter(Converter):
    name = "font"

    def convert(self, ctx: ConvertContext) -> list[Path]:
        self.ensure_source_exists(ctx)
        self.ensure_kind(ctx, {"font"})

        source = ctx.source
        token = ctx.token
        if token not in FLAVORS:
            raise ConversionError(f"不支援的字型目標：{token}")

        font = _load(source)
        try:
            if token == "font-ttf" and ("CFF " in font or "CFF2" in font):
                raise ConversionError(
                    f"「{source.name}」使用 OpenType（CFF）輪廓，無法直接轉成 TTF。"
                    "請改選 WOFF 或 WOFF2，或使用專業字型工具轉換輪廓。"
                )

            ctx.report(0.3, "轉換字型")
            dest = resolve_output(source, ctx.output_dir, ctx.job.target.extension, overwrite=ctx.overwrite)
            ctx.track(dest)
            font.flavor = FLAVORS[token]
            try:
                font.save(str(dest))
            except ImportError as exc:
                dest.unlink(missing_ok=True)
                raise ConversionError(
                    "轉成 WOFF2 需要 brotli 套件，請執行 pip install brotli 後再試。",
                    detail=str(exc),
                ) from exc
            except Exception as exc:
                dest.unlink(missing_ok=True)
                raise ConversionError(
                    f"無法將「{source.name}」轉成 {ctx.job.target.label}：{exc}",
                    detail=str(exc),
                ) from exc
        finally:
            font.close()

        ctx.report(1.0, "完成")
        if not dest.exists() or dest.stat().st_size == 0:
            dest.unlink(missing_ok=True)
            raise ConversionError("字型轉換失敗，沒有產生有效檔案。")
        return [dest]


__all__ = ["FontConverter"]
