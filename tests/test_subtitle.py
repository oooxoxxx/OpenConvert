"""字幕轉換測試。"""

from __future__ import annotations

from pathlib import Path

import pytest

from openconvert.converters.subtitle import parse_ass, parse_srt, parse_vtt, to_ass, to_srt
from openconvert.core.errors import ConversionError

from .helpers import run_conversion


def test_srt_to_vtt(tools, srt_file: Path, tmp_path: Path):
    _job, outputs = run_conversion([srt_file], "sub-vtt", tools, output_dir=tmp_path / "out")

    text = outputs[0].read_text(encoding="utf-8")
    assert text.startswith("WEBVTT")
    assert "00:00:01.000 --> 00:00:03.500" in text
    assert "Hello world" in text
    assert "<i>" not in text  # 標籤會被移除


def test_srt_to_ass(tools, srt_file: Path, tmp_path: Path):
    _job, outputs = run_conversion([srt_file], "sub-ass", tools, output_dir=tmp_path / "out")

    text = outputs[0].read_text(encoding="utf-8")
    assert "[Events]" in text
    assert "Dialogue: 0,0:00:01.00,0:00:03.50,Default,,0,0,0,," in text
    assert r"{\i1}Hello{\i0} world" in text  # <i> 會對應成 ASS 的斜體標籤


def test_ass_to_srt(tools, ass_file: Path, tmp_path: Path):
    _job, outputs = run_conversion([ass_file], "sub-srt", tools, output_dir=tmp_path / "out")

    text = outputs[0].read_text(encoding="utf-8")
    assert text.startswith("1\n00:00:01,000 --> 00:00:03,500")
    assert "Hello world" in text
    assert "{\\" not in text  # ASS 覆寫標籤會被清掉


def test_vtt_roundtrip_preserves_text(tools, srt_file: Path, tmp_path: Path):
    _job, vtt_outputs = run_conversion([srt_file], "sub-vtt", tools, output_dir=tmp_path / "a")
    _job, srt_outputs = run_conversion([vtt_outputs[0]], "sub-srt", tools, output_dir=tmp_path / "b")

    text = srt_outputs[0].read_text(encoding="utf-8")
    assert "Hello world" in text
    assert "Second line" in text


def test_parsers_ignore_empty_input():
    assert parse_srt("") == []
    assert parse_vtt("") == []
    assert parse_ass("") == []


def test_srt_writer_keeps_multiline_text():
    cues = parse_srt("1\n00:00:00,000 --> 00:00:02,000\nline one\nline two\n")
    assert cues[0].text == "line one\nline two"
    assert "line one\nline two" in to_srt(cues)


def test_ass_writer_escapes_braces():
    cues = parse_srt("1\n00:00:00,000 --> 00:00:02,000\n{not a tag}\n")
    output = to_ass(cues)
    assert r"\{not a tag\}" in output


def test_empty_subtitle_file_raises(tools, tmp_path: Path):
    broken = tmp_path / "empty.srt"
    broken.write_text("", encoding="utf-8")

    with pytest.raises(ConversionError) as excinfo:
        run_conversion([broken], "sub-vtt", tools)

    assert "找不到任何字幕" in excinfo.value.user_message
