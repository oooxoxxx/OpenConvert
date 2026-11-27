"""圖片轉換（Pillow）。

包含單張圖片轉檔、批量縮圖，以及「多張圖片合併成一份 PDF」。
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

from ..core.errors import ConversionError
from ..core.imaging import heic_available
from .base import ConvertContext, Converter

#: 目標 token → Pillow 格式名稱
PIL_FORMATS: dict[str, str] = {
    "png": "PNG",
    "jpg": "JPEG",
    "webp": "WEBP",
    "avif": "AVIF",
    "heic": "HEIF",
    "bmp": "BMP",
    "tiff": "TIFF",
    "ico": "ICO",
    "image-gif": "GIF",
    "apng": "PNG",
}

#: 不支援透明度的格式
FLATTEN_FORMATS = frozenset({"jpg", "bmp"})

#: 可保留動畫的格式
ANIMATED_FORMATS = frozenset({"image-gif", "webp", "apng"})

#: 圖片旋轉角度 → PIL 轉置常數
ROTATE_TRANSPOSE = {
    90: Image.Transpose.ROTATE_270,  # 順時針 90 度
    180: Image.Transpose.ROTATE_180,
    270: Image.Transpose.ROTATE_90,  # 順時針 270 度
}

FLIP_TRANSPOSE = {
    "h": Image.Transpose.FLIP_LEFT_RIGHT,
    "v": Image.Transpose.FLIP_TOP_BOTTOM,
}

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


def _crop_to_ratio(image: Image.Image, ratio_text: str) -> Image.Image:
    """置中裁切成指定比例（例如 ``16:9``、``1:1``）；不放大。"""
    try:
        width_text, height_text = ratio_text.lower().replace("：", ":").split(":")
        ratio = float(width_text.strip()) / float(height_text.strip())
        if ratio <= 0:
            raise ValueError
    except (ValueError, ZeroDivisionError) as exc:
        raise ConversionError(f"裁切比例格式不正確：「{ratio_text}」。例如 16:9、1:1") from exc

    width, height = image.size
    if width / height > ratio:  # 太寬 → 裁左右
        new_width = min(width, max(1, round(height * ratio)))
        new_height = height
    else:  # 太高 → 裁上下
        new_width = width
        new_height = min(height, max(1, round(width / ratio)))
    left = (width - new_width) // 2
    top = (height - new_height) // 2
    return image.crop((left, top, left + new_width, top + new_height))


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
    elif image.mode == "P" and not animated:
        keep_alpha = token in ("png", "webp", "avif", "heic", "apng")
        image = image.convert("RGBA" if keep_alpha else "RGB")
    elif token in ("avif", "heic") and not animated and image.mode not in ("RGB", "RGBA", "L"):
        image = image.convert("RGBA")

    if token == "jpg":
        params.update(quality=quality, optimize=True, progressive=True)
    elif token == "webp":
        params.update(quality=quality, method=6)
    elif token == "avif":
        params.update(quality=quality, speed=6)
    elif token == "heic":
        params.update(quality=quality)
    elif token == "png":
        params.update(optimize=True, compress_level=6)
    elif token == "apng":
        if animated:
            params.update(save_all=True, loop=0, default_image=False)
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

        if token in ("img-rotate", "img-flip", "img-crop"):
            return self._transform_image(ctx, token, max_dimension)

        if token not in PIL_FORMATS:
            raise ConversionError(f"不支援的圖片格式：{token}")

        if token == "heic" and not heic_available():
            raise ConversionError("轉成 HEIC 需要 pillow-heif 套件，請執行 pip install pillow-heif 後再試。")

        source = ctx.source
        dest = ctx.resolve_output(source, ctx.job.target.extension)
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

    # ------------------------------------------------------------ 旋轉／翻轉／裁切

    def _transform_image(self, ctx: ConvertContext, token: str, max_dimension: int | None) -> list[Path]:
        """旋轉／翻轉／裁切：無損操作，輸出 PNG。

        動畫圖片只處理第一格（會在記錄中說明）。
        """
        source = ctx.source
        dest = ctx.resolve_output(source, ctx.job.target.extension)
        ctx.track(dest)
        ctx.report(0.1, "讀取中")

        with _open(source) as image:
            if getattr(image, "n_frames", 1) > 1:
                ctx.log("動畫圖片只會處理第一格，輸出為單張 PNG。")
            work = ImageOps.exif_transpose(image)
            work = _resize(work, max_dimension)

            if token == "img-rotate":
                raw = ctx.option("rotate_degrees", 90)
                try:
                    degrees = int(raw)
                except (TypeError, ValueError) as exc:
                    raise ConversionError(f"不支援的旋轉角度：{raw}（可用 90／180／270）") from exc
                transpose = ROTATE_TRANSPOSE.get(degrees)
                if transpose is None:
                    raise ConversionError(f"不支援的旋轉角度：{degrees}（可用 90／180／270）")
                work = work.transpose(transpose)
            elif token == "img-flip":
                axis = str(ctx.option("flip_axis", "h") or "h")
                transpose = FLIP_TRANSPOSE.get(axis)
                if transpose is None:
                    raise ConversionError(f"不支援的翻轉方向：{axis}（可用 h／v）")
                work = work.transpose(transpose)
            else:  # img-crop
                ratio_text = str(ctx.option("crop_ratio", "16:9") or "16:9")
                work = _crop_to_ratio(work, ratio_text)

            ctx.report(0.7, "寫入檔案")
            params: dict[str, object] = {"optimize": True, "compress_level": 6}
            if work.mode == "P":
                work = work.convert("RGBA" if "transparency" in image.info else "RGB")
            try:
                work.save(dest, "PNG", **params)  # type: ignore[arg-type]
            except (OSError, ValueError) as exc:
                raise ConversionError(f"無法儲存為 PNG：{exc}", detail=str(exc)) from exc

        ctx.report(1.0, "完成")
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
        dest = ctx.resolve_output(first.with_name(name), "pdf")
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
