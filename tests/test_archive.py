"""封裝（ZIP／tar.gz）測試。"""

from __future__ import annotations

import tarfile
import zipfile
from pathlib import Path

from .helpers import run_conversion


def test_zip_groups_all_files(tools, png_file: Path, csv_file: Path, tmp_path: Path):
    _job, outputs = run_conversion([png_file, csv_file], "zip", tools, output_dir=tmp_path / "out")

    assert outputs[0].suffix == ".zip"
    with zipfile.ZipFile(outputs[0]) as archive:
        assert sorted(archive.namelist()) == ["data.csv", "sample.png"]


def test_tar_gz_output_has_double_extension(tools, png_file: Path, csv_file: Path, tmp_path: Path):
    _job, outputs = run_conversion([png_file, csv_file], "tar-gz", tools, output_dir=tmp_path / "out")

    assert outputs[0].name.endswith(".tar.gz")
    with tarfile.open(outputs[0]) as archive:
        assert sorted(archive.getnames()) == ["data.csv", "sample.png"]


def test_duplicate_names_are_disambiguated(tools, tmp_path: Path):
    first = tmp_path / "a"
    second = tmp_path / "b"
    first.mkdir()
    second.mkdir()
    (first / "same.txt").write_text("one", encoding="utf-8")
    (second / "same.txt").write_text("two", encoding="utf-8")

    _job, outputs = run_conversion(
        [first / "same.txt", second / "same.txt"], "zip", tools, output_dir=tmp_path / "out"
    )

    with zipfile.ZipFile(outputs[0]) as archive:
        names = archive.namelist()
    assert len(names) == 2
    assert len(set(names)) == 2


def test_existing_archive_is_not_overwritten(tools, png_file: Path, tmp_path: Path):
    out = tmp_path / "out"
    _job, first = run_conversion([png_file], "zip", tools, output_dir=out)
    _job, second = run_conversion([png_file], "zip", tools, output_dir=out)

    assert first[0] != second[0]
    assert second[0].name == "sample (1).zip"


def test_single_file_is_allowed(tools, png_file: Path, tmp_path: Path):
    _job, outputs = run_conversion([png_file], "zip", tools, output_dir=tmp_path / "out")
    with zipfile.ZipFile(outputs[0]) as archive:
        assert archive.namelist() == ["sample.png"]


def test_archive_accepts_any_file_kind(tools, tmp_path: Path):
    source = tmp_path / "file.txt"
    source.write_text("hello", encoding="utf-8")

    _job, outputs = run_conversion([source], "tar-gz", tools, output_dir=tmp_path / "out")

    assert outputs[0].name.endswith(".tar.gz")
