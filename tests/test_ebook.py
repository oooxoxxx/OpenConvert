"""電子書轉換測試，包含 EPUB 結構驗證。"""

from __future__ import annotations

import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from openconvert.converters.ebook import natural_key

from .helpers import run_conversion

CONTAINER_NS = "{urn:oasis:names:tc:opendocument:xmlns:container}"


def assert_valid_epub(path: Path) -> None:
    """檢查 EPUB 的必要結構：mimetype 必須是第一筆且未壓縮。"""
    assert path.exists()
    assert zipfile.is_zipfile(path)

    with zipfile.ZipFile(path) as archive:
        infos = archive.infolist()
        assert infos[0].filename == "mimetype"
        assert infos[0].compress_type == zipfile.ZIP_STORED
        assert archive.read("mimetype") == b"application/epub+zip"

        container = ET.fromstring(archive.read("META-INF/container.xml"))
        rootfile = container.find(f".//{CONTAINER_NS}rootfile")
        assert rootfile is not None
        opf_path = rootfile.get("full-path")
        assert opf_path

        opf = ET.fromstring(archive.read(opf_path))
        base = Path(opf_path).parent

        items = [node for node in opf.iter() if node.tag.endswith("item")]
        assert items, "manifest 是空的"
        for item in items:
            href = item.get("href")
            assert href
            target = str((base / href).as_posix())
            assert archive.getinfo(target) is not None, f"manifest 指到不存在的檔案：{target}"

        spine = [node for node in opf.iter() if node.tag.endswith("itemref")]
        assert spine, "spine 是空的"


def test_natural_sort_orders_numbers_correctly():
    names = ["page10.jpg", "page2.jpg", "page1.jpg"]
    assert sorted(names, key=natural_key) == ["page1.jpg", "page2.jpg", "page10.jpg"]


def test_images_to_cbz(tools, png_series: list[Path]):
    _job, outputs = run_conversion(png_series, "cbz", tools)

    assert len(outputs) == 1
    with zipfile.ZipFile(outputs[0]) as archive:
        names = archive.namelist()
    assert names == ["0001.png", "0002.png", "0003.png"]


def test_cbz_to_epub(tools, cbz_file: Path):
    _job, outputs = run_conversion([cbz_file], "epub", tools)

    assert outputs[0].suffix == ".epub"
    assert_valid_epub(outputs[0])

    with zipfile.ZipFile(outputs[0]) as archive:
        images = [n for n in archive.namelist() if n.startswith("OEBPS/images/")]
    assert len(images) == 3


def test_epub_to_cbz_roundtrip(tools, cbz_file: Path, tmp_path: Path):
    _job, epub_outputs = run_conversion([cbz_file], "epub", tools, output_dir=tmp_path / "a")
    assert_valid_epub(epub_outputs[0])

    _job, cbz_outputs = run_conversion([epub_outputs[0]], "cbz", tools, output_dir=tmp_path / "b")

    assert cbz_outputs[0].suffix == ".cbz"
    with zipfile.ZipFile(cbz_outputs[0]) as archive:
        pages = [n for n in archive.namelist() if n.lower().endswith((".png", ".jpg", ".jpeg"))]
    assert len(pages) == 3


def test_images_to_epub(tools, png_series: list[Path]):
    _job, outputs = run_conversion(png_series, "epub", tools)
    assert_valid_epub(outputs[0])


def test_epub_progress_never_goes_backwards(tools, png_series: list[Path]):
    reported: list[float] = []

    run_conversion(png_series, "epub", tools, progress=lambda fraction, *_: reported.append(fraction))

    assert reported, "轉換過程沒有任何進度回報"
    for previous, current in zip(reported, reported[1:]):
        assert current >= previous, f"進度倒退：{previous} -> {current}"
    assert reported[-1] == 1.0


def test_epub_cover_metadata_present(tools, cbz_file: Path):
    _job, outputs = run_conversion([cbz_file], "epub", tools)

    with zipfile.ZipFile(outputs[0]) as archive:
        opf = archive.read("OEBPS/content.opf").decode("utf-8")
    assert 'properties="cover-image"' in opf
    assert 'name="cover"' in opf


def test_epub_escapes_special_characters_in_title(tools, png_series: list[Path]):
    _job, outputs = run_conversion(png_series, "epub", tools, title='A & B <C> "D"')

    with zipfile.ZipFile(outputs[0]) as archive:
        opf = archive.read("OEBPS/content.opf").decode("utf-8")
    assert "&amp;" in opf
    assert "&lt;C&gt;" in opf


def test_corrupted_cbz_raises_readable_error(tools, tmp_path: Path):
    broken = tmp_path / "broken.cbz"
    broken.write_bytes(b"not a zip")

    from openconvert.core.errors import ConversionError

    with pytest.raises(ConversionError) as excinfo:
        run_conversion([broken], "epub", tools)
    assert "不是有效的 CBZ" in excinfo.value.user_message


def test_epub_without_images_is_rejected(tools, tmp_path: Path):
    path = tmp_path / "empty.epub"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("mimetype", b"application/epub+zip")
        archive.writestr("text.txt", b"hello")

    from openconvert.core.errors import ConversionError

    with pytest.raises(ConversionError):
        run_conversion([path], "cbz", tools)
