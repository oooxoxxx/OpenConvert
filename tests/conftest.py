"""共用測試設定與樣本檔產生器。"""

from __future__ import annotations

import os
import struct
import subprocess
import zipfile
import zlib
from pathlib import Path

import pytest

# 必須在匯入 Qt 之前設定，讓 CI 不需要實體螢幕
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


# --------------------------------------------------------------------------- 環境隔離


@pytest.fixture(autouse=True)
def isolated_app_dirs(tmp_path, monkeypatch):
    """讓設定與紀錄寫到暫存目錄，不污染真實使用者資料。"""
    monkeypatch.setenv("OPENCONVERT_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("OPENCONVERT_DATA_DIR", str(tmp_path / "data"))
    yield


@pytest.fixture(scope="session")
def tools():
    from openconvert.core.ffmpeg import discover

    return discover()


@pytest.fixture(scope="session")
def ffmpeg_available(tools) -> bool:
    return tools.available


def require_ffmpeg(tools):
    if not tools.available:
        pytest.skip("系統沒有 FFmpeg，跳過媒體測試")


# --------------------------------------------------------------------------- 圖片


@pytest.fixture
def png_file(tmp_path: Path) -> Path:
    from PIL import Image

    path = tmp_path / "sample.png"
    image = Image.new("RGB", (80, 60), (200, 40, 40))
    image.save(path, "PNG")
    image.close()
    return path


@pytest.fixture
def rgba_png_file(tmp_path: Path) -> Path:
    from PIL import Image

    path = tmp_path / "alpha.png"
    image = Image.new("RGBA", (40, 40), (0, 0, 0, 0))
    for x in range(20):
        for y in range(20):
            image.putpixel((x, y), (0, 128, 255, 255))
    image.save(path, "PNG")
    image.close()
    return path


@pytest.fixture
def png_series(tmp_path: Path) -> list[Path]:
    from PIL import Image

    folder = tmp_path / "pages"
    folder.mkdir()
    paths: list[Path] = []
    for index in range(3):
        path = folder / f"page_{index + 1}.png"
        image = Image.new("RGB", (40, 50), (20 * index, 90, 160))
        image.save(path, "PNG")
        image.close()
        paths.append(path)
    return paths


# --------------------------------------------------------------------------- PDF


@pytest.fixture
def pdf_file(tmp_path: Path) -> Path:
    return _make_pdf(tmp_path / "doc.pdf", pages=3, label="A")


@pytest.fixture
def second_pdf_file(tmp_path: Path) -> Path:
    return _make_pdf(tmp_path / "doc2.pdf", pages=2, label="B")


def _make_pdf(path: Path, pages: int, label: str) -> Path:
    from pypdf import PdfWriter

    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=200, height=300)
    writer.add_metadata({"/Title": f"Test {label}"})
    with path.open("wb") as handle:
        writer.write(handle)
    writer.close()
    return path


# --------------------------------------------------------------------------- 電子書


@pytest.fixture
def cbz_file(tmp_path: Path, png_series: list[Path]) -> Path:
    path = tmp_path / "comic.cbz"
    with zipfile.ZipFile(path, "w") as archive:
        for index, image in enumerate(png_series):
            archive.writestr(f"{index + 1:02d}.png", image.read_bytes())
    return path


# --------------------------------------------------------------------------- 媒體


@pytest.fixture(scope="session")
def sample_mp4(tmp_path_factory, tools) -> Path:
    """用 FFmpeg 的測試訊號源產生 1 秒短片。"""
    if not tools.available:
        pytest.skip("系統沒有 FFmpeg")
    folder = tmp_path_factory.mktemp("media")
    path = folder / "clip.mp4"
    command = [
        str(tools.ffmpeg),
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-f",
        "lavfi",
        "-i",
        "testsrc=duration=1:size=160x120:rate=10",
        "-f",
        "lavfi",
        "-i",
        "sine=frequency=440:duration=1",
        "-shortest",
        "-c:v",
        "libx264",
        "-preset",
        "ultrafast",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        str(path),
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        pytest.skip(f"無法產生測試影片：{result.stderr[-300:]}")
    return path


# --------------------------------------------------------------------------- 其他


def make_noise_wav(path: Path, seconds: float = 0.5) -> Path:
    """不需要 FFmpeg 就能產生合法 WAV。"""
    sample_rate = 8000
    frames = int(sample_rate * seconds)
    data = b"".join(struct.pack("<h", (i % 40) * 200 - 4000) for i in range(frames))
    with path.open("wb") as handle:
        handle.write(b"RIFF")
        handle.write(struct.pack("<I", 36 + len(data)))
        handle.write(b"WAVEfmt ")
        handle.write(struct.pack("<IHHIIHH", 16, 1, 1, sample_rate, sample_rate * 2, 2, 16))
        handle.write(b"data")
        handle.write(struct.pack("<I", len(data)))
        handle.write(data)
    return path


__all__ = ["make_noise_wav", "require_ffmpeg", "zlib"]
