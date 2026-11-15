"""命令列介面測試。"""

from __future__ import annotations

import json
from pathlib import Path

from openconvert import cli


def test_formats_lists_all_categories(capsys):
    assert cli.main(["formats"]) == 0
    output = capsys.readouterr().out
    for category in ("影片", "音訊", "圖片", "PDF", "電子書"):
        assert category in output


def test_convert_image_via_cli(png_file: Path, tmp_path: Path):
    out = tmp_path / "cli-out"

    code = cli.main(["convert", str(png_file), "-t", "jpg", "-o", str(out), "-q"])

    assert code == 0
    assert (out / "sample.jpg").exists()


def test_convert_rejects_unknown_format(png_file: Path, capsys):
    assert cli.main(["convert", str(png_file), "-t", "nope", "-q"]) == 2
    assert "不支援的目標格式" in capsys.readouterr().err


def test_convert_without_matching_files_returns_error(tmp_path: Path, capsys):
    image = tmp_path / "a.png"
    from PIL import Image

    Image.new("RGB", (10, 10)).save(image)

    assert cli.main(["convert", str(image), "-t", "pdf-merge", "-q"]) == 2


def test_probe_outputs_json(png_file: Path, capsys):
    assert cli.main(["probe", str(png_file)]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["kind"] == "image"
    assert payload["details"]["尺寸"] == "80 × 60"


def test_version_flag_exits_cleanly():
    import pytest

    with pytest.raises(SystemExit) as excinfo:
        cli.main(["--version"])
    assert excinfo.value.code == 0


def test_output_survives_non_utf8_console(monkeypatch):
    """模擬 Windows cp1252 主控台：輸出中文不應拋出 UnicodeEncodeError。"""
    import io
    import sys

    buffer = io.BytesIO()
    legacy = io.TextIOWrapper(buffer, encoding="cp1252", errors="strict", newline="")
    monkeypatch.setattr(sys, "stdout", legacy)
    monkeypatch.setattr(sys, "stderr", legacy)

    assert cli.main(["formats"]) == 0
    legacy.flush()
    assert "圖片" in buffer.getvalue().decode("utf-8")
