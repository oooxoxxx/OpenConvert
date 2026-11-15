"""字型格式轉換測試（使用系統字型）。"""

from __future__ import annotations

from pathlib import Path

import pytest
from fontTools.ttLib import TTFont

from openconvert.core.errors import ConversionError

from .helpers import run_conversion


def _sfnt_version(path: Path) -> str:
    font = TTFont(str(path))
    try:
        return font.sfntVersion
    finally:
        font.close()


def test_ttf_to_woff(tools, system_font: Path, tmp_path: Path):
    _job, outputs = run_conversion([system_font], "font-woff", tools, output_dir=tmp_path / "out")

    assert outputs[0].suffix == ".woff"
    font = TTFont(str(outputs[0]))
    try:
        assert font.flavor == "woff"
    finally:
        font.close()


def test_woff_to_woff2_and_back(tools, system_font: Path, tmp_path: Path):
    _job, woff = run_conversion([system_font], "font-woff", tools, output_dir=tmp_path / "a")
    _job, woff2 = run_conversion([woff[0]], "font-woff2", tools, output_dir=tmp_path / "b")
    _job, ttf = run_conversion([woff2[0]], "font-ttf", tools, output_dir=tmp_path / "c")

    assert woff2[0].suffix == ".woff2"
    assert ttf[0].suffix == ".ttf"
    # 取出的字型必須是有效的 sfnt（TTF 或 OTF），且不再是壓縮容器
    assert _sfnt_version(ttf[0]) in ("\x00\x01\x00\x00", "true", "OTTO")


def test_source_font_is_never_modified(tools, system_font: Path, tmp_path: Path):
    before = system_font.read_bytes()
    run_conversion([system_font], "font-woff", tools, output_dir=tmp_path / "out")
    assert system_font.read_bytes() == before


def test_corrupted_font_raises_readable_error(tools, tmp_path: Path):
    broken = tmp_path / "broken.ttf"
    broken.write_bytes(b"not a font at all")

    with pytest.raises(ConversionError) as excinfo:
        run_conversion([broken], "font-woff", tools)
    assert "無法讀取字型" in excinfo.value.user_message
