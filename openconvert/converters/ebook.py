"""電子書轉換：CBZ ⇄ EPUB，以及整批圖片 → 電子書。

EPUB 由本專案自行以 ``zipfile`` + XHTML 樣板產生，不依賴 AGPL 授權的
第三方 EPUB 函式庫。這樣做的好處是行為完全可預測，也能直接寫單元測試。
"""

from __future__ import annotations

import io
import re
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree as ET

from PIL import Image

from ..core.errors import ConversionError
from ..core.paths import resolve_output
from ..core.sorting import natural_key
from ..core.textio import read_text, write_text
from . import markup
from .base import ConvertContext, Converter

IMAGE_EXTENSIONS = frozenset({"jpg", "jpeg", "png", "gif", "webp", "bmp", "tif", "tiff", "avif"})

#: EPUB 3 核心媒體類型；其他格式在打包時轉成 JPEG 以確保閱讀器能顯示
EPUB_MEDIA_TYPES = {
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "gif": "image/gif",
    "webp": "image/webp",
    "svg": "image/svg+xml",
}

TEXT_EXTENSIONS = frozenset({"txt"})
MARKDOWN_EXTENSIONS = frozenset({"md", "markdown"})
HTML_EXTENSIONS = frozenset({"html", "htm"})


def _is_image(name: str) -> bool:
    return Path(name).suffix.lstrip(".").lower() in IMAGE_EXTENSIONS


def _normalize_image(name: str, data: bytes) -> tuple[str, bytes]:
    """把 EPUB 不支援的圖片格式轉成 JPEG。"""
    ext = Path(name).suffix.lstrip(".").lower()
    if ext in EPUB_MEDIA_TYPES:
        return name, data
    try:
        with Image.open(io.BytesIO(data)) as image:
            converted = image.convert("RGB")
            buffer = io.BytesIO()
            converted.save(buffer, "JPEG", quality=92)
            return f"{Path(name).stem}.jpg", buffer.getvalue()
    except (OSError, ValueError) as exc:
        raise ConversionError(f"無法處理圖片「{name}」：{exc}", detail=str(exc)) from exc


