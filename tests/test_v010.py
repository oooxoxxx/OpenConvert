"""0.10.0 新增目標的測試：XML／SQLite／7z／tar.zst／解壓／PDF 分割／檔名樣板。"""

from __future__ import annotations

import json
import sqlite3
import zipfile
from pathlib import Path

import pytest

from .helpers import run_conversion

# --------------------------------------------------------------------------- XML


def test_xml_to_json(tools, tmp_path: Path):
    xml = tmp_path / "data.xml"
    xml.write_text(
        "<root>"
        '<person id="1"><name>Alice</name><age>30</age></person>'
        '<person id="2"><name>Bob</name><age>25</age></person>'
        "</root>",
        encoding="utf-8",
    )

    _job, outputs = run_conversion([xml], "data-json", tools, output_dir=tmp_path / "out")

    data = json.loads(outputs[0].read_text(encoding="utf-8"))
    assert data == [
        {"id": "1", "name": "Alice", "age": "30"},
        {"id": "2", "name": "Bob", "age": "25"},
    ]


def test_xml_repeated_tags_become_list(tools, tmp_path: Path):
    xml = tmp_path / "items.xml"
    xml.write_text(
        "<root><item><tag>a</tag><tag>b</tag></item></root>",
        encoding="utf-8",
    )

    _job, outputs = run_conversion([xml], "data-json", tools, output_dir=tmp_path / "out")
    data = json.loads(outputs[0].read_text(encoding="utf-8"))
    assert data[0]["tag"] == ["a", "b"]


def test_xml_to_csv(tools, tmp_path: Path):
    xml = tmp_path / "data.xml"
    xml.write_text(
        "<root><row><name>Alice</name><score>90</score></row></root>",
        encoding="utf-8",
    )

    _job, outputs = run_conversion([xml], "data-csv", tools, output_dir=tmp_path / "out")
    text = outputs[0].read_text(encoding="utf-8-sig")
    assert text.splitlines()[0] == "name,score"
    assert "Alice,90" in text


def test_xml_invalid_raises(tools, tmp_path: Path):
    from openconvert.core.errors import ConversionError

    bad = tmp_path / "bad.xml"
    bad.write_text("<root><unclosed>", encoding="utf-8")

    with pytest.raises(ConversionError):
        run_conversion([bad], "data-json", tools)


def test_xml_to_excel_yaml_and_toml(tools, tmp_path: Path):
    xml = tmp_path / "data.xml"
    xml.write_text("<root><row><name>Alice</name><score>90</score></row></root>", encoding="utf-8")

    _job, xlsx = run_conversion([xml], "data-xlsx", tools, output_dir=tmp_path / "xlsx")
    _job, yaml_out = run_conversion([xml], "data-yaml", tools, output_dir=tmp_path / "yaml")
    _job, toml = run_conversion([xml], "data-toml", tools, output_dir=tmp_path / "toml")

    import openpyxl
    import yaml

    try:
        import tomllib
    except ModuleNotFoundError:  # Python 3.10
        import tomli as tomllib

    workbook = openpyxl.load_workbook(xlsx[0], read_only=True)
    rows = list(workbook.active.iter_rows(values_only=True))
    workbook.close()
    assert rows == [("name", "score"), ("Alice", "90")]
    assert yaml.safe_load(yaml_out[0].read_text(encoding="utf-8")) == [{"name": "Alice", "score": "90"}]
    assert tomllib.loads(toml[0].read_text(encoding="utf-8"))["records"] == [{"name": "Alice", "score": "90"}]


def test_json_xml_roundtrip(tools, tmp_path: Path):
    from xml.etree import ElementTree as ET

    source = tmp_path / "data.json"
    expected = [{"name": "Alice", "tag": ["a", "b"]}]
    source.write_text(json.dumps(expected), encoding="utf-8")

    _job, xml = run_conversion([source], "data-xml", tools, output_dir=tmp_path / "xml")
    root = ET.parse(xml[0]).getroot()
    assert root.tag == "records"
    assert root.findtext("record/name") == "Alice"
    assert [node.text for node in root.findall("record/tag")] == ["a", "b"]

    _job, restored = run_conversion(xml, "data-json", tools, output_dir=tmp_path / "json")
    assert json.loads(restored[0].read_text(encoding="utf-8")) == expected


# --------------------------------------------------------------------------- SQLite


