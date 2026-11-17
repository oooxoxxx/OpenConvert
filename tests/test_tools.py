"""引擎模組（自足化 / 模組化）的測試。

完全離線：用假的 manifest（``file://`` 下載）與假的目錄結構驗證
下載驗證、安裝、狀態與尋找順序，不需要真的連上 GitHub。
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import zipfile
from pathlib import Path

import pytest

from openconvert.core import modules
from openconvert.core.errors import ConversionCancelled, ModuleError

ROOT = Path(__file__).resolve().parents[1]

EXE = ".exe" if sys.platform == "win32" else ""


def _load_fetch_tools():
    path = ROOT / "scripts" / "fetch_tools.py"
    spec = importlib.util.spec_from_file_location("openconvert_fetch_tools", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


fetch_tools = _load_fetch_tools()


# --------------------------------------------------------------------------- 基本工具


def test_platform_key_has_expected_shape():
    key = modules.platform_key()
    assert key.split("-")[0] in {"windows", "linux", "macos"}
    assert key.split("-")[1] in {"x64", "arm64"}


def test_sha256_matches_hashlib(tmp_path: Path):
    target = tmp_path / "blob.bin"
    target.write_bytes(b"openconvert")
    assert modules._sha256(target) == hashlib.sha256(b"openconvert").hexdigest()


def test_shipped_manifest_lists_ffmpeg_and_libreoffice():
    manifest = modules.load_manifest()
    assert {"ffmpeg", "libreoffice"} <= set(manifest["modules"])
    ffmpeg = manifest["modules"]["ffmpeg"]["targets"]
    assert len(ffmpeg["windows-x64"]["sha256"]) == 64


def test_get_module_missing_platform_returns_none(monkeypatch):
    monkeypatch.setattr(modules, "platform_key", lambda: "os2-warp")
    assert modules.get_module("ffmpeg") is None
    assert modules.get_module("不存在的模組") is None


# --------------------------------------------------------------------------- 下載與安裝


def _write_fake_manifest(
    tmp_path: Path,
    module_id: str,
    archive: Path,
    sha256: str,
    version: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = {
        "manifest_version": 1,
        "channel": "test",
        "modules": {
            module_id: {
                "label": f"{module_id} 測試",
                "purpose": "測試用",
                "license": "GPL-3.0-or-later" if module_id == "ffmpeg" else "MPL-2.0",
                "homepage": "https://example.com",
                "source": "https://example.com/source",
                "source_page": "https://example.com/license",
                "targets": {
                    modules.platform_key(): {
                        "version": version,
                        "url": archive.as_uri(),
                        "sha256": sha256,
                        "size": archive.stat().st_size,
                        "archive": "zip",
                    }
                },
            }
        },
    }
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setenv(modules.MANIFEST_ENV, str(path))


def _fake_ffmpeg_zip(tmp_path: Path) -> tuple[Path, str]:
    archive_path = tmp_path / "ffmpeg-test.zip"
    inner = f"ffmpeg-test/bin/ffmpeg{EXE}"
    probe = f"ffmpeg-test/bin/ffprobe{EXE}"
    with zipfile.ZipFile(archive_path, "w") as bundle:
        bundle.writestr(inner, b"ffmpeg binary")
        bundle.writestr(probe, b"ffprobe binary")
        bundle.writestr("ffmpeg-test/LICENSE.txt", "GPL-3.0-or-later")
    return archive_path, modules._sha256(archive_path)


def test_download_accepts_matching_hash(tmp_path: Path, monkeypatch):
    archive, digest = _fake_ffmpeg_zip(tmp_path)
    _write_fake_manifest(tmp_path, "ffmpeg", archive, digest, "1.2.3", monkeypatch)

    spec = modules.get_module("ffmpeg")
    assert spec is not None
    result = modules._download(spec, lambda *_: None, lambda: False)
    assert result.exists() and result.stat().st_size == archive.stat().st_size


def test_download_rejects_wrong_hash(tmp_path: Path, monkeypatch):
    archive, _digest = _fake_ffmpeg_zip(tmp_path)
    _write_fake_manifest(tmp_path, "ffmpeg", archive, "0" * 64, "1.2.3", monkeypatch)

    spec = modules.get_module("ffmpeg")
    assert spec is not None
    with pytest.raises(ModuleError) as excinfo:
        modules._download(spec, lambda *_: None, lambda: False)
    assert "SHA-256" in excinfo.value.user_message


def test_download_honours_cancellation(tmp_path: Path, monkeypatch):
    archive, digest = _fake_ffmpeg_zip(tmp_path)
    _write_fake_manifest(tmp_path, "ffmpeg", archive, digest, "1.2.3", monkeypatch)

    spec = modules.get_module("ffmpeg")
    assert spec is not None
    with pytest.raises(ConversionCancelled):
        modules._download(spec, lambda *_: None, lambda: True)


def test_install_ffmpeg_creates_expected_layout(tmp_path: Path, monkeypatch):
    archive, digest = _fake_ffmpeg_zip(tmp_path)
    _write_fake_manifest(tmp_path, "ffmpeg", archive, digest, "9.9.9", monkeypatch)

    base = tmp_path / "tools"
    path = modules.install("ffmpeg", base=base)

    assert (path / f"ffmpeg{EXE}").is_file()
    assert (path / f"ffprobe{EXE}").is_file()
    assert (path / "LICENSE.txt").is_file()
    marker = json.loads((path / ".openconvert-module.json").read_text(encoding="utf-8"))
    assert marker["version"] == "9.9.9"

    state = modules.status("ffmpeg", base)
    assert state.installed and state.install_dir == path and state.version == "9.9.9"
    assert modules.installed_dir("ffmpeg", base) == path


def test_install_reports_missing_binaries(tmp_path: Path, monkeypatch):
    archive_path = tmp_path / "broken.zip"
    with zipfile.ZipFile(archive_path, "w") as bundle:
        bundle.writestr("whatever/readme.txt", "no binaries here")
    _write_fake_manifest(tmp_path, "ffmpeg", archive_path, modules._sha256(archive_path), "1.0", monkeypatch)

    with pytest.raises(ModuleError) as excinfo:
        modules.install("ffmpeg", base=tmp_path / "tools")
    assert "找不到 ffmpeg" in excinfo.value.user_message


def test_remove_forgets_installation(tmp_path: Path, monkeypatch):
    archive, digest = _fake_ffmpeg_zip(tmp_path)
    _write_fake_manifest(tmp_path, "ffmpeg", archive, digest, "1.0", monkeypatch)
    modules.install("ffmpeg", base=tmp_path / "tools")

    assert modules.remove("ffmpeg", tmp_path / "tools") is True
    assert modules.remove("ffmpeg", tmp_path / "tools") is False
    assert modules.status("ffmpeg", tmp_path / "tools").installed is False


def test_write_notices_lists_installed_engines(tmp_path: Path, monkeypatch):
    archive, digest = _fake_ffmpeg_zip(tmp_path)
    _write_fake_manifest(tmp_path, "ffmpeg", archive, digest, "1.0", monkeypatch)
    base = tmp_path / "tools"
    modules.install("ffmpeg", base=base)

    notices = modules.write_notices(base, base)
    assert notices is not None and notices.exists()
    text = notices.read_text(encoding="utf-8")
    assert "ffmpeg" in text and "GPL" in text


def test_write_notices_returns_none_without_engines(tmp_path: Path):
    assert modules.write_notices(tmp_path) is None


def test_install_libreoffice_creates_expected_layout(tmp_path: Path):
    extracted = tmp_path / "extracted"
    program = extracted / "LibreOffice" / "program"
    program.mkdir(parents=True)
    (program / f"soffice{EXE}").write_bytes(b"soffice")
    (extracted / "LibreOffice" / "share").mkdir()

    install_path = tmp_path / "tools" / "libreoffice"
    modules._install_libreoffice(
        extracted,
        install_path,
        modules.ModuleSpec(
            id="libreoffice",
            label="",
            purpose="",
            license="",
            homepage="",
            source="",
            source_page="",
            version="26.2.7",
            url="",
            sha256="",
            size=0,
            archive="msi",
        ),
    )

    assert (install_path / "program" / f"soffice{EXE}").is_file()
    assert (install_path / "share").is_dir()


def test_install_libreoffice_rejects_unexpected_layout(tmp_path: Path):
    extracted = tmp_path / "extracted"
    (extracted / "random").mkdir(parents=True)
    (extracted / "random" / f"soffice{EXE}").write_bytes(b"soffice")

    with pytest.raises(ModuleError):
        modules._install_libreoffice(
            extracted,
            tmp_path / "tools" / "libreoffice",
            modules.ModuleSpec(
                id="libreoffice",
                label="",
                purpose="",
                license="",
                homepage="",
                source="",
                source_page="",
                version="",
                url="",
                sha256="",
                size=0,
                archive="msi",
            ),
        )


# --------------------------------------------------------------------------- 尋找順序


def _make_managed_dirs(monkeypatch, tmp_path: Path) -> Path:
    tools = tmp_path / "tools"
    tools.mkdir()
    monkeypatch.setattr("openconvert.core.ffmpeg.module_search_dirs", lambda: (tools,))
    monkeypatch.setattr("openconvert.core.office.module_search_dirs", lambda: (tools,))
    return tools


def test_ffmpeg_prefers_managed_module(monkeypatch, tmp_path: Path):
    from openconvert.core.ffmpeg import discover

    tools = _make_managed_dirs(monkeypatch, tmp_path)
    ffmpeg = tools / "ffmpeg" / f"ffmpeg{EXE}"
    ffmpeg.parent.mkdir()
    ffmpeg.write_bytes(b"managed")
    (tools / "ffmpeg" / f"ffprobe{EXE}").write_bytes(b"managed")

    found = discover()

    assert found.ffmpeg == ffmpeg
    assert found.ffprobe == tools / "ffmpeg" / f"ffprobe{EXE}"
    assert found.managed is True


def test_ffmpeg_marks_system_binary_as_not_managed(monkeypatch, tmp_path: Path):
    from openconvert.core import ffmpeg as ffmpeg_module

    tools = _make_managed_dirs(monkeypatch, tmp_path)
    assert not any(tools.iterdir())

    system_ffmpeg = tmp_path / "system" / f"ffmpeg{EXE}"
    system_ffmpeg.parent.mkdir()
    system_ffmpeg.write_bytes(b"system")
    monkeypatch.setattr(ffmpeg_module, "locate", lambda name, override=None: system_ffmpeg)

    found = ffmpeg_module.discover()

    assert found.ffmpeg == system_ffmpeg
    assert found.managed is False


def test_office_prefers_managed_module(monkeypatch, tmp_path: Path):
    from openconvert.core.office import discover

    tools = _make_managed_dirs(monkeypatch, tmp_path)
    soffice = tools / "libreoffice" / "program" / f"soffice{EXE}"
    soffice.parent.mkdir(parents=True)
    soffice.write_bytes(b"managed")

    found = discover()

    assert found.soffice == soffice
    assert found.managed is True


def test_office_reports_missing_when_nothing_found(monkeypatch, tmp_path: Path):
    from openconvert.core.office import discover, locate

    _make_managed_dirs(monkeypatch, tmp_path)
    monkeypatch.setattr("openconvert.core.office.shutil.which", lambda _name: None)
    monkeypatch.setattr("openconvert.core.office._candidate_paths", lambda: iter(()))

    assert locate() is None
    assert discover().available is False


def test_office_command_includes_headless_flags(monkeypatch, tmp_path: Path):
    import subprocess

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
