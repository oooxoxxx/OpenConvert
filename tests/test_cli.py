"""命令列介面測試。"""

from __future__ import annotations

import json
from pathlib import Path

from openconvert import cli


def test_formats_lists_all_categories(capsys):
    assert cli.main(["formats"]) == 0
    output = capsys.readouterr().out
    for category in ("影片", "音訊", "圖片", "PDF", "電子書", "文件", "資料", "字幕", "字型", "壓縮"):
        assert category in output
    assert "sub-vtt" in output
    assert "font-woff2" in output
    assert "tar.gz" in output


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


def test_convert_subtitle_via_cli(srt_file: Path, tmp_path: Path):
    out = tmp_path / "cli-sub"

    assert cli.main(["convert", str(srt_file), "-t", "sub-vtt", "-o", str(out), "-q"]) == 0
    assert (out / "movie.vtt").exists()


def test_convert_data_via_cli(csv_file: Path, tmp_path: Path):
    out = tmp_path / "cli-data"

    assert cli.main(["convert", str(csv_file), "-t", "data-json", "-o", str(out), "-q"]) == 0
    payload = json.loads((out / "data.json").read_text(encoding="utf-8"))
    assert payload[0]["name"] == "Alice"


def test_convert_font_via_cli(system_font: Path, tmp_path: Path):
    out = tmp_path / "cli-font"

    assert cli.main(["convert", str(system_font), "-t", "font-woff", "-o", str(out), "-q"]) == 0
    assert (out / f"{system_font.stem}.woff").exists()


def test_convert_archive_via_cli(csv_file: Path, tmp_path: Path):
    out = tmp_path / "cli-archive"

    assert cli.main(["convert", str(csv_file), "-t", "zip", "-o", str(out), "-q"]) == 0
    assert (out / "data.zip").exists()


def test_modules_list_reports_status(capsys):
    assert cli.main(["modules", "list"]) == 0

    output = capsys.readouterr().out
    assert "ffmpeg" in output
    assert "libreoffice" in output
    # 每個模組一定會標示「未安裝」或「此平台未提供」其中之一
    assert ("未安裝" in output) or ("此平台未提供" in output)


def test_modules_install_with_local_manifest(tmp_path: Path, monkeypatch, capsys):
    import hashlib
    import sys
    import zipfile

    from openconvert.core import modules as modules_module

    exe = ".exe" if sys.platform == "win32" else ""
    archive = tmp_path / "ffmpeg-test.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr(f"ffmpeg-test/bin/ffmpeg{exe}", b"ffmpeg")
        bundle.writestr(f"ffmpeg-test/bin/ffprobe{exe}", b"ffprobe")

    manifest = {
        "manifest_version": 1,
        "channel": "test",
        "modules": {
            "ffmpeg": {
                "label": "FFmpeg（測試）",
                "purpose": "測試",
                "license": "GPL-3.0-or-later",
                "homepage": "https://example.com",
                "source": "https://example.com",
                "source_page": "https://example.com",
                "targets": {
                    modules_module.platform_key(): {
                        "version": "1.0",
                        "url": archive.as_uri(),
                        "sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
                        "size": archive.stat().st_size,
                        "archive": "zip",
                    }
                },
            }
        },
    }
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setenv(modules_module.MANIFEST_ENV, str(manifest_path))

    dest = tmp_path / "tools"
    assert cli.main(["modules", "install", "ffmpeg", "--dest", str(dest)]) == 0

    assert (dest / "ffmpeg" / f"ffmpeg{exe}").is_file()
    assert (dest / "THIRD-PARTY-NOTICES.txt").exists()

    assert cli.main(["modules", "list", "--dest", str(dest)]) == 0
    assert "已安裝" in capsys.readouterr().out

    assert cli.main(["modules", "remove", "ffmpeg", "--dest", str(dest)]) == 0
    assert not (dest / "ffmpeg").exists()


def test_probe_outputs_json(png_file: Path, capsys):
    assert cli.main(["probe", str(png_file)]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["kind"] == "image"
    assert payload["details"]["尺寸"] == "80 × 60"


def test_probe_text_file_reports_encoding(csv_file: Path, capsys):
    assert cli.main(["probe", str(csv_file)]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["kind"] == "data"
    assert "行數" in payload["details"]
    assert payload["details"]["文字編碼"]


def test_probe_font_reports_family(system_font: Path, capsys):
    assert cli.main(["probe", str(system_font)]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["kind"] == "font"
    assert "字型家族" in payload["details"]


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
