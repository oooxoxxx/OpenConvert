"""文件轉換：Markdown、HTML、DOCX 與 Office 格式。

純文字與 Markdown／HTML 之間的轉換由本專案直接完成；需要完整排版
（DOCX → PDF、PPTX → PDF…）時才呼叫外部的 LibreOffice。
"""

from __future__ import annotations

import re
import tempfile
from pathlib import Path

from ..core import office
from ..core.errors import ConversionError, UnsupportedFormatError
from ..core.textio import read_text, write_text
from . import markup
from .base import ConvertContext, Converter

MARKDOWN_EXTENSIONS = frozenset({"md", "markdown"})
HTML_EXTENSIONS = frozenset({"html", "htm"})

#: token → (LibreOffice 目標副檔名, 可接受的來源副檔名)
OFFICE_TARGETS: dict[str, tuple[str, frozenset[str]]] = {
    "docx-pdf": ("pdf", frozenset({"docx"})),
    "doc-pdf": ("pdf", frozenset({"doc"})),
    "doc-docx": ("docx", frozenset({"doc"})),
    "docx-odt": ("odt", frozenset({"docx"})),
    "odt-docx": ("docx", frozenset({"odt"})),
    "odt-pdf": ("pdf", frozenset({"odt"})),
    "rtf-pdf": ("pdf", frozenset({"rtf"})),
    "pptx-pdf": ("pdf", frozenset({"pptx"})),
    "odp-pdf": ("pdf", frozenset({"odp"})),
    "xlsx-pdf": ("pdf", frozenset({"xlsx", "xlsm"})),
    "xls-pdf": ("pdf", frozenset({"xls"})),
    "xls-xlsx": ("xlsx", frozenset({"xls"})),
    "xlsx-ods": ("ods", frozenset({"xlsx", "xlsm"})),
    "ods-xlsx": ("xlsx", frozenset({"ods"})),
    "ods-pdf": ("pdf", frozenset({"ods"})),
}

_PLAIN_STYLE = (
    "pre.plain{white-space:pre-wrap;word-wrap:break-word;"
    'font-family:"Cascadia Code",Consolas,"Courier New",monospace;'
    "font-size:11pt;line-height:1.55;margin:0;}"
)


def _require_ext(ctx: ConvertContext, allowed: frozenset[str]) -> str:
    extension = ctx.source.suffix.lstrip(".").lower()
    if extension not in allowed:
        expected = "、".join(sorted(allowed))
        raise UnsupportedFormatError(
            f"「{ctx.source.name}」不是 {ctx.job.target.label} 支援的來源格式（需要 {expected}）。"
        )
    return extension


# --------------------------------------------------------------------------- DOCX


def _docx_document(path: Path):
    try:
        from docx import Document
    except ImportError as exc:  # pragma: no cover - 依賴缺失
        raise ConversionError("缺少 python-docx，無法讀取 Word 文件。") from exc

    try:
        return Document(str(path))
    except Exception as exc:  # python-docx 的例外種類很多
        raise ConversionError(
            f"無法讀取「{path.name}」，檔案可能已損毀或不是有效的 DOCX。",
            detail=str(exc),
        ) from exc


def _iter_docx_blocks(document):
    from docx.oxml.ns import qn
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    for child in document.element.body.iterchildren():
        if child.tag == qn("w:p"):
            yield Paragraph(child, document)
        elif child.tag == qn("w:tbl"):
            yield Table(child, document)


def _paragraph_style(paragraph) -> str:
    try:
        return (paragraph.style.name or "").lower()
    except AttributeError:  # pragma: no cover - 缺少樣式時
        return ""


def _paragraph_markdown(paragraph) -> str:
    pieces: list[str] = []
    for run in paragraph.runs:
        text = run.text
        if not text:
            continue
        if run.bold and run.italic:
            text = f"***{text}***"
        elif run.bold:
            text = f"**{text}**"
        elif run.italic:
            text = f"*{text}*"
        pieces.append(text)
    text = "".join(pieces).strip() or paragraph.text.strip()
    if not text:
        return ""

    style = _paragraph_style(paragraph)
    if style.startswith("heading"):
        match = re.search(r"(\d+)", style)
        level = min(6, max(1, int(match.group(1)))) if match else 1
        return f"{'#' * level} {text}"
    if style == "title":
        return f"# {text}"
    if "list bullet" in style:
        return f"- {text}"
    if "list number" in style:
        return f"1. {text}"
    if "quote" in style:
        return f"> {text}"
    return text