class EbookConverter(Converter):
    name = "ebook"

    def convert(self, ctx: ConvertContext) -> list[Path]:
        self.ensure_source_exists(ctx)
        token = ctx.token

        if token == "cbz":
            return self._write_cbz(ctx, self._collect_pages(ctx))

        if token == "epub":
            extension = ctx.source.suffix.lstrip(".").lower()
            if extension in TEXT_EXTENSIONS | MARKDOWN_EXTENSIONS | HTML_EXTENSIONS:
                return self._write_text_epub(ctx, extension)
            pages = self._collect_pages(ctx)
            return self._write_epub(ctx, pages)

        if token == "book-pdf":
            return self._write_pdf(ctx, self._collect_pages(ctx))

        if token == "epub-txt":
            return self._write_plain_text(ctx)

        raise ConversionError(f"不支援的電子書格式：{token}")

    # ------------------------------------------------------------ 收集頁面

    def _collect_pages(self, ctx: ConvertContext) -> list[tuple[str, bytes]]:
        source = ctx.source

        if source.suffix.lower() == ".cbz":
            return self._pages_from_cbz(source, ctx)

        if source.suffix.lower() == ".epub":
            return self._pages_from_epub(source, ctx)

        # 圖片：單張或整批（群組型目標）
        pages: list[tuple[str, bytes]] = []
        sources = sorted(ctx.sources, key=lambda p: natural_key(p.name))
        for index, path in enumerate(sources):
            ctx.check_cancel()
            ctx.report(index / max(1, len(sources)) * 0.5, f"讀取 {index + 1}/{len(sources)}")
            ext = path.suffix.lstrip(".").lower()
            if ext not in IMAGE_EXTENSIONS:
                raise ConversionError(f"「{path.name}」不是圖片，無法放進電子書。")
            try:
                pages.append((f"{index + 1:04d}{path.suffix}", path.read_bytes()))
            except OSError as exc:
                raise ConversionError(f"無法讀取「{path.name}」：{exc}", detail=str(exc)) from exc
        if not pages:
            raise ConversionError("沒有可放進電子書的圖片。")
        return pages

    def _pages_from_cbz(self, source: Path, ctx: ConvertContext) -> list[tuple[str, bytes]]:
        try:
            with zipfile.ZipFile(source) as archive:
                names = [
                    n
                    for n in archive.namelist()
                    if not n.endswith("/") and _is_image(n) and not n.startswith("__MACOSX")
                ]
                if not names:
                    raise ConversionError(f"「{source.name}」裡沒有圖片。")
                names.sort(key=natural_key)
                pages: list[tuple[str, bytes]] = []
                for index, name in enumerate(names):
                    ctx.check_cancel()
                    ctx.report(index / len(names) * 0.5, f"讀取 {index + 1}/{len(names)}")
                    suffix = Path(name).suffix or ".jpg"
                    pages.append((f"{index + 1:04d}{suffix}", archive.read(name)))
                return pages
        except zipfile.BadZipFile as exc:
            raise ConversionError(f"「{source.name}」不是有效的 CBZ（ZIP）檔案。", detail=str(exc)) from exc
        except OSError as exc:
            raise ConversionError(f"無法讀取「{source.name}」：{exc}", detail=str(exc)) from exc

    def _pages_from_epub(self, source: Path, ctx: ConvertContext) -> list[tuple[str, bytes]]:
        try:
            with zipfile.ZipFile(source) as archive:
                images = {n for n in archive.namelist() if _is_image(n)}
                if not images:
                    raise ConversionError(f"「{source.name}」裡沒有圖片。")

                ordered = self._epub_spine_images(archive, images)
                if not ordered:
                    ordered = sorted(images, key=natural_key)

                pages: list[tuple[str, bytes]] = []
                for index, name in enumerate(ordered):
                    ctx.check_cancel()
                    ctx.report(index / len(ordered) * 0.5, f"讀取 {index + 1}/{len(ordered)}")
                    suffix = Path(name).suffix or ".jpg"
                    pages.append((f"{index + 1:04d}{suffix}", archive.read(name)))
                return pages
        except zipfile.BadZipFile as exc:
            raise ConversionError(f"「{source.name}」不是有效的 EPUB 檔案。", detail=str(exc)) from exc
        except OSError as exc:
            raise ConversionError(f"無法讀取「{source.name}」：{exc}", detail=str(exc)) from exc

    @staticmethod
    def _epub_spine_hrefs(archive: zipfile.ZipFile) -> list[str]:
        """依 container.xml → OPF → spine 的順序回傳閱讀章節路徑。"""
        try:
            container = ET.fromstring(archive.read("META-INF/container.xml"))
        except (KeyError, ET.ParseError):
            return []
        rootfile = container.find(".//{urn:oasis:names:tc:opendocument:xmlns:container}rootfile")
        if rootfile is None:
            rootfile = container.find(".//rootfile")
        if rootfile is None:
            return []
        opf_path = rootfile.get("full-path")
        if not opf_path:
            return []
        try:
            opf = ET.fromstring(archive.read(opf_path))
        except (KeyError, ET.ParseError):
            return []

        base = Path(opf_path).parent
        manifest: dict[str, str] = {}
        for item in opf.iter():
            if item.tag.endswith("item") and item.get("id") and item.get("href"):
                manifest[item.get("id", "")] = item.get("href", "")

        order: list[str] = []
        for itemref in opf.iter():
            if itemref.tag.endswith("itemref") and itemref.get("idref"):
                href = manifest.get(itemref.get("idref", ""))
                if href:
                    order.append(str((base / href).as_posix()).lstrip("./"))
        return order

    @classmethod
    def _epub_spine_images(cls, archive: zipfile.ZipFile, images: set[str]) -> list[str]:
        """依 EPUB spine 順序找出圖片，讓 CBZ 的頁序與閱讀順序一致。"""
        found: list[str] = []
        for xhtml in cls._epub_spine_hrefs(archive):
            try:
                content = archive.read(xhtml).decode("utf-8", "ignore")
            except KeyError:
                continue
            for match in re.finditer(r'<img[^>]+src="([^"]+)"', content, re.IGNORECASE):
                target = str((Path(xhtml).parent / match.group(1)).as_posix()).lstrip("./")
                if target in images and target not in found:
                    found.append(target)
        return found

    # ------------------------------------------------------------ 輸出 CBZ

    def _write_cbz(self, ctx: ConvertContext, pages: list[tuple[str, bytes]]) -> list[Path]:
        source = ctx.source
        name = f"{source.stem}_book" if len(ctx.sources) > 1 else source.stem
        dest = resolve_output(source.with_name(name), ctx.output_dir, "cbz", overwrite=ctx.overwrite)
        ctx.track(dest)

        try:
            with zipfile.ZipFile(dest, "w", compression=zipfile.ZIP_STORED) as archive:
                for index, (filename, data) in enumerate(pages):
                    ctx.check_cancel()
                    ctx.report(0.5 + index / len(pages) * 0.45, f"打包 {index + 1}/{len(pages)}")
                    suffix = Path(filename).suffix or ".jpg"
                    archive.writestr(f"{index + 1:04d}{suffix}", data)
        except OSError as exc:
            raise ConversionError(f"無法寫入 CBZ：{exc}", detail=str(exc)) from exc

        ctx.report(1.0, "完成")
        self._verify(dest)
        return [dest]

    # ------------------------------------------------------------ 輸出 EPUB

    def _write_epub(self, ctx: ConvertContext, pages: list[tuple[str, bytes]]) -> list[Path]:
        source = ctx.source
        name = f"{source.stem}_book" if len(ctx.sources) > 1 else source.stem
        dest = resolve_output(source.with_name(name), ctx.output_dir, "epub", overwrite=ctx.overwrite)
        ctx.track(dest)

        book_id = f"urn:uuid:{uuid.uuid4()}"
        title = ctx.option("title") or (source.stem if len(ctx.sources) == 1 else "OpenConvert 合輯")
        author = str(ctx.option("author", "OpenConvert"))
        language = str(ctx.option("language", "zh-TW"))
        modified = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        entries: list[tuple[str, bytes]] = []
        for index, (filename, data) in enumerate(pages):
            ctx.check_cancel()
            ctx.report(0.5 + index / len(pages) * 0.1, f"處理 {index + 1}/{len(pages)}")
            normalized_name, normalized_data = _normalize_image(filename, data)
            entries.append((f"images/{index + 1:04d}{Path(normalized_name).suffix}", normalized_data))

        manifest: list[str] = []
        spine: list[str] = []
        xhtml_items: list[tuple[str, bytes]] = []

        for index, (image_path, _) in enumerate(entries):
            page_id = f"page_{index + 1:04d}"
            img_id = f"img_{index + 1:04d}"
            image_href = image_path.split("/", 1)[1]
            media_type = EPUB_MEDIA_TYPES.get(Path(image_path).suffix.lstrip(".").lower(), "image/jpeg")
            cover = ' properties="cover-image"' if index == 0 else ""
            manifest.append(
                f'    <item id="{img_id}" href="images/{image_href}" media-type="{media_type}"{cover}/>'
            )
            manifest.append(
                f'    <item id="{page_id}" href="{page_id}.xhtml" media-type="application/xhtml+xml"/>'
            )
            spine.append(f'    <itemref idref="{page_id}"/>')
            xhtml_items.append(
                (f"OEBPS/{page_id}.xhtml", _xhtml_page(title, f"images/{image_href}").encode("utf-8"))
            )

        nav = _nav_document(title)
        manifest.append(
            '    <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>'
        )

        opf = _opf_document(
            book_id=book_id,
            title=title,
            author=author,
            language=language,
            modified=modified,
            manifest="\n".join(manifest),
            spine="\n".join(spine),
            cover_href=entries[0][0].split("/", 1)[1] if entries else None,
        )

        try:
            with zipfile.ZipFile(dest, "w") as archive:
                # mimetype 必須是第一個項目且不壓縮
                archive.writestr(
                    zipfile.ZipInfo("mimetype"),
                    b"application/epub+zip",
                    compress_type=zipfile.ZIP_STORED,
                )
                archive.writestr("META-INF/container.xml", _CONTAINER, compress_type=zipfile.ZIP_DEFLATED)
                archive.writestr("OEBPS/content.opf", opf.encode("utf-8"), compress_type=zipfile.ZIP_DEFLATED)
                archive.writestr("OEBPS/nav.xhtml", nav.encode("utf-8"), compress_type=zipfile.ZIP_DEFLATED)
                for index, (path, data) in enumerate(entries):
                    ctx.check_cancel()
                    ctx.report(0.6 + index / len(entries) * 0.35, f"寫入圖片 {index + 1}/{len(entries)}")
                    archive.writestr(f"OEBPS/{path}", data, compress_type=zipfile.ZIP_STORED)
                for path, data in xhtml_items:
                    archive.writestr(path, data, compress_type=zipfile.ZIP_DEFLATED)
        except OSError as exc:
            raise ConversionError(f"無法寫入 EPUB：{exc}", detail=str(exc)) from exc

        ctx.report(1.0, "完成")
        self._verify(dest)
        return [dest]

    # ------------------------------------------------------------ 輸出 PDF

    def _write_pdf(self, ctx: ConvertContext, pages: list[tuple[str, bytes]]) -> list[Path]:
        source = ctx.source
        name = f"{source.stem}_book" if len(ctx.sources) > 1 else source.stem
        dest = resolve_output(source.with_name(name), ctx.output_dir, "pdf", overwrite=ctx.overwrite)
        ctx.track(dest)

        images: list[Image.Image] = []
        try:
            for index, (filename, data) in enumerate(pages):
                ctx.check_cancel()
                ctx.report(index / len(pages) * 0.7, f"讀取 {index + 1}/{len(pages)}")
                try:
                    with Image.open(io.BytesIO(data)) as image:
                        page = image.convert("RGB")
                        page.thumbnail((4000, 4000), Image.Resampling.LANCZOS)
                        images.append(page.copy())
                except (OSError, ValueError) as exc:
                    raise ConversionError(f"無法處理圖片「{filename}」：{exc}", detail=str(exc)) from exc

            if not images:
                raise ConversionError("這本漫畫沒有可轉成 PDF 的頁面。")

            ctx.report(0.8, "寫入 PDF")
            images[0].save(
                dest,
                "PDF",
                save_all=True,
                append_images=images[1:],
                resolution=150,
            )
        except OSError as exc:
            raise ConversionError(f"無法產生 PDF：{exc}", detail=str(exc)) from exc
        finally:
            for image in images:
                image.close()

        ctx.report(1.0, "完成")
        self._verify(dest)
        return [dest]

    # ------------------------------------------------------------ EPUB → 文字

    def _write_plain_text(self, ctx: ConvertContext) -> list[Path]:
        source = ctx.source
        try:
            with zipfile.ZipFile(source) as archive:
                names = [
                    name
                    for name in archive.namelist()
                    if name.lower().endswith((".xhtml", ".html", ".htm"))
                    and not Path(name).name.lower().startswith("nav")
                ]
                ordered = self._epub_spine_hrefs(archive)
                if not ordered:
                    ordered = sorted(names, key=natural_key)

                chapters: list[str] = []
                for index, name in enumerate(ordered):
                    if name not in names:
                        continue
                    ctx.check_cancel()
                    ctx.report(index / max(1, len(ordered)) * 0.8, f"讀取 {index + 1}")
                    raw = archive.read(name).decode("utf-8", "ignore")
                    text = markup.html_to_text(raw)
                    if text:
                        chapters.append(text)
        except zipfile.BadZipFile as exc:
            raise ConversionError(f"「{source.name}」不是有效的 EPUB 檔案。", detail=str(exc)) from exc
        except OSError as exc:
            raise ConversionError(f"無法讀取「{source.name}」：{exc}", detail=str(exc)) from exc

        content = "\n\n".join(chapters).strip()
        if not content:
            raise ConversionError("這本 EPUB 沒有可抽取的文字（可能全部是圖片）。")

        dest = resolve_output(source, ctx.output_dir, "txt", overwrite=ctx.overwrite)
        ctx.track(dest)
        write_text(dest, content + "\n")
        ctx.report(1.0, "完成")
        self._verify(dest)
        return [dest]

    # ------------------------------------------------------------ 文字 → EPUB

    def _write_text_epub(self, ctx: ConvertContext, extension: str) -> list[Path]:
        source = ctx.source
        try:
            raw = read_text(source)
        except OSError as exc:
            raise ConversionError(f"無法讀取「{source.name}」：{exc}", detail=str(exc)) from exc

        if extension in MARKDOWN_EXTENSIONS:
            body = markup.markdown_to_html(raw)
        elif extension in HTML_EXTENSIONS:
            body = markup.html_body(raw)
        else:
            paragraphs = [
                f"<p>{markup.escape(block).replace(chr(10), '<br/>')}</p>"
                for block in re.split(r"\n\s*\n", raw)
                if block.strip()
            ]
            body = "\n".join(paragraphs)

        if not body.strip():
            raise ConversionError(f"「{source.name}」沒有可放進電子書的內容。")

        chapters = _split_chapters(body, source.stem)
        dest = resolve_output(source, ctx.output_dir, "epub", overwrite=ctx.overwrite)
        ctx.track(dest)

        title = str(ctx.option("title") or source.stem)
        author = str(ctx.option("author", "OpenConvert"))
        language = str(ctx.option("language", "zh-TW"))
        book_id = f"urn:uuid:{uuid.uuid4()}"
        modified = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        manifest: list[str] = []
        spine: list[str] = []
        documents: list[tuple[str, bytes]] = []
        for index, (chapter_title, chapter_body) in enumerate(chapters, start=1):
            item_id = f"chapter_{index:04d}"
            manifest.append(
                f'    <item id="{item_id}" href="{item_id}.xhtml" media-type="application/xhtml+xml"/>'
            )
            spine.append(f'    <itemref idref="{item_id}"/>')
            documents.append(
                (
                    f"OEBPS/{item_id}.xhtml",
                    _text_chapter_xhtml(chapter_title, chapter_body).encode("utf-8"),
                )
            )

        manifest.append(
            '    <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>'
        )
        nav = _nav_document(title, [chapter_title for chapter_title, _ in chapters])
        opf = _opf_document(
            book_id=book_id,
            title=title,
            author=author,
            language=language,
            modified=modified,
            manifest="\n".join(manifest),
            spine="\n".join(spine),
            cover_href=None,
        )

        try:
            with zipfile.ZipFile(dest, "w") as archive:
                archive.writestr(
                    zipfile.ZipInfo("mimetype"),
                    b"application/epub+zip",
                    compress_type=zipfile.ZIP_STORED,
                )
                archive.writestr("META-INF/container.xml", _CONTAINER, compress_type=zipfile.ZIP_DEFLATED)
                archive.writestr("OEBPS/content.opf", opf.encode("utf-8"), compress_type=zipfile.ZIP_DEFLATED)
                archive.writestr("OEBPS/nav.xhtml", nav.encode("utf-8"), compress_type=zipfile.ZIP_DEFLATED)
                for index, (path, data) in enumerate(documents):
                    ctx.check_cancel()
                    ctx.report(0.5 + index / len(documents) * 0.45, f"寫入第 {index + 1} 章")
                    archive.writestr(path, data, compress_type=zipfile.ZIP_DEFLATED)
        except OSError as exc:
            raise ConversionError(f"無法寫入 EPUB：{exc}", detail=str(exc)) from exc

        ctx.report(1.0, "完成")
        self._verify(dest)
        return [dest]

    # ------------------------------------------------------------ 檢查

    @staticmethod
    def _verify(path: Path) -> None:
        if not path.exists() or path.stat().st_size == 0:
            path.unlink(missing_ok=True)
            raise ConversionError("電子書輸出失敗，沒有產生有效檔案。")


