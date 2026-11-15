"""圖片轉換整合測試：真的產生檔案並驗證內容。"""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from openconvert.core.errors import ConversionError, UnsupportedFormatError

from .helpers import run_conversion


def test_png_to_jpg(tools, png_file: Path, tmp_path: Path):
    job, outputs = run_conversion([png_file], "jpg", tools, output_dir=tmp_path / "out")

    assert job.status.value == "done"
    assert len(outputs) == 1
    assert outputs[0].suffix == ".jpg"
    assert outputs[0].exists()

    with Image.open(outputs[0]) as image:
        assert image.format == "JPEG"
        assert image.size == (80, 60)
        assert image.mode == "RGB"


def test_source_file_is_never_modified(tools, png_file: Path):
    before = png_file.read_bytes()
    run_conversion([png_file], "webp", tools)
    assert png_file.read_bytes() == before


def test_alpha_is_flattened_to_white_for_jpeg(tools, rgba_png_file: Path):
    _job, outputs = run_conversion([rgba_png_file], "jpg", tools)

    with Image.open(outputs[0]) as image:
        assert image.mode == "RGB"
        corner = image.getpixel((35, 35))
        assert all(channel >= 250 for channel in corner)


def test_resize_limits_longest_edge(tools, png_file: Path):
    _job, outputs = run_conversion([png_file], "png", tools, max_dimension=40)

    with Image.open(outputs[0]) as image:
        assert image.size == (40, 30)


def test_resize_does_not_upscale(tools, png_file: Path):
    _job, outputs = run_conversion([png_file], "png", tools, max_dimension=2000)

    with Image.open(outputs[0]) as image:
        assert image.size == (80, 60)


@pytest.mark.parametrize(
    "token,expected",
    [
        ("webp", "WEBP"),
        ("bmp", "BMP"),
        ("tiff", "TIFF"),
        ("image-gif", "GIF"),
        ("ico", "ICO"),
    ],
)
def test_multiple_target_formats(tools, png_file: Path, token: str, expected: str):
    _job, outputs = run_conversion([png_file], token, tools)
    with Image.open(outputs[0]) as image:
        assert image.format == expected


def test_existing_output_is_not_overwritten(tools, png_file: Path, tmp_path: Path):
    out = tmp_path / "out"
    _job, first = run_conversion([png_file], "jpg", tools, output_dir=out)
    first[0].write_bytes(b"keep me")

    _job, second = run_conversion([png_file], "jpg", tools, output_dir=out)

    assert second[0] != first[0]
    assert second[0].name == "sample (1).jpg"
    assert first[0].read_bytes() == b"keep me"


def test_images_to_single_pdf(tools, png_series: list[Path], tmp_path: Path):
    from pypdf import PdfReader

    _job, outputs = run_conversion(png_series, "img-pdf", tools, output_dir=tmp_path / "out")

    assert len(outputs) == 1
    assert outputs[0].suffix == ".pdf"
    reader = PdfReader(str(outputs[0]))
    assert len(reader.pages) == 3


def test_corrupted_image_raises_readable_error(tools, tmp_path: Path):
    broken = tmp_path / "broken.png"
    broken.write_bytes(b"not really a png")

    with pytest.raises(ConversionError) as excinfo:
        run_conversion([broken], "jpg", tools)

    assert "無法讀取圖片" in excinfo.value.user_message


def test_text_file_is_rejected(tools, tmp_path: Path):
    text = tmp_path / "note.txt"
    text.write_text("hello", encoding="utf-8")

    with pytest.raises(UnsupportedFormatError):
        run_conversion([text], "jpg", tools)


def test_failed_conversion_leaves_no_partial_file(tools, tmp_path: Path):
    broken = tmp_path / "broken.jpg"
    broken.write_bytes(b"\xff\xd8this is not a jpeg")

    with pytest.raises(ConversionError):
        run_conversion([broken], "png", tools)

    assert not (tmp_path / "broken.png").exists()