def _table_rows(table) -> list[list[str]]:
    rows: list[list[str]] = []
    for row in table.rows:
        rows.append([cell.text.replace("\n", " ").strip() for cell in row.cells])
    return rows


def _table_markdown(table) -> str:
    rows = _table_rows(table)
    if not rows:
        return ""
    header = rows[0]
    body = rows[1:]
    lines = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join("---" for _ in header) + " |",
    ]
    for row in body:
        padded = row + [""] * (len(header) - len(row))
        lines.append("| " + " | ".join(padded[: len(header)]) + " |")
    return "\n".join(lines)


def docx_to_markdown(path: Path) -> str:
    document = _docx_document(path)
    parts: list[str] = []
    list_buffer: list[str] = []

    def flush() -> None:
        if list_buffer:
            parts.append("\n".join(list_buffer))
            list_buffer.clear()

    for block in _iter_docx_blocks(document):
        if hasattr(block, "rows"):
            flush()
            table = _table_markdown(block)
            if table:
                parts.append(table)
            continue

        style = _paragraph_style(block)
        text = _paragraph_markdown(block)
        if not text:
            continue
        if "list bullet" in style or "list number" in style:
            list_buffer.append(text)
        else:
            flush()
            parts.append(text)
    flush()
    return "\n\n".join(parts).strip() + "\n"


def docx_to_text(path: Path) -> str:
    document = _docx_document(path)
    lines: list[str] = []
    for block in _iter_docx_blocks(document):
        if hasattr(block, "rows"):
            for row in _table_rows(block):
                if any(cell for cell in row):
                    lines.append("\t".join(row))
            continue
        text = block.text.strip()
        if text:
            lines.append(text)
    return "\n".join(lines).strip() + "\n"


# --------------------------------------------------------------------------- 主流程


