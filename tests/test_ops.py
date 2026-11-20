"""0.6.0 新增目標的測試：合併／分割／旋轉／裁切／加密／壓縮／ODS。"""

from __future__ import annotations

import json
import subprocess
import zipfile
from pathlib import Path

import pytest

from openconvert.core.errors import ConversionError, InvalidInputError

from .conftest import make_noise_wav, require_ffmpeg
from .helpers import run_conversion

# --------------------------------------------------------------------------- 樣本


def _make_clip(tools, path: Path, duration: float = 0.6) -> Path:
    require_ffmpeg(tools)
    subprocess.run(
        [
            str(tools.ffmpeg),
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"testsrc=duration={duration}:size=160x120:rate=10",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=440:duration={duration}",
            "-shortest",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            str(path),
        ],
        check=True,
    )
    return path


@pytest.fixture
def clip_a(tools, tmp_path: Path) -> Path:
    if not tools.available:
        pytest.skip("系統沒有 FFmpeg")
    return _make_clip(tools, tmp_path / "a.mp4")


@pytest.fixture
def clip_b(tools, tmp_path: Path) -> Path:
    if not tools.available:
        pytest.skip("系統沒有 FFmpeg")
    return _make_clip(tools, tmp_path / "b.mp4")


# --------------------------------------------------------------------------- 影片合併


def test_merge_videos(tools, clip_a: Path, clip_b: Path, tmp_path: Path):
    from openconvert.core.ffmpeg import probe

    require_ffmpeg(tools)
    _job, outputs = run_conversion([clip_a, clip_b], "video-merge", tools, output_dir=tmp_path / "out")

    assert outputs[0].suffix == ".mp4"
    info = probe(outputs[0], tools)
    assert info.video_stream is not None
    assert 0.9 <= info.duration <= 1.6


def test_merge_videos_requires_two(tools, clip_a: Path):
    with pytest.raises(InvalidInputError):
        run_conversion([clip_a], "video-merge", tools)


def test_split_video(tools, clip_a: Path, tmp_path: Path):
    from openconvert.core.ffmpeg import probe

    require_ffmpeg(tools)
    _job, outputs = run_conversion(
        [clip_a],
        "video-split",
        tools,
        output_dir=tmp_path / "out",
        split_start="0.1",
        split_end="0.4",
    )

    info = probe(outputs[0], tools)
    assert 0.05 <= info.duration <= 0.5


def test_split_video_rejects_bad_range(tools, clip_a: Path):
    require_ffmpeg(tools)
    with pytest.raises(InvalidInputError):
        run_conversion([clip_a], "video-split", tools, split_start="0.4", split_end="0.1")
    with pytest.raises(InvalidInputError):
        run_conversion([clip_a], "video-split", tools, split_start="0", split_end="999")


def test_rotate_video_swaps_dimensions(tools, clip_a: Path, tmp_path: Path):
    from openconvert.core.ffmpeg import probe

    require_ffmpeg(tools)
    _job, outputs = run_conversion(
        [clip_a], "video-rotate", tools, output_dir=tmp_path / "out", rotate_mode="90"
    )

    info = probe(outputs[0], tools)
    assert info.video_stream is not None
    assert (info.video_stream.width, info.video_stream.height) == (120, 160)


# --------------------------------------------------------------------------- 音訊合併


def test_merge_audio(tools, tmp_path: Path):
    from openconvert.core.ffmpeg import probe

    require_ffmpeg(tools)
    first = make_noise_wav(tmp_path / "one.wav")
    second = make_noise_wav(tmp_path / "two.wav")

    _job, outputs = run_conversion([first, second], "audio-merge", tools, output_dir=tmp_path / "out")

    assert outputs[0].suffix == ".mp3"
    info = probe(outputs[0], tools)
    assert info.audio_stream is not None
    assert 0.7 <= info.duration <= 1.5


# --------------------------------------------------------------------------- 圖片操作


def test_rotate_image(tools, png_file: Path, tmp_path: Path):
    from PIL import Image

    _job, outputs = run_conversion(
        [png_file], "img-rotate", tools, output_dir=tmp_path / "out", rotate_degrees=90
    )

    with Image.open(outputs[0]) as image:
        assert image.size == (60, 80)


def test_flip_image(tools, png_file: Path, tmp_path: Path):
    from PIL import Image

    _job, outputs = run_conversion([png_file], "img-flip", tools, output_dir=tmp_path / "out", flip_axis="h")

    with Image.open(png_file) as original, Image.open(outputs[0]) as flipped:
        assert flipped.size == original.size
        # 水平翻轉後，左右邊緣像素應互換
        assert flipped.getpixel((0, 0)) == original.getpixel((original.width - 1, 0))


def test_crop_image_to_ratio(tools, png_file: Path, tmp_path: Path):
    from PIL import Image

    _job, outputs = run_conversion(
        [png_file], "img-crop", tools, output_dir=tmp_path / "out", crop_ratio="1:1"
    )
    with Image.open(outputs[0]) as image:
        assert image.size == (60, 60)

    _job, outputs = run_conversion(
        [png_file], "img-crop", tools, output_dir=tmp_path / "out2", crop_ratio="16:9"
    )
    with Image.open(outputs[0]) as image:
        assert image.size == (80, 45)


