"""輸出路徑規劃的單元測試。"""

from __future__ import annotations

from pathlib import Path

from openconvert.core.paths import (
    human_size,
    resolve_output,
    resolve_output_dir,
    sanitize_stem,
    unique_dir,
    unique_path,
)


def test_sanitize_stem_replaces_illegal_characters():
    assert sanitize_stem("a/b:c*d?") == "a_b_c_d_"


def test_sanitize_stem_handles_empty_and_dots():
    assert sanitize_stem("   ") == "output"
    assert sanitize_stem("...") == "output"


def test_sanitize_stem_escapes_windows_reserved_names():
    assert sanitize_stem("CON") == "_CON"
    assert sanitize_stem("lpt1") == "_lpt1"


def test_unique_path_returns_same_when_absent(tmp_path: Path):
    candidate = tmp_path / "file.png"
    assert unique_path(candidate) == candidate


def test_unique_path_increments_until_free(tmp_path: Path):
    target = tmp_path / "file.png"
    target.write_bytes(b"x")
    assert unique_path(target) == tmp_path / "file (1).png"

    (tmp_path / "file (1).png").write_bytes(b"x")
    assert unique_path(target) == tmp_path / "file (2).png"


def test_unique_dir_increments(tmp_path: Path):
    target = tmp_path / "pages"
    target.mkdir()
    assert unique_dir(target) == tmp_path / "pages (1)"


def test_resolve_output_never_overwrites_source(tmp_path: Path):
    source = tmp_path / "photo.png"
    source.write_bytes(b"original")

    result = resolve_output(source, None, "png")

    assert result != source
    assert result.name == "photo_converted.png"
    assert source.read_bytes() == b"original"


def test_resolve_output_creates_unique_name_when_exists(tmp_path: Path):
    source = tmp_path / "photo.png"
    source.write_bytes(b"x")
    existing = tmp_path / "photo.jpg"
    existing.write_bytes(b"old")

    result = resolve_output(source, None, "jpg")

    assert result == tmp_path / "photo (1).jpg"
    assert existing.read_bytes() == b"old"


def test_resolve_output_overwrite_reuses_name(tmp_path: Path):
    source = tmp_path / "photo.png"
    source.write_bytes(b"x")
    existing = tmp_path / "photo.jpg"
    existing.write_bytes(b"old")

    result = resolve_output(source, None, "jpg", overwrite=True)

    assert result == existing


def test_resolve_output_uses_custom_directory(tmp_path: Path):
    source = tmp_path / "in" / "photo.png"
    source.parent.mkdir()
    source.write_bytes(b"x")
    out = tmp_path / "out"

    result = resolve_output(source, out, "webp")

    assert result.parent == out
    assert out.is_dir()


def test_resolve_output_dir_is_fresh_directory(tmp_path: Path):
    source = tmp_path / "doc.pdf"
    source.write_bytes(b"x")
    (tmp_path / "doc_pages").mkdir()

    result = resolve_output_dir(source, None, "doc_pages")

    assert result == tmp_path / "doc_pages (1)"
    assert not result.exists()


def test_human_size_formats_units():
    assert human_size(512) == "512 B"
    assert human_size(2048) == "2.0 KB"
    assert human_size(5 * 1024 * 1024) == "5.0 MB"
