"""PDF 處理（pypdf 負責結構、pypdfium2 負責點陣化）。"""

from __future__ import annotations

import re
from pathlib import Path

from pypdf import PdfReader, PdfWriter
from pypdf.errors import PdfReadError

from ..core.errors import ConversionError, InvalidInputError
from ..core.paths import resolve_output, resolve_output_dir
from .base import ConvertContext, Converter

_RANGE_PART = re.compile(r"^\s*(\d+)?\s*(?:-\s*(\d+)?)?\s*$")

DEFAULT_DPI = 150
MIN_DPI = 72
MAX_DPI = 600


def parse_page_ranges(text: str, page_count: int) -> list[int]:
    """把 ``"1-3,7"`` 解析成 0 起始的頁碼清單。

    Raises:
        InvalidInputError: 語法錯誤或頁碼超出範圍。
    """
    if page_count <= 0:
        raise InvalidInputError("這份 PDF 沒有任何頁面。")

    cleaned = (text or "").strip()
    if not cleaned:
        return list(range(page_count))

    indices: list[int] = []
    seen: set[int] = set()

    for chunk in cleaned.split(","):
        if not chunk.strip():
            continue
        match = _RANGE_PART.match(chunk)
        if not match:
            raise InvalidInputError(f"頁碼格式不正確：「{chunk.strip()}」。例如可輸入 1-3,7")
        start_raw, end_raw = match.group(1), match.group(2)
        if start_raw is None and end_raw is None:
            raise InvalidInputError(f"頁碼格式不正確：「{chunk.strip()}」。")
        start = int(start_raw) if start_raw else 1
        if end_raw:
            end = int(end_raw)
        elif "-" in chunk:
            end = page_count  # "5-" 表示第 5 頁到最後一頁
        else:
            end = start
        if start < 1 or end < 1:
            raise InvalidInputError("頁碼必須從 1 開始。")
        if start > page_count or end > page_count:
            raise InvalidInputError(f"頁碼超出範圍，這份 PDF 只有 {page_count} 頁。")
        if end < start:
            start, end = end, start
        for number in range(start, end + 1):
            zero_based = number - 1
            if zero_based not in seen:
                seen.add(zero_based)
                indices.append(zero_based)

    if not indices:
        raise InvalidInputError("沒有指定任何頁面。")
    return indices


def _open_reader(path: Path) -> PdfReader:
    try:
        reader = PdfReader(str(path))
        # 空密碼可以開啟的檔案很常見（僅限制編輯），先嘗試解密
        if reader.is_encrypted and not reader.decrypt(""):
            raise ConversionError(f"「{path.name}」有密碼保護，請先解除密碼後再轉換。")
        return reader
    except PdfReadError as exc:
        raise ConversionError(f"無法讀取「{path.name}」，PDF 可能已損毀。", detail=str(exc)) from exc
    except OSError as exc:
        raise ConversionError(f"無法開啟「{path.name}」：{exc}", detail=str(exc)) from exc


class PdfConverter(Converter):
    name = "pdf"

    def convert(self, ctx: ConvertContext) -> list[Path]:
        self.ensure_source_exists(ctx)
        self.ensure_kind(ctx, {"pdf"})

        token = ctx.token
        if token == "pdf-merge":
            return self._merge(ctx)
        if token == "pdf-extract":
            return self._extract(ctx)
        if token in ("pdf-png", "pdf-jpg"):
            return self._rasterize(ctx, token)
        raise ConversionError(f"不支援的 PDF 操作：{token}")

    # ------------------------------------------------------------ 合併

    def _merge(self, ctx: ConvertContext) -> list[Path]:
        if len(ctx.sources) < 2:
            raise InvalidInputError("合併 PDF 需要至少 2 個檔案。")

        first = ctx.sources[0]
        dest = resolve_output(
            first.with_name(f"{first.stem}_merged"), ctx.output_dir, "pdf", overwrite=ctx.overwrite
        )
        ctx.track(dest)

        writer = PdfWriter()
        try:
            total_pages = 0
            for source in ctx.sources:
                ctx.check_cancel()
                reader = _open_reader(source)
                for page in reader.pages:
                    writer.add_page(page)
                    total_pages += 1

            if total_pages == 0:
                raise ConversionError("來源 PDF 沒有可合併的頁面。")

            ctx.report(0.9, "寫入檔案")
            with dest.open("wb") as fh:
                writer.write(fh)
        finally:
            writer.close()

        ctx.report(1.0, "完成")
        self._verify(dest)
        return [dest]

    # ------------------------------------------------------------ 抽頁

    def _extract(self, ctx: ConvertContext) -> list[Path]:
        source = ctx.source
        reader = _open_reader(source)
        page_count = len(reader.pages)
        indices = parse_page_ranges(str(ctx.option("pages", "")), page_count)

        dest = resolve_output(source, ctx.output_dir, "pdf", overwrite=ctx.overwrite)
        ctx.track(dest)

        writer = PdfWriter()
        try:
            for position, index in enumerate(indices):
                ctx.report(position / max(1, len(indices)) * 0.9, f"複製第 {index + 1} 頁")
                writer.add_page(reader.pages[index])
            with dest.open("wb") as fh:
                writer.write(fh)
        finally:
            writer.close()

        ctx.report(1.0, "完成")
        self._verify(dest)
        return [dest]

    # ------------------------------------------------------------ 點陣化

    def _rasterize(self, ctx: ConvertContext, token: str) -> list[Path]:
        try:
            import pypdfium2 as pdfium
        except ImportError as exc:  # pragma: no cover - 依賴缺失
            raise ConversionError(
                "缺少 pypdfium2，無法將 PDF 轉成圖片。請執行 pip install pypdfium2。"
            ) from exc

        source = ctx.source
        extension = "png" if token == "pdf-png" else "jpg"
        dpi = int(ctx.option("dpi", DEFAULT_DPI) or DEFAULT_DPI)
        dpi = max(MIN_DPI, min(MAX_DPI, dpi))

        out_dir = resolve_output_dir(source, ctx.output_dir, f"{source.stem}_pages")
        ctx.track(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        outputs: list[Path] = []
        document = None
        try:
            document = pdfium.PdfDocument(str(source))
            page_count = len(document)
            if page_count == 0:
                raise ConversionError("這份 PDF 沒有任何頁面。")

            for index in range(page_count):
                ctx.check_cancel()
                ctx.report(index / page_count, f"第 {index + 1}/{page_count} 頁")
                page = document[index]
                bitmap = page.render(scale=dpi / 72)
                image = bitmap.to_pil()
                dest = out_dir / f"page_{index + 1:03d}.{extension}"
                try:
                    if extension == "jpg":
                        image.convert("RGB").save(dest, "JPEG", quality=92, optimize=True)
                    else:
                        image.save(dest, "PNG", optimize=True)
                finally:
                    image.close()
                    bitmap.close()
                    page.close()
                outputs.append(dest)
        except ConversionError:
            raise
        except Exception as exc:  # pypdfium2 會拋出多種自訂例外
            raise ConversionError(f"無法將 PDF 轉成圖片：{exc}", detail=str(exc)) from exc
        finally:
            if document is not None:
                document.close()

        ctx.report(1.0, "完成")
        if not outputs:
            raise ConversionError("PDF 轉圖片沒有產生任何檔案。")
        return outputs

    # ------------------------------------------------------------ 檢查

    @staticmethod
    def _verify(path: Path) -> None:
        if not path.exists() or path.stat().st_size == 0:
            path.unlink(missing_ok=True)
            raise ConversionError("PDF 處理失敗，沒有產生有效檔案。")