def test_crop_rejects_bad_ratio(tools, png_file: Path):
    with pytest.raises(ConversionError):
        run_conversion([png_file], "img-crop", tools, crop_ratio="abc")


# --------------------------------------------------------------------------- PDF 加密／壓縮


def test_pdf_encrypt_and_decrypt(tools, pdf_file: Path, tmp_path: Path):
    from pypdf import PdfReader

    _job, encrypted = run_conversion(
        [pdf_file], "pdf-encrypt", tools, output_dir=tmp_path / "a", pdf_password="test123"
    )

    reader = PdfReader(str(encrypted[0]))
    assert reader.is_encrypted
    assert reader.decrypt("wrong") == 0
    assert reader.decrypt("test123") != 0

    _job, decrypted = run_conversion(
        [encrypted[0]], "pdf-decrypt", tools, output_dir=tmp_path / "b", pdf_password="test123"
    )

    plain = PdfReader(str(decrypted[0]))
    assert not plain.is_encrypted
    assert len(plain.pages) == 3


def test_pdf_encrypt_requires_password(tools, pdf_file: Path):
    with pytest.raises(InvalidInputError):
        run_conversion([pdf_file], "pdf-encrypt", tools, pdf_password="")


def test_pdf_decrypt_wrong_password(tools, pdf_file: Path, tmp_path: Path):
    _job, encrypted = run_conversion(
        [pdf_file], "pdf-encrypt", tools, output_dir=tmp_path / "a", pdf_password="test123"
    )
    with pytest.raises(ConversionError):
        run_conversion(
            [encrypted[0]],
            "pdf-decrypt",
            tools,
            output_dir=tmp_path / "b",
            pdf_password="wrong-password",
        )


def test_pdf_compress_keeps_pages(tools, pdf_file: Path, tmp_path: Path):
    from pypdf import PdfReader

    before = pdf_file.stat().st_size
    _job, outputs = run_conversion([pdf_file], "pdf-compress", tools, output_dir=tmp_path / "out")

    reader = PdfReader(str(outputs[0]))
    assert len(reader.pages) == 3
    assert outputs[0].stat().st_size > 0
    # 壓縮不該把檔案變成空的；已最佳化的檔案不一定變小
    assert before > 0


# --------------------------------------------------------------------------- ODS


def _write_ods(path: Path, sheets: dict[str, list[list[object]]]) -> None:
    """手寫一個最小的 ODS（ZIP + content.xml），不需要 LibreOffice。"""
    tables = []
    for name, rows in sheets.items():
        rows_xml = []
        for row in rows:
            cells_xml = []
            for cell in row:
                if isinstance(cell, (int, float)) and not isinstance(cell, bool):
                    cells_xml.append(
                        f'<table:table-cell office:value-type="float" office:value="{cell}">'
                        f"<text:p>{cell}</text:p></table:table-cell>"
                    )
                else:
                    cells_xml.append(
                        "<table:table-cell office:value-type='string'>"
                        f"<text:p>{cell}</text:p></table:table-cell>"
                    )
            rows_xml.append("<table:table-row>" + "".join(cells_xml) + "</table:table-row>")
        tables.append(f'<table:table table:name="{name}">' + "".join(rows_xml) + "</table:table>")

    content = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<office:document-content "
        'xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" '
        'xmlns:table="urn:oasis:names:tc:opendocument:xmlns:table:1.0" '
        'xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0">'
        f"<office:body><office:spreadsheet>{''.join(tables)}</office:spreadsheet></office:body>"
        "</office:document-content>"
    )
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("mimetype", "application/vnd.oasis.opendocument.spreadsheet")
        archive.writestr("content.xml", content)


def test_ods_to_json(tmp_path: Path, tools):
    ods = tmp_path / "data.ods"
    _write_ods(ods, {"成績": [["name", "score"], ["Alice", 90], ["Bob", 85.5]]})

    _job, outputs = run_conversion([ods], "data-json", tools, output_dir=tmp_path / "out")

    data = json.loads(outputs[0].read_text(encoding="utf-8"))
    assert data == [
        {"name": "Alice", "score": 90.0},
        {"name": "Bob", "score": 85.5},
    ]


def test_ods_sheet_selection(tmp_path: Path, tools):
    ods = tmp_path / "book.ods"
    _write_ods(
        ods,
        {
            "第一表": [["a", "b"], ["1", "2"]],
            "第二表": [["x", "y"], ["9", "8"]],
        },
    )

    _job, outputs = run_conversion([ods], "data-json", tools, output_dir=tmp_path / "out", sheet="第二表")

    data = json.loads(outputs[0].read_text(encoding="utf-8"))
    assert data == [{"x": "9", "y": "8"}]


def test_ods_to_csv_roundtrip(tmp_path: Path, tools):
    ods = tmp_path / "data.ods"
    _write_ods(ods, {"表": [["name", "age"], ["Alice", "30"]]})

    _job, outputs = run_conversion([ods], "data-csv", tools, output_dir=tmp_path / "out")

    text = outputs[0].read_text(encoding="utf-8-sig")
    assert text.splitlines()[0] == "name,age"
    assert "Alice,30" in text