def _make_db(path: Path) -> None:
    connection = sqlite3.connect(path)
    connection.execute("CREATE TABLE scores (name TEXT, score INTEGER)")
    connection.execute("INSERT INTO scores VALUES ('Alice', 90), ('Bob', 85)")
    connection.execute("CREATE TABLE other (x TEXT)")
    connection.execute("INSERT INTO other VALUES ('y')")
    connection.commit()
    connection.close()


def test_sqlite_to_json(tools, tmp_path: Path):
    db = tmp_path / "data.sqlite"
    _make_db(db)

    _job, outputs = run_conversion([db], "data-json", tools, output_dir=tmp_path / "out")

    data = json.loads(outputs[0].read_text(encoding="utf-8"))
    assert data == [{"name": "Alice", "score": 90}, {"name": "Bob", "score": 85}]


def test_sqlite_sheet_selection(tools, tmp_path: Path):
    db = tmp_path / "data.sqlite"
    _make_db(db)

    _job, outputs = run_conversion([db], "data-json", tools, output_dir=tmp_path / "out", sheet="other")
    data = json.loads(outputs[0].read_text(encoding="utf-8"))
    assert data == [{"x": "y"}]

    from openconvert.core.errors import InvalidInputError

    with pytest.raises(InvalidInputError):
        run_conversion([db], "data-json", tools, sheet="不存在的表")


def test_sqlite_to_csv(tools, tmp_path: Path):
    db = tmp_path / "data.sqlite"
    _make_db(db)

    _job, outputs = run_conversion([db], "data-csv", tools, output_dir=tmp_path / "out")
    text = outputs[0].read_text(encoding="utf-8-sig")
    assert text.splitlines()[0] == "name,score"
    assert "Alice,90" in text


# --------------------------------------------------------------------------- 7z / tar.zst


def test_7z_roundtrip(tools, png_file: Path, csv_file: Path, tmp_path: Path):
    _job, packed = run_conversion([png_file, csv_file], "archive-7z", tools, output_dir=tmp_path / "a")
    assert packed[0].suffix == ".7z"

    _job, extracted = run_conversion([packed[0]], "archive-extract", tools, output_dir=tmp_path / "b")
    assert extracted[0].is_dir()
    names = {path.name for path in extracted[0].rglob("*") if path.is_file()}
    assert {"sample.png", "data.csv"} <= names


def test_tar_zst_roundtrip(tools, png_file: Path, csv_file: Path, tmp_path: Path):
    _job, packed = run_conversion([png_file, csv_file], "archive-tar-zst", tools, output_dir=tmp_path / "a")
    assert packed[0].name.endswith(".tar.zst")

    _job, extracted = run_conversion([packed[0]], "archive-extract", tools, output_dir=tmp_path / "b")
    assert extracted[0].name == "sample_archive_extracted"
    names = {path.name for path in extracted[0].rglob("*") if path.is_file()}
    assert {"sample.png", "data.csv"} <= names


def test_zip_extract(tools, png_file: Path, csv_file: Path, tmp_path: Path):
    _job, packed = run_conversion([png_file, csv_file], "zip", tools, output_dir=tmp_path / "a")
    _job, extracted = run_conversion([packed[0]], "archive-extract", tools, output_dir=tmp_path / "b")

    names = {path.name for path in extracted[0].rglob("*") if path.is_file()}
    assert {"sample.png", "data.csv"} <= names


def test_extract_rejects_path_traversal(tools, tmp_path: Path):
    from openconvert.core.errors import ConversionError

    malicious = tmp_path / "evil.zip"
    with zipfile.ZipFile(malicious, "w") as archive:
        archive.writestr("../escape.txt", "bad")

    # 整包只有不安全路徑時，應回報錯誤而不是把檔案寫到 out_dir 外面
    with pytest.raises(ConversionError):
        run_conversion([malicious], "archive-extract", tools, output_dir=tmp_path / "out")
    assert not (tmp_path / "escape.txt").exists()


@pytest.mark.parametrize(
    "name",
    ["../escape.txt", "..\\escape.txt", "/absolute.txt", "C:/escape.txt", "C:escape.txt", "a//b.txt"],
)
def test_archive_member_path_safety(name: str):
    from openconvert.converters.archive import _safe_member

    assert _safe_member(name) is None


def test_archive_member_path_allows_nested_files():
    from openconvert.converters.archive import _safe_member

    assert _safe_member("folder/file.txt") == "folder/file.txt"
    assert _safe_member("folder\\file.txt") == "folder/file.txt"