_CONTAINER = """<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>
"""

_PAGE_STYLE = (
    "html,body{margin:0;padding:0;height:100%;}"
    "body{text-align:center;}"
    "img{max-width:100%;max-height:100%;object-fit:contain;}"
)


def _xhtml_page(title: str, image_href: str) -> str:
    safe_title = _escape(title)
    return f"""<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" xml:lang="zh-TW">
<head>
  <meta charset="utf-8"/>
  <title>{safe_title}</title>
  <style type="text/css">{_PAGE_STYLE}</style>
</head>
<body>
  <div><img src="{_escape(image_href)}" alt="{safe_title}"/></div>
</body>
</html>
"""


_TEXT_STYLE = (
    'body{font-family:"Noto Sans TC","Microsoft JhengHei","PingFang TC",serif;'
    "line-height:1.8;margin:1.2em;}"
    "h1{font-size:1.6em;line-height:1.3;margin:1em 0 0.6em;}"
    "h2{font-size:1.3em;line-height:1.3;margin:1.2em 0 0.5em;}"
    "p{margin:0 0 0.9em;text-align:justify;}"
    "blockquote{margin:0 0 0.9em;padding-left:1em;border-left:3px solid #999;}"
    "pre{white-space:pre-wrap;font-size:0.85em;}"
    "table{border-collapse:collapse;width:100%;}"
    "th,td{border:1px solid #999;padding:0.3em 0.5em;}"
)


