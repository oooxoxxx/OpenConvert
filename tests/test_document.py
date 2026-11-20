"""文件轉換測試：Markdown／HTML／DOCX 與 LibreOffice 排版。"""

from __future__ import annotations

from pathlib import Path

import pytest
from pypdf import PdfReader

from openconvert.core.errors import UnsupportedFormatError

from .conftest import require_office
from .helpers import run_conversion


def test_markdown_to_html(tools, md_file: Path, tmp_path: Path):
    _job, outputs = run_conversion([md_file], "md-html", tools, output_dir=tmp_path / "out")

    text = outputs[0].read_text(encoding="utf-8")
    assert "<h1" in text and "主標題" in text
    assert "<strong>粗體</strong>" in text
    assert "<table>" in text
    assert "<!DOCTYPE html>" in text


def test_html_to_markdown(tools, html_file: Path, tmp_path: Path):
    _job, outputs = run_conversion([html_file], "html-md", tools, output_dir=tmp_path / "out")

    text = outputs[0].read_text(encoding="utf-8")
    assert "# 標題" in text
    assert "- 甲" in text
    assert "| A | B |" in text


def test_html_to_text(tools, html_file: Path, tmp_path: Path):
    _job, outputs = run_conversion([html_file], "html-txt", tools, output_dir=tmp_path / "out")

    text = outputs[0].read_text(encoding="utf-8")
    assert "標題" in text
    assert "<" not in text


def test_docx_to_markdown(tools, docx_file: Path, tmp_path: Path):
    _job, outputs = run_conversion([docx_file], "docx-md", tools, output_dir=tmp_path / "out")

    text = outputs[0].read_text(encoding="utf-8")
    assert "# 報告標題" in text
    assert "**粗體**" in text
    assert "- 項目一" in text
    assert "| A | B |" in text


def test_docx_to_text(tools, docx_file: Path, tmp_path: Path):
    _job, outputs = run_conversion([docx_file], "docx-txt", tools, output_dir=tmp_path / "out")

    text = outputs[0].read_text(encoding="utf-8")
    assert "報告標題" in text
    assert "**" not in text  # 純文字不應有 Markdown 標記


def test_docx_to_html(tools, docx_file: Path, tmp_path: Path):
    _job, outputs = run_conversion([docx_file], "docx-html", tools, output_dir=tmp_path / "out")
    assert "<h1" in outputs[0].read_text(encoding="utf-8")


def test_wrong_source_extension_is_rejected(tools, docx_file: Path):
    with pytest.raises(UnsupportedFormatError):
        run_conversion([docx_file], "md-html", tools)


def test_markdown_to_docx(tools, office_tools, md_file: Path, tmp_path: Path):
    from docx import Document as ReadDocx

    require_office(office_tools)
    _job, outputs = run_conversion([md_file], "md-docx", tools, output_dir=tmp_path / "out")

    document = ReadDocx(str(outputs[0]))
    text = "\n".join(p.text for p in document.paragraphs)
    assert "主標題" in text


def test_html_to_docx(tools, office_tools, html_file: Path, tmp_path: Path):
    require_office(office_tools)
    _job, outputs = run_conversion([html_file], "html-docx", tools, output_dir=tmp_path / "out")

    from docx import Document as ReadDocx

    document = ReadDocx(str(outputs[0]))
    text = "\n".join(p.text for p in document.paragraphs)
    assert "標題" in text


def test_text_to_epub_is_handled_by_ebook_converter(tools, txt_file: Path, tmp_path: Path):
    # txt-pdf 需要 LibreOffice，但 epub 的入口在電子書轉換器
    _job, outputs = run_conversion([txt_file], "epub", tools, output_dir=tmp_path / "out")
    assert outputs[0].suffix == ".epub"


# --------------------------------------------------------------------------- LibreOffice


def test_docx_to_pdf(tools, office_tools, docx_file: Path, tmp_path: Path):
    require_office(office_tools)
    _job, outputs = run_conversion([docx_file], "docx-pdf", tools, output_dir=tmp_path / "out")

    reader = PdfReader(str(outputs[0]))
    assert len(reader.pages) >= 1
    assert "報告" in (reader.pages[0].extract_text() or "")


def test_markdown_to_pdf(tools, office_tools, md_file: Path, tmp_path: Path):
    require_office(office_tools)
    _job, outputs = run_conversion([md_file], "md-pdf", tools, output_dir=tmp_path / "out")

    reader = PdfReader(str(outputs[0]))
    assert len(reader.pages) >= 1


def test_xlsx_to_pdf(tools, office_tools, xlsx_file: Path, tmp_path: Path):
    require_office(office_tools)
    _job, outputs = run_conversion([xlsx_file], "xlsx-pdf", tools, output_dir=tmp_path / "out")
    assert outputs[0].suffix == ".pdf"


def test_missing_libreoffice_gives_readable_error(tools, docx_file: Path, tmp_path: Path):
    from openconvert.converters.base import ConvertContext
    from openconvert.converters.document import DocumentConverter
    from openconvert.core.errors import ConversionError
    from openconvert.core.job import Job
    from openconvert.core.office import OfficeTools
    from openconvert.core.targets import target_by_token

    spec = target_by_token("docx-pdf")
    assert spec is not None
    job = Job.create([docx_file], spec, {})
    job.start()
    ctx = ConvertContext(
        job=job,
        output_dir=tmp_path,
        overwrite=False,
        tools=tools,
        progress=lambda *_args: None,
        office=OfficeTools(soffice=None),
    )

    with pytest.raises(ConversionError) as excinfo:
        DocumentConverter().convert(ctx)
    assert "找不到 LibreOffice" in excinfo.value.user_message