def test_tar_zst_unique_name(tools, png_file: Path, csv_file: Path, tmp_path: Path):
    out = tmp_path / "out"
    _job, first = run_conversion([png_file, csv_file], "archive-tar-zst", tools, output_dir=out)
    _job, second = run_conversion([png_file, csv_file], "archive-tar-zst", tools, output_dir=out)

    assert first[0].name == "sample_archive.tar.zst"
    assert second[0].name == "sample_archive (1).tar.zst"


# --------------------------------------------------------------------------- PDF 分割


def test_pdf_split(tools, pdf_file: Path, tmp_path: Path):
    from pypdf import PdfReader

    _job, outputs = run_conversion([pdf_file], "pdf-split", tools, output_dir=tmp_path / "out", split_pages=2)

    assert len(outputs) == 2
    counts = sorted(len(PdfReader(str(path)).pages) for path in outputs)
    assert counts == [1, 2]


def test_pdf_split_rejects_zero(tools, pdf_file: Path):
    from openconvert.core.errors import InvalidInputError

    with pytest.raises(InvalidInputError):
        run_conversion([pdf_file], "pdf-split", tools, split_pages=0)


# --------------------------------------------------------------------------- 檔名樣板


def test_filename_template(tools, png_file: Path, tmp_path: Path):
    _job, outputs = run_conversion(
        [png_file],
        "jpg",
        tools,
        output_dir=tmp_path / "out",
        filename_template="{name}_v2.{ext}",
    )
    assert outputs[0].name == "sample_v2.jpg"


def test_filename_template_with_date_and_index(tools, png_file: Path, tmp_path: Path):
    _job, outputs = run_conversion(
        [png_file],
        "png",
        tools,
        output_dir=tmp_path / "out",
        filename_template="{name}-{index}.{ext}",
    )
    assert outputs[0].name == "sample-001.png"


def test_filename_template_empty_uses_source_stem(tools, png_file: Path, tmp_path: Path):
    _job, outputs = run_conversion([png_file], "jpg", tools, output_dir=tmp_path / "out")
    assert outputs[0].name == "sample.jpg"


# --------------------------------------------------------------------------- 0.10.1 安全回歸


def test_template_overwrite_never_overwrites_real_source(tools, pdf_file: Path):
    original = pdf_file.read_bytes()

    _job, outputs = run_conversion(
        [pdf_file],
        "pdf-compress",
        tools,
        overwrite=True,
        filename_template=pdf_file.stem,
    )

    assert outputs[0] != pdf_file
    assert outputs[0].name == f"{pdf_file.stem}_compressed_converted.pdf"
    assert pdf_file.read_bytes() == original


def test_template_overwrite_protects_every_group_source(tools, pdf_file: Path, tmp_path: Path):
    second = tmp_path / "other.pdf"
    second.write_bytes(pdf_file.read_bytes())
    original = second.read_bytes()

    _job, outputs = run_conversion(
        [pdf_file, second],
        "pdf-merge",
        tools,
        overwrite=True,
        filename_template=second.stem,
    )

    assert outputs[0] != second
    assert second.read_bytes() == original
    assert outputs[0].is_file()


def test_7z_extracts_only_safe_members(tools, tmp_path: Path, monkeypatch):
    import importlib

    import py7zr

    module = importlib.import_module("py7zr.py7zr")
    malicious = tmp_path / "mixed.7z"
    # py7zr 正常會拒絕建立這種封裝；只在產生惡意測試樣本時暫時繞過，
    # 建立後立刻還原，讓解壓端使用真正的安全檢查。
    with monkeypatch.context() as patch:
        patch.setattr(module, "check_archive_path", lambda _path: True)
        with py7zr.SevenZipFile(malicious, "w") as archive:
            archive.writestr(b"good", "safe.txt")
            archive.writestr(b"bad", "../escape.txt")

    _job, outputs = run_conversion([malicious], "archive-extract", tools, output_dir=tmp_path / "out")

    assert (outputs[0] / "safe.txt").read_bytes() == b"good"
    assert not (tmp_path / "escape.txt").exists()
    assert not (tmp_path / "out" / "escape.txt").exists()


def test_invalid_sqlite_raises_conversion_error(tools, tmp_path: Path):
    from openconvert.core.errors import ConversionError

    bad = tmp_path / "bad.sqlite"
    bad.write_text("not a database", encoding="utf-8")

    with pytest.raises(ConversionError, match="SQLite"):
        run_conversion([bad], "data-json", tools)
