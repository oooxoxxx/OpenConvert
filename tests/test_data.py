"""資料轉換測試：CSV／JSON／XLSX／YAML／TOML。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from openconvert.converters.data import load_source
from openconvert.core.errors import ConversionError, InvalidInputError

from .helpers import run_conversion


def test_csv_to_json(tools, csv_file: Path, tmp_path: Path):
    _job, outputs = run_conversion([csv_file], "data-json", tools, output_dir=tmp_path / "out")

    data = json.loads(outputs[0].read_text(encoding="utf-8"))
    assert data == [
        {"name": "Alice", "age": "30", "city": "台北"},
        {"name": "Bob", "age": "25", "city": "高雄"},
    ]


def test_json_to_csv(tools, json_file: Path, tmp_path: Path):
    _job, outputs = run_conversion([json_file], "data-csv", tools, output_dir=tmp_path / "out")

    text = outputs[0].read_text(encoding="utf-8-sig")
    assert text.splitlines()[0] == "name,age"
    assert "Alice,30" in text


def test_csv_to_xlsx_and_back(tools, csv_file: Path, tmp_path: Path):
    _job, xlsx_outputs = run_conversion([csv_file], "data-xlsx", tools, output_dir=tmp_path / "a")
    _job, csv_outputs = run_conversion([xlsx_outputs[0]], "data-csv", tools, output_dir=tmp_path / "b")

    rows = csv_outputs[0].read_text(encoding="utf-8-sig").splitlines()
    assert rows[0] == "name,age,city"
    assert "Alice,30,台北" in rows


def test_xlsx_to_json(tools, xlsx_file: Path, tmp_path: Path):
    _job, outputs = run_conversion([xlsx_file], "data-json", tools, output_dir=tmp_path / "out")

    data = json.loads(outputs[0].read_text(encoding="utf-8"))
    assert data == [{"name": "Alice", "score": 90}, {"name": "Bob", "score": 80}]


def test_xlsx_sheet_selection(tools, xlsx_file: Path, tmp_path: Path):
    _job, outputs = run_conversion([xlsx_file], "data-csv", tools, output_dir=tmp_path / "out", sheet="成績")
    assert "Alice" in outputs[0].read_text(encoding="utf-8-sig")

    with pytest.raises(InvalidInputError):
        run_conversion([xlsx_file], "data-csv", tools, sheet="不存在的工作表")


def test_yaml_to_json(tools, tmp_path: Path):
    source = tmp_path / "config.yaml"
    source.write_text("name: demo\nitems:\n  - a\n  - b\n", encoding="utf-8")

    _job, outputs = run_conversion([source], "data-json", tools, output_dir=tmp_path / "out")

    data = json.loads(outputs[0].read_text(encoding="utf-8"))
    assert data == {"name": "demo", "items": ["a", "b"]}


def test_yaml_to_toml(tools, tmp_path: Path):
    source = tmp_path / "config.yaml"
    source.write_text("name: demo\ncount: 3\n", encoding="utf-8")

    _job, outputs = run_conversion([source], "data-toml", tools, output_dir=tmp_path / "out")

    text = outputs[0].read_text(encoding="utf-8")
    assert 'name = "demo"' in text
    assert "count = 3" in text


def test_toml_roundtrip(tools, tmp_path: Path):
    source = tmp_path / "config.toml"
    source.write_text('name = "demo"\n[server]\nport = 8080\n', encoding="utf-8")

    _job, outputs = run_conversion([source], "data-json", tools, output_dir=tmp_path / "out")

    data = json.loads(outputs[0].read_text(encoding="utf-8"))
    assert data == {"name": "demo", "server": {"port": 8080}}


def test_tsv_is_supported(tools, tmp_path: Path):
    source = tmp_path / "data.tsv"
    source.write_text("a\tb\n1\t2\n", encoding="utf-8")

    _job, outputs = run_conversion([source], "data-json", tools, output_dir=tmp_path / "out")
    assert json.loads(outputs[0].read_text(encoding="utf-8")) == [{"a": "1", "b": "2"}]


def test_invalid_json_raises_readable_error(tools, tmp_path: Path):
    broken = tmp_path / "broken.json"
    broken.write_text("{not json", encoding="utf-8")

    with pytest.raises(ConversionError) as excinfo:
        run_conversion([broken], "data-csv", tools)
    assert "格式不正確" in excinfo.value.user_message


def test_load_source_detects_table_shape(csv_file: Path):
    kind, payload = load_source(csv_file)
    assert kind == "table"
    header, rows = payload
    assert header == ["name", "age", "city"]
    assert len(rows) == 2
