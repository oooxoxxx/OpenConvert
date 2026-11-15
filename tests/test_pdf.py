"""PDF 處理測試。"""

from __future__ import annotations

from pathlib import Path

import pytest
from pypdf import PdfReader

from openconvert.converters.pdf import parse_page_ranges
from openconvert.core.errors import InvalidInputError

from .helpers import run_conversion

# --------------------------------------------------------------------------- 頁碼解析


def test_parse_all_pages_when_blank():
    assert parse_page_ranges("", 4) == [0, 1, 2, 3]


def test_parse_single_range():
    assert parse_page_ranges("2-4", 5) == [1, 2, 3]


def test_parse_mixed_ranges_and_single_pages():
    assert parse_page_ranges("1-2,4", 5) == [0, 1, 3]


def test_parse_open_ended_range():
    assert parse_page_ranges("3-", 5) == [2, 3, 4]


def test_parse_leading_range():
    assert parse_page_ranges("-2", 5) == [0, 1]


def test_parse_reversed_range_is_normalized():
    assert parse_page_ranges("4-2", 5) == [1, 2, 3]


def test_parse_removes_duplicates():
    assert parse_page_ranges("1,1,2", 5) == [0, 1]


def test_parse_rejects_out_of_range():
    with pytest.raises(InvalidInputError):
        parse_page_ranges("9", 3)


def test_parse_rejects_garbage():
    with pytest.raises(InvalidInputError):
        parse_page_ranges("abc", 3)


def test_parse_rejects_zero():
    with pytest.raises(InvalidInputError):
        parse_page_ranges("0", 3)


# --------------------------------------------------------------------------- 合併


def test_merge_two_pdfs(tools, pdf_file: Path, second_pdf_file: Path, tmp_path: Path):
    job, outputs = run_conversion(
        [pdf_file, second_pdf_file], "pdf-merge", tools, output_dir=tmp_path / "out"
    )

    assert len(outputs) == 1
    reader = PdfReader(str(outputs[0]))
    assert len(reader.pages) == 5
    assert job.status.value == "done"


def test_merge_requires_two_files(tools, pdf_file: Path):
    with pytest.raises(InvalidInputError):
        run_conversion([pdf_file], "pdf-merge", tools)


# --------------------------------------------------------------------------- 抽頁


def test_extract_selected_pages(tools, pdf_file: Path):
    _job, outputs = run_conversion([pdf_file], "pdf-extract", tools, pages="1,3")

    reader = PdfReader(str(outputs[0]))
    assert len(reader.pages) == 2


def test_extract_keeps_source_untouched(tools, pdf_file: Path):
    before = pdf_file.read_bytes()
    run_conversion([pdf_file], "pdf-extract", tools, pages="2")
    assert pdf_file.read_bytes() == before


# --------------------------------------------------------------------------- 點陣化


@pytest.mark.parametrize("token,extension", [("pdf-png", "png"), ("pdf-jpg", "jpg")])
def test_pdf_to_images(tools, pdf_file: Path, tmp_path: Path, token: str, extension: str):
    _job, outputs = run_conversion([pdf_file], token, tools, output_dir=tmp_path / "out", dpi=72)

    assert len(outputs) == 3
    assert all(path.suffix == f".{extension}" for path in outputs)
    assert outputs[0].parent.name == "doc_pages"

    from PIL import Image

    with Image.open(outputs[0]) as image:
        assert image.width > 0
        assert image.height > 0


def test_corrupted_pdf_raises_readable_error(tools, tmp_path: Path):
    broken = tmp_path / "broken.pdf"
    broken.write_bytes(b"%PDF-1.4 this is broken")

    from openconvert.core.errors import ConversionError

    with pytest.raises(ConversionError):
        run_conversion([broken], "pdf-png", tools)


# --------------------------------------------------------------------------- 轉 CBZ


def test_pdf_to_cbz(tools, pdf_file: Path, tmp_path: Path):
    import zipfile

    _job, outputs = run_conversion([pdf_file], "pdf-cbz", tools, output_dir=tmp_path / "out", dpi=72)

    assert outputs[0].suffix == ".cbz"
    with zipfile.ZipFile(outputs[0]) as archive:
        names = archive.namelist()
    assert len(names) == 3
    assert names[0] == "page_0001.jpg"


# --------------------------------------------------------------------------- 抽文字


def test_pdf_without_text_layer_raises(tools, pdf_file: Path):
    from openconvert.core.errors import ConversionError

    with pytest.raises(ConversionError) as excinfo:
        run_conversion([pdf_file], "pdf-txt", tools)
    assert "沒有可抽取的文字層" in excinfo.value.user_message


def test_pdf_with_text_layer_extracts_text(tools, office_tools, docx_file: Path, tmp_path: Path):
    from .conftest import require_office

    require_office(office_tools)

    _job, pdf_outputs = run_conversion([docx_file], "docx-pdf", tools, output_dir=tmp_path / "a")
    _job, outputs = run_conversion([pdf_outputs[0]], "pdf-txt", tools, output_dir=tmp_path / "b")

    assert "報告" in outputs[0].read_text(encoding="utf-8")
