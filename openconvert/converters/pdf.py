"""PDF 處理（pypdf 負責結構、pypdfium2 負責點陣化）。"""

from __future__ import annotations

import io
import re
import zipfile
from pathlib import Path

from pypdf import PdfReader, PdfWriter
from pypdf.errors import PdfReadError

from ..core.errors import ConversionError, InvalidInputError
from ..core.paths import human_size, resolve_output, resolve_output_dir
from ..core.textio import write_text
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


def _open_reader(path: Path, password: str = "") -> PdfReader:
    try:
        reader = PdfReader(str(path))
        # 空密碼可以開啟的檔案很常見（僅限制編輯），先嘗試解密
        if reader.is_encrypted:
            if reader.decrypt(password or ""):
                return reader
            if password:
                raise ConversionError(f"「{path.name}」的密碼不正確，無法開啟。")
            raise ConversionError(f"「{path.name}」有密碼保護，請在選項中填入密碼，或先解除密碼後再轉換。")
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
        if token == "pdf-txt":
            return self._to_text(ctx)
        if token == "pdf-cbz":
            return self._to_cbz(ctx)
        if token == "pdf-encrypt":
            return self._encrypt(ctx)
        if token == "pdf-decrypt":
            return self._decrypt(ctx)
        if token == "pdf-compress":
            return self._compress(ctx)
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

    # ------------------------------------------------------------ 抽出文字

    def _to_text(self, ctx: ConvertContext) -> list[Path]:
        source = ctx.source
        reader = _open_reader(source)

        pages: list[str] = []
        for index, page in enumerate(reader.pages):
            ctx.check_cancel()
            ctx.report(index / max(1, len(reader.pages)) * 0.8, f"第 {index + 1} 頁")
            try:
                pages.append((page.extract_text() or "").strip())
            except Exception as exc:  # pypdf 的例外種類很多
                ctx.log(f"第 {index + 1} 頁無法抽取文字：{exc}")
                pages.append("")

        content = "\n\n".join(text for text in pages if text).strip()
        if not content:
            raise ConversionError(
                "這份 PDF 沒有可抽取的文字層。它可能是掃描檔，請改用「PDF → PNG／JPEG」再辨識文字。"
            )

        dest = resolve_output(source, ctx.output_dir, "txt", overwrite=ctx.overwrite)
        ctx.track(dest)
        write_text(dest, content + "\n")
        ctx.report(1.0, "完成")
        self._verify(dest)
        return [dest]

    # ------------------------------------------------------------ PDF → CBZ

    def _to_cbz(self, ctx: ConvertContext) -> list[Path]:
        try:
            import pypdfium2 as pdfium
        except ImportError as exc:  # pragma: no cover - 依賴缺失
            raise ConversionError(
                "缺少 pypdfium2，無法將 PDF 轉成漫畫壓縮檔。請執行 pip install pypdfium2。"
            ) from exc

        source = ctx.source
        dpi = int(ctx.option("dpi", DEFAULT_DPI) or DEFAULT_DPI)
        dpi = max(MIN_DPI, min(MAX_DPI, dpi))

        dest = resolve_output(source, ctx.output_dir, "cbz", overwrite=ctx.overwrite)
        ctx.track(dest)

        document = None
        written = 0
        try:
            document = pdfium.PdfDocument(str(source))
            page_count = len(document)
            if page_count == 0:
                raise ConversionError("這份 PDF 沒有任何頁面。")

            with zipfile.ZipFile(dest, "w", compression=zipfile.ZIP_STORED) as archive:
                for index in range(page_count):
                    ctx.check_cancel()
                    ctx.report(index / page_count * 0.95, f"第 {index + 1}/{page_count} 頁")
                    page = document[index]
                    bitmap = page.render(scale=dpi / 72)
                    image = bitmap.to_pil()
                    buffer = io.BytesIO()
                    try:
                        image.convert("RGB").save(buffer, "JPEG", quality=90, optimize=True)
                    finally:
                        image.close()
                        bitmap.close()
                        page.close()
                    archive.writestr(f"page_{index + 1:04d}.jpg", buffer.getvalue())
                    written += 1
        except ConversionError:
            raise
        except Exception as exc:  # pypdfium2 會拋出多種自訂例外
            raise ConversionError(f"無法將 PDF 轉成 CBZ：{exc}", detail=str(exc)) from exc
        finally:
            if document is not None:
                document.close()

        if not written:
            raise ConversionError("PDF 轉 CBZ 沒有產生任何頁面。")
        ctx.report(1.0, "完成")
        self._verify(dest)
        return [dest]

    # ------------------------------------------------------------ 加密／解密／壓縮

    def _encrypt(self, ctx: ConvertContext) -> list[Path]:
        password = str(ctx.option("pdf_password", "") or "")
        if not password:
            raise InvalidInputError("請在選項中填入 PDF 密碼。")

        source = ctx.source
        reader = _open_reader(source)
        writer = PdfWriter()
        try:
            writer.append(reader)
            try:
                writer.encrypt(user_password=password, owner_password=password, algorithm="AES-128")
            except Exception as exc:  # 沒有 cryptography 套件時退回相容性較低的 RC4
                ctx.log(f"AES 加密不可用（{exc}），改用 RC4-128。")
                writer.encrypt(user_password=password, owner_password=password, algorithm="RC4-128")
            ctx.report(0.9, "寫入檔案")
            dest = resolve_output(
                source.with_name(f"{source.stem}_encrypted"),
                ctx.output_dir,
                "pdf",
                overwrite=ctx.overwrite,
            )
            ctx.track(dest)
            with dest.open("wb") as handle:
                writer.write(handle)
        finally:
            writer.close()

        # 驗證：用密碼重新開啟
        check = PdfReader(str(dest))
        if not (check.is_encrypted and check.decrypt(password)):
            dest.unlink(missing_ok=True)
            raise ConversionError("加密後的 PDF 無法用密碼開啟，已中止。")

        ctx.report(1.0, "完成")
        self._verify(dest)
        return [dest]

    def _decrypt(self, ctx: ConvertContext) -> list[Path]:
        password = str(ctx.option("pdf_password", "") or "")
        source = ctx.source
        reader = _open_reader(source, password)
        if not reader.is_encrypted:
            raise ConversionError(f"「{source.name}」本來就沒有密碼保護。")

        writer = PdfWriter()
        try:
            writer.append(reader)
            ctx.report(0.9, "寫入檔案")
            dest = resolve_output(
                source.with_name(f"{source.stem}_decrypted"),
                ctx.output_dir,
                "pdf",
                overwrite=ctx.overwrite,
            )
            ctx.track(dest)
            with dest.open("wb") as handle:
                writer.write(handle)
        finally:
            writer.close()

        check = PdfReader(str(dest))
        if check.is_encrypted:
            dest.unlink(missing_ok=True)
            raise ConversionError("解除密碼後的 PDF 仍受保護，已中止。")

        ctx.report(1.0, "完成")
        self._verify(dest)
        return [dest]

    def _compress(self, ctx: ConvertContext) -> list[Path]:
        source = ctx.source
        reader = _open_reader(source)
        writer = PdfWriter()
        try:
            writer.append(reader)
            ctx.report(0.3, "壓縮內容串流")
            for index, page in enumerate(writer.pages):
                ctx.check_cancel()
                ctx.report(0.3 + index / max(1, len(writer.pages)) * 0.5, f"第 {index + 1} 頁")
                try:
                    page.compress_content_streams()
                except Exception as exc:  # 部分頁面（掃描圖片）壓不動就保留原樣
                    ctx.log(f"第 {index + 1} 頁無法再壓縮：{exc}")
            try:
                writer.compress_identical_objects(remove_identicals=True, remove_orphans=True)
            except Exception as exc:  # 部分檔案結構特殊時保留原樣
                ctx.log(f"重複物件清理略過：{exc}")

            ctx.report(0.9, "寫入檔案")
            dest = resolve_output(
                source.with_name(f"{source.stem}_compressed"),
                ctx.output_dir,
                "pdf",
                overwrite=ctx.overwrite,
            )
            ctx.track(dest)
            with dest.open("wb") as handle:
                writer.write(handle)
        finally:
            writer.close()

        before, after = source.stat().st_size, dest.stat().st_size
        ctx.log(f"壓縮結果：{human_size(before)} → {human_size(after)}")
        ctx.report(1.0, "完成")
        self._verify(dest)
        return [dest]

    # ------------------------------------------------------------ 檢查

    @staticmethod
    def _verify(path: Path) -> None:
        if not path.exists() or path.stat().st_size == 0:
            path.unlink(missing_ok=True)
            raise ConversionError("PDF 處理失敗，沒有產生有效檔案。")