def _text_chapter_xhtml(title: str, body: str) -> str:
    heading = "" if re.search(r"<h1[\s>]", body, re.IGNORECASE) else f"<h1>{_escape(title)}</h1>"
    return f"""<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" xml:lang="zh-TW">
<head>
  <meta charset="utf-8"/>
  <title>{_escape(title)}</title>
  <style type="text/css">{_TEXT_STYLE}</style>
</head>
<body>
{heading}
{body}
</body>
</html>
"""


def _split_chapters(body: str, fallback: str) -> list[tuple[str, str]]:
    """依 H1／H2 切成章節；沒有標題時依長度分段。"""
    for pattern in (r"(?=<h1[\s>])", r"(?=<h2[\s>])"):
        parts = [part for part in re.split(pattern, body, flags=re.IGNORECASE) if part.strip()]
        if len(parts) > 1:
            chapters: list[tuple[str, str]] = []
            for index, part in enumerate(parts, start=1):
                match = re.search(r"<h[12][^>]*>(.*?)</h[12]>", part, re.IGNORECASE | re.DOTALL)
                title = markup.html_to_text(match.group(1)) if match else ""
                chapters.append((title or f"第 {index} 章", part))
            return chapters

    heading = re.search(r"<h1[^>]*>(.*?)</h1>", body, re.IGNORECASE | re.DOTALL)
    if heading:
        title = markup.html_to_text(heading.group(1))
        return [(title or fallback, body)]

    blocks = re.split(r"(?<=</p>)", body)
    chunks: list[str] = []
    current = ""
    for block in blocks:
        if len(current) + len(block) > 30000 and current:
            chunks.append(current)
            current = ""
        current += block
    if current.strip():
        chunks.append(current)
    if len(chunks) <= 1:
        return [(fallback, body)]
    return [(f"{fallback}（{index}）", chunk) for index, chunk in enumerate(chunks, start=1)]


