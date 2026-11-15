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


@pytest.fixture(scope="session")
def office_tools():
    from openconvert.core.office import discover

    return discover()


def require_office(office_tools):
    if not office_tools.available:
        pytest.skip("系統沒有 LibreOffice，跳過 Office 文件測試")


def find_system_font() -> Path | None:
    """找一個可用來測試的字型檔；找不到時回傳 None。"""
    candidates = [
        Path(r"C:\Windows\Fonts\arial.ttf"),
        Path(r"C:\Windows\Fonts\calibri.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        Path("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"),
        Path("/System/Library/Fonts/Supplemental/Arial.ttf"),
        Path("/Library/Fonts/Arial.ttf"),
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    for root in (Path("/usr/share/fonts"), Path("/Library/Fonts")):
        if root.is_dir():
            for match in root.rglob("*.ttf"):
                return match
    return None


# --------------------------------------------------------------------------- 文字 / 文件


@pytest.fixture
def md_file(tmp_path: Path) -> Path:
    path = tmp_path / "doc.md"
    path.write_text(
        "# 主標題\n\n"
        "這是一段文字，包含 **粗體** 與 *斜體*。\n\n"
        "- 項目一\n- 項目二\n\n"
        "| 欄位 | 值 |\n| --- | --- |\n| a | 1 |\n",
        encoding="utf-8",
    )
    return path


@pytest.fixture
def html_file(tmp_path: Path) -> Path:
    path = tmp_path / "page.html"
    path.write_text(
        "<!DOCTYPE html><html><head><title>測試</title></head><body>"
        "<h1>標題</h1><p>段落一</p><ul><li>甲</li><li>乙</li></ul>"
        "<table><tr><th>A</th><th>B</th></tr><tr><td>1</td><td>2</td></tr></table>"
        "</body></html>",
        encoding="utf-8",
    )
    return path


@pytest.fixture
def txt_file(tmp_path: Path) -> Path:
    path = tmp_path / "note.txt"
    path.write_text("第一段文字。\n\n第二段文字，含中文與 English。\n", encoding="utf-8")
    return path


@pytest.fixture
def docx_file(tmp_path: Path) -> Path:
    from docx import Document

    document = Document()
    document.add_heading("報告標題", level=1)
    paragraph = document.add_paragraph("這是一段")
    run = paragraph.add_run("粗體")
    run.bold = True
    document.add_paragraph("項目一", style="List Bullet")
    table = document.add_table(rows=2, cols=2)
    table.cell(0, 0).text = "A"
    table.cell(0, 1).text = "B"
    table.cell(1, 0).text = "1"
    table.cell(1, 1).text = "2"

    path = tmp_path / "report.docx"
    document.save(path)
    return path


# --------------------------------------------------------------------------- 資料


@pytest.fixture
def csv_file(tmp_path: Path) -> Path:
    path = tmp_path / "data.csv"
    path.write_text("name,age,city\nAlice,30,台北\nBob,25,高雄\n", encoding="utf-8")
    return path


@pytest.fixture
def json_file(tmp_path: Path) -> Path:
    path = tmp_path / "data.json"
    path.write_text(
        '[{"name": "Alice", "age": 30}, {"name": "Bob", "age": 25}]',
        encoding="utf-8",
    )
    return path


@pytest.fixture
def xlsx_file(tmp_path: Path) -> Path:
    from openpyxl import Workbook

    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "成績"
    worksheet.append(["name", "score"])
    worksheet.append(["Alice", 90])
    worksheet.append(["Bob", 80])
    path = tmp_path / "sheet.xlsx"
    workbook.save(path)
    workbook.close()
    return path


# --------------------------------------------------------------------------- 字幕


@pytest.fixture
def srt_file(tmp_path: Path) -> Path:
    path = tmp_path / "movie.srt"
    path.write_text(
        "1\n00:00:01,000 --> 00:00:03,500\n<i>Hello</i> world\n\n"
        "2\n00:00:04,000 --> 00:00:06,000\nSecond line\n",
        encoding="utf-8",
    )
    return path


@pytest.fixture
def ass_file(tmp_path: Path) -> Path:
    path = tmp_path / "movie.ass"
    path.write_text(
        "[Script Info]\nScriptType: v4.00+\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
        "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
        "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
        "Style: Default,Arial,64,&H00FFFFFF,&H000000FF,&H00000000,&H64000000,0,0,0,0,100,"
        "100,0,0,1,3,0,2,40,40,40,1\n\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
        "Dialogue: 0,0:00:01.00,0:00:03.50,Default,,0,0,0,,{\\i1}Hello{\\i0} world\n",
        encoding="utf-8",
    )
    return path


@pytest.fixture(scope="session")
def system_font() -> Path:
    font = find_system_font()
    if font is None:
        pytest.skip("系統找不到可用字型，跳過字型測試")
    return font


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
def animated_gif_file(tmp_path: Path) -> Path:
    from PIL import Image

    path = tmp_path / "anim.gif"
    frames = [
        Image.new("RGBA", (40, 40), (255, 0, 0, 255)),
        Image.new("RGBA", (40, 40), (0, 255, 0, 255)),
        Image.new("RGBA", (40, 40), (0, 0, 255, 255)),
    ]
    frames[0].save(path, "GIF", save_all=True, append_images=frames[1:], duration=120, loop=0)
    for frame in frames:
        frame.close()
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
