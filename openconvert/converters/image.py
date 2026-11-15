"""圖片轉換（Pillow）。

包含單張圖片轉檔、批量縮圖，以及「多張圖片合併成一份 PDF」。
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

from ..core.errors import ConversionError
from ..core.paths import resolve_output
from .base import ConvertContext, Converter

#: 目標 token → Pillow 格式名稱
PIL_FORMATS: dict[str, str] = {
    "png": "PNG",
    "jpg": "JPEG",
    "webp": "WEBP",
    "bmp": "BMP",
    "tiff": "TIFF",
    "ico": "ICO",
    "image-gif": "GIF",
}

#: 不支援透明度的格式
FLATTEN_FORMATS = frozenset({"jpg", "bmp"})

#: 可保留動畫的格式
ANIMATED_FORMATS = frozenset({"image-gif", "webp"})

ICO_SIZES = ((16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256))


def _open(path: Path) -> Image.Image:
    try:
        image = Image.open(path)
        image.load()
    except (UnidentifiedImageError, OSError) as exc:
        raise ConversionError(
            f"無法讀取圖片「{path.name}」，格式可能不受支援或檔案已損毀。", detail=str(exc)
        ) from exc
    return image


def _flatten(image: Image.Image, background: str) -> Image.Image:
    """把含透明度的圖片壓到指定底色上（JPEG / BMP 必需）。"""
    has_alpha = image.mode in ("RGBA", "LA") or (image.mode == "P" and "transparency" in image.info)
    if not has_alpha:
        return image.convert("RGB")
    rgba = image.convert("RGBA")
    canvas = Image.new("RGB", rgba.size, background)
    canvas.paste(rgba, mask=rgba.getchannel("A"))
    return canvas


def _resize(image: Image.Image, max_dimension: int | None) -> Image.Image:
    if not max_dimension:
        return image
    longest = max(image.size)
    if longest <= max_dimension:
        return image
    ratio = max_dimension / longest
    size = (max(1, round(image.width * ratio)), max(1, round(image.height * ratio)))
    return image.resize(size, Image.Resampling.LANCZOS)


def _save(
    image: Image.Image, dest: Path, token: str, *, quality: int, background: str, animated: bool
) -> None:
    fmt = PIL_FORMATS[token]

    params: dict[str, object] = {}
    if token in FLATTEN_FORMATS:
        image = _flatten(image, background)
    elif token == "ico":
        image = image.convert("RGBA")
        params["sizes"] = ICO_SIZES
    elif image.mode == "P":
        image = image.convert("RGBA" if token in ("png", "webp") else "RGB")

    if token == "jpg":
        params.update(quality=quality, optimize=True, progressive=True)
    elif token == "webp":
        params.update(quality=quality, method=6)
    elif token == "png":
        params.update(optimize=True, compress_level=6)
    elif token == "tiff":
        params.update(compression="tiff_lzw")
    elif token == "image-gif" and animated:
        params.update(save_all=True, loop=0)

    try:
        image.save(dest, format=fmt, **params)  # type: ignore[arg-type]
    except (OSError, ValueError) as exc:
        raise ConversionError(
            f"無法儲存為 {dest.suffix.lstrip('.').upper()}：{exc}", detail=str(exc)
        ) from exc


class ImageConverter(Converter):
    name = "image"

    def convert(self, ctx: ConvertContext) -> list[Path]:
        self.ensure_source_exists(ctx)
        self.ensure_kind(ctx, {"image"})

        token = ctx.token
        quality = int(ctx.option("quality_jpeg", 90) or 90)
        quality = max(1, min(100, quality))
        background = str(ctx.option("background", "#ffffff") or "#ffffff")
        max_dimension = ctx.option("max_dimension")
        try:
            max_dimension = int(max_dimension) if max_dimension else None
        except (TypeError, ValueError):
            max_dimension = None

        if token == "img-pdf":
            return self._images_to_pdf(ctx, background, max_dimension)

        if token not in PIL_FORMATS:
            raise ConversionError(f"不支援的圖片格式：{token}")

        source = ctx.source
        dest = resolve_output(source, ctx.output_dir, ctx.job.target.extension, overwrite=ctx.overwrite)
        ctx.track(dest)
        ctx.report(0.1, "讀取中")

        with _open(source) as image:
            frames = getattr(image, "n_frames", 1)
            animated = frames > 1 and token in ANIMATED_FORMATS

            if animated:
                if max_dimension:
                    ctx.log("動畫圖片不支援縮放，將保留原始尺寸。")
                _save(image, dest, token, quality=quality, background=background, animated=True)
            else:
                work = ImageOps.exif_transpose(image)
                work = _resize(work, max_dimension)
                _save(work, dest, token, quality=quality, background=background, animated=False)

        ctx.report(0.95, "寫入完成")
        self._verify(dest)
        return [dest]

    # ------------------------------------------------------------ 圖片 → PDF

    def _images_to_pdf(
        self,
        ctx: ConvertContext,
        background: str,
        max_dimension: int | None,
    ) -> list[Path]:
        sources = ctx.sources
        first = sources[0]
        name = f"{first.stem}_merged" if len(sources) > 1 else first.stem
        dest = resolve_output(first.with_name(name), ctx.output_dir, "pdf", overwrite=ctx.overwrite)
        ctx.track(dest)

        pages: list[Image.Image] = []
        try:
            for index, source in enumerate(sources):
                ctx.check_cancel()
                ctx.report(index / max(1, len(sources)) * 0.9, f"讀取 {index + 1}/{len(sources)}")
                with _open(source) as image:
                    page = ImageOps.exif_transpose(image)
                    page = _resize(page, max_dimension)
                    pages.append(_flatten(page, background))

            if not pages:
                raise ConversionError("沒有可合併的圖片。")

            dpi = 150
            pages[0].save(
                dest,
                "PDF",
                save_all=True,
                append_images=pages[1:],
                resolution=dpi,
            )
        except OSError as exc:
            raise ConversionError(f"無法產生 PDF：{exc}", detail=str(exc)) from exc
        finally:
            for page in pages:
                page.close()

        ctx.report(1.0, "完成")
        self._verify(dest)
        return [dest]

    # ------------------------------------------------------------ 檢查

    @staticmethod
    def _verify(path: Path) -> None:
        if not path.exists() or path.stat().st_size == 0:
            path.unlink(missing_ok=True)
            raise ConversionError("圖片轉換失敗，沒有產生有效檔案。")