class DocumentConverter(Converter):
    name = "document"

    def convert(self, ctx: ConvertContext) -> list[Path]:
        self.ensure_source_exists(ctx)
        self.ensure_kind(ctx, {kind.value for kind in ctx.job.target.kinds})

        token = ctx.token
        source = ctx.source

        if token == "md-html":
            _require_ext(ctx, MARKDOWN_EXTENSIONS)
            body = markup.markdown_to_html(read_text(source))
            return self._write_html(ctx, markup.html_document(body, source.stem))

        if token == "html-md":
            _require_ext(ctx, HTML_EXTENSIONS)
            return self._write_text(ctx, markup.html_to_markdown(read_text(source)))

        if token == "html-txt":
            _require_ext(ctx, HTML_EXTENSIONS)
            return self._write_text(ctx, markup.html_to_text(read_text(source)))

        if token == "docx-txt":
            _require_ext(ctx, frozenset({"docx"}))
            return self._write_text(ctx, docx_to_text(source))

        if token == "docx-md":
            _require_ext(ctx, frozenset({"docx"}))
            return self._write_text(ctx, docx_to_markdown(source))

        if token == "docx-html":
            _require_ext(ctx, frozenset({"docx"}))
            body = markup.markdown_to_html(docx_to_markdown(source))
            return self._write_html(ctx, markup.html_document(body, source.stem))

        if token == "md-docx":
            _require_ext(ctx, MARKDOWN_EXTENSIONS)
            body = markup.markdown_to_html(read_text(source))
            return self._office_from_html(ctx, "docx", body)

        if token == "html-docx":
            _require_ext(ctx, HTML_EXTENSIONS)
            raw = read_text(source)
            return self._office_from_html(ctx, "docx", markup.html_body(raw), markup.html_styles(raw))

        if token == "md-pdf":
            _require_ext(ctx, MARKDOWN_EXTENSIONS)
            body = markup.markdown_to_html(read_text(source))
            return self._html_to_pdf(ctx, body)

        if token == "html-pdf":
            _require_ext(ctx, HTML_EXTENSIONS)
            raw = read_text(source)
            return self._html_to_pdf(ctx, markup.html_body(raw), markup.html_styles(raw))

        if token == "txt-pdf":
            _require_ext(ctx, frozenset({"txt"}))
            body = f'<pre class="plain">{markup.escape(read_text(source))}</pre>'
            return self._html_to_pdf(ctx, body, f"<style>{_PLAIN_STYLE}</style>")

        office_target = OFFICE_TARGETS.get(token)
        if office_target is not None:
            target_extension, allowed = office_target
            _require_ext(ctx, allowed)
            return self._office_convert(ctx, target_extension)

        raise ConversionError(f"不支援的文件目標：{token}")  # pragma: no cover

    # ------------------------------------------------------------ 輸出

    def _write_text(self, ctx: ConvertContext, content: str) -> list[Path]:
        ctx.report(0.7, "寫入檔案")
        dest = ctx.resolve_output(ctx.source, ctx.job.target.extension)
        ctx.track(dest)
        write_text(dest, content)
        return self._finish(ctx, dest)

    def _write_html(self, ctx: ConvertContext, content: str) -> list[Path]:
        ctx.report(0.7, "寫入 HTML")
        dest = ctx.resolve_output(ctx.source, ctx.job.target.extension)
        ctx.track(dest)
        write_text(dest, content)
        return self._finish(ctx, dest)

    def _office_convert(self, ctx: ConvertContext, extension: str) -> list[Path]:
        tools = ctx.office_tools()
        if not tools.available:
            raise ConversionError(
                "找不到 LibreOffice。這項轉換需要 LibreOffice，請安裝後重新啟動，"
                "或在「設定」中指定 soffice 路徑。"
            )

        source = ctx.source
        dest = ctx.resolve_output(source, extension)
        ctx.track(dest)

        ctx.report(0.05, "啟動 LibreOffice")
        office.convert_to(tools, source, dest, extension)
        return self._finish(ctx, dest)

    def _html_to_pdf(self, ctx: ConvertContext, body: str, extra_head: str = "") -> list[Path]:
        return self._office_from_html(ctx, "pdf", body, extra_head)

    def _office_from_html(
        self,
        ctx: ConvertContext,
        extension: str,
        body: str,
        extra_head: str = "",
    ) -> list[Path]:
        """把 HTML 內容交給 LibreOffice 排版成指定格式（pdf／docx…）。

        HTML 在 LibreOffice 屬於 Writer/Web 模組，匯出 DOCX 必須明確指定
        ``MS Word 2007 XML`` 濾器，否則會出現「no export filter」。
        """
        tools = ctx.office_tools()
        if not tools.available:
            raise ConversionError(
                "找不到 LibreOffice。這項轉換需要 LibreOffice 排版，請安裝後重新啟動，"
                "或在「設定」中指定 soffice 路徑。"
            )

        source = ctx.source
        dest = ctx.resolve_output(source, extension)
        ctx.track(dest)

        filter_name = "MS Word 2007 XML" if extension.lower() == "docx" else ""
        ctx.report(0.05, "排版中")
        with tempfile.TemporaryDirectory(prefix="openconvert-doc-") as folder:
            html_path = Path(folder) / f"{source.stem or 'document'}.html"
            write_text(html_path, markup.html_document(body, source.stem, extra_head))
            office.convert_to(tools, html_path, dest, extension, filter_name=filter_name)
        return self._finish(ctx, dest)

    @staticmethod
    def _finish(ctx: ConvertContext, dest: Path) -> list[Path]:
        ctx.report(1.0, "完成")
        if not dest.exists() or dest.stat().st_size == 0:
            dest.unlink(missing_ok=True)
            raise ConversionError("文件轉換失敗，沒有產生有效檔案。")
        return [dest]


__all__ = ["DocumentConverter", "docx_to_markdown", "docx_to_text"]