def _nav_document(title: str, chapter_titles: list[str] | None = None) -> str:
    safe = _escape(title)
    if chapter_titles:
        items = "\n".join(
            f'      <li><a href="chapter_{index:04d}.xhtml">{_escape(name)}</a></li>'
            for index, name in enumerate(chapter_titles, start=1)
        )
    else:
        items = '      <li><a href="page_0001.xhtml">開始閱讀</a></li>'
    return f"""<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" xml:lang="zh-TW">
<head><meta charset="utf-8"/><title>{safe}</title></head>
<body>
  <nav epub:type="toc" id="toc">
    <h1>{safe}</h1>
    <ol>
{items}
    </ol>
  </nav>
</body>
</html>
"""


def _opf_document(
    *,
    book_id: str,
    title: str,
    author: str,
    language: str,
    modified: str,
    manifest: str,
    spine: str,
    cover_href: str | None,
) -> str:
    cover_meta = '\n    <meta name="cover" content="img_0001"/>' if cover_href else ""
    return f"""<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="bookid" xml:lang="{_escape(language)}">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="bookid">{_escape(book_id)}</dc:identifier>
    <dc:title>{_escape(title)}</dc:title>
    <dc:creator>{_escape(author)}</dc:creator>
    <dc:language>{_escape(language)}</dc:language>{cover_meta}
    <meta property="dcterms:modified">{modified}</meta>
  </metadata>
  <manifest>
{manifest}
  </manifest>
  <spine>
{spine}
  </spine>
</package>
"""


def _escape(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )
