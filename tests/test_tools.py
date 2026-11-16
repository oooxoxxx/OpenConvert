"""隨附引擎（自足化）的尋找與建置工具測試。

這些測試完全離線：不真的下載引擎，只用假的目錄結構驗證尋找順序與雜湊邏輯。
"""

from __future__ import annotations

import hashlib
import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _load_fetch_tools():
    path = ROOT / "scripts" / "fetch_tools.py"
    spec = importlib.util.spec_from_file_location("openconvert_fetch_tools", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


fetch_tools = _load_fetch_tools()

EXE = ".exe" if sys.platform == "win32" else ""


# --------------------------------------------------------------------------- 建置工具


def test_platform_key_has_expected_shape():
    key = fetch_tools.platform_key()
    assert key.split("-")[0] in {"windows", "linux", "macos"}
    assert key.split("-")[1] in {"x64", "arm64"}


def test_sha256_matches_hashlib(tmp_path: Path):
    target = tmp_path / "blob.bin"
    target.write_bytes(b"openconvert")
    assert fetch_tools.sha256_of(target) == hashlib.sha256(b"openconvert").hexdigest()


def test_download_accepts_matching_hash(tmp_path: Path):
    source = tmp_path / "source.bin"
    source.write_bytes(b"payload")
    digest = hashlib.sha256(b"payload").hexdigest()

    result = fetch_tools.download(source.as_uri(), tmp_path / "copy.bin", digest)

    assert result.read_bytes() == b"payload"


def test_download_rejects_wrong_hash(tmp_path: Path):
    source = tmp_path / "source.bin"
    source.write_bytes(b"payload")

    with pytest.raises(SystemExit) as excinfo:
        fetch_tools.download(source.as_uri(), tmp_path / "copy.bin", "0" * 64)

    assert "SHA-256 不符" in str(excinfo.value)
    assert not (tmp_path / "copy.bin").exists()


def test_install_ffmpeg_creates_expected_layout(tmp_path: Path):
    extracted = tmp_path / "extracted"
    bin_dir = extracted / "ffmpeg-ver-win64-gpl" / "bin"
    bin_dir.mkdir(parents=True)
    (bin_dir / f"ffmpeg{EXE}").write_bytes(b"ffmpeg")
    (bin_dir / f"ffprobe{EXE}").write_bytes(b"ffprobe")
    (extracted / "ffmpeg-ver-win64-gpl" / "LICENSE.txt").write_text("GPL", encoding="utf-8")

    dest_tools = tmp_path / "tools"
    result = fetch_tools.install_ffmpeg(extracted, dest_tools)

    assert (dest_tools / "ffmpeg" / f"ffmpeg{EXE}").is_file()
    assert (dest_tools / "ffmpeg" / f"ffprobe{EXE}").is_file()
    assert (dest_tools / "ffmpeg" / "LICENSE.txt").is_file()
    assert result["path"].endswith("ffmpeg")


def test_install_libreoffice_creates_expected_layout(tmp_path: Path):
    extracted = tmp_path / "extracted"
    program = extracted / "LibreOffice" / "program"
    program.mkdir(parents=True)
    (program / f"soffice{EXE}").write_bytes(b"soffice")
    (extracted / "LibreOffice" / "share").mkdir()

    dest_tools = tmp_path / "tools"
    fetch_tools.install_libreoffice(extracted, dest_tools)

    assert (dest_tools / "libreoffice" / "program" / f"soffice{EXE}").is_file()
    assert (dest_tools / "libreoffice" / "share").is_dir()


def test_install_libreoffice_rejects_unexpected_layout(tmp_path: Path):
    extracted = tmp_path / "extracted"
    (extracted / "random").mkdir(parents=True)
    (extracted / "random" / f"soffice{EXE}").write_bytes(b"soffice")

    with pytest.raises(SystemExit):
        fetch_tools.install_libreoffice(extracted, tmp_path / "tools")


def test_write_notices_lists_engines(tmp_path: Path):
    lock = fetch_tools.load_lock()
    fetch_tools.write_notices(tmp_path, lock, "windows-x64", ["ffmpeg"])

    text = (tmp_path / "THIRD-PARTY-NOTICES.txt").read_text(encoding="utf-8")
    assert "FFmpeg" in text
    assert "GPL" in text


def test_lock_file_has_ffmpeg_for_windows():
    lock = fetch_tools.load_lock()
    entry = lock["engines"]["ffmpeg"]["targets"]["windows-x64"]
    assert entry["url"].startswith("https://")
    assert len(entry["sha256"]) == 64


# --------------------------------------------------------------------------- 尋找順序


def _make_bundled_tools(monkeypatch, tmp_path: Path) -> Path:
    tools = tmp_path / "tools"
    tools.mkdir()
    monkeypatch.setattr("openconvert.core.ffmpeg.tools_dir", lambda: tools)
    monkeypatch.setattr("openconvert.core.office.tools_dir", lambda: tools)
    return tools


def test_ffmpeg_prefers_bundled_tools(monkeypatch, tmp_path: Path):
    from openconvert.core.ffmpeg import discover

    tools = _make_bundled_tools(monkeypatch, tmp_path)
    ffmpeg = tools / "ffmpeg" / f"ffmpeg{EXE}"
    ffmpeg.parent.mkdir()
    ffmpeg.write_bytes(b"bundled")
    ffprobe = tools / "ffmpeg" / f"ffprobe{EXE}"
    ffprobe.write_bytes(b"bundled")

    found = discover()

    assert found.ffmpeg == ffmpeg
    assert found.ffprobe == ffprobe
    assert found.bundled is True


def test_ffmpeg_marks_system_binary_as_not_bundled(monkeypatch, tmp_path: Path):
    from openconvert.core import ffmpeg as ffmpeg_module

    tools = _make_bundled_tools(monkeypatch, tmp_path)
    assert not any(tools.iterdir())

    system_ffmpeg = tmp_path / "system" / f"ffmpeg{EXE}"
    system_ffmpeg.parent.mkdir()
    system_ffmpeg.write_bytes(b"system")
    monkeypatch.setattr(ffmpeg_module, "locate", lambda name, override=None: system_ffmpeg)

    found = ffmpeg_module.discover()

    assert found.ffmpeg == system_ffmpeg
    assert found.bundled is False


def test_office_prefers_bundled_tools(monkeypatch, tmp_path: Path):
    from openconvert.core.office import discover

    tools = _make_bundled_tools(monkeypatch, tmp_path)
    soffice = tools / "libreoffice" / "program" / f"soffice{EXE}"
    soffice.parent.mkdir(parents=True)
    soffice.write_bytes(b"bundled")

    found = discover()

    assert found.soffice == soffice
    assert found.bundled is True


def test_office_reports_missing_when_nothing_found(monkeypatch, tmp_path: Path):
    from openconvert.core.office import discover, locate

    _make_bundled_tools(monkeypatch, tmp_path)
    monkeypatch.setattr("openconvert.core.office.shutil.which", lambda _name: None)
    monkeypatch.setattr("openconvert.core.office._candidate_paths", lambda: iter(()))

    assert locate() is None
    assert discover().available is False


def test_office_command_includes_headless_flags(monkeypatch, tmp_path: Path):
    from openconvert.core import office as office_module

    captured: dict[str, list[str]] = {}

    def fake_run(command, **_kwargs):
        captured["command"] = list(command)
        outdir = Path(command[command.index("--outdir") + 1])
        source = Path(command[-1])
        outdir.mkdir(parents=True, exist_ok=True)
        produced = outdir / f"{source.stem}.pdf"
        produced.write_bytes(b"%PDF-1.4 fake")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(office_module.subprocess, "run", fake_run)

    source = tmp_path / "report.docx"
    source.write_bytes(b"fake docx")
    dest = tmp_path / "out" / "report.pdf"
    tools = office_module.OfficeTools(soffice=Path("soffice"))

    result = office_module.convert_to(tools, source, dest, "pdf")

    assert result == dest
    assert dest.exists()
    command = captured["command"]
    assert "--headless" in command
    assert "--nofirststartwizard" in command
    assert "--convert-to" in command
    assert "UserInstallation" in " ".join(command)
