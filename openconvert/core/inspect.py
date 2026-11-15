"""檔案資訊檢視：不轉換，只讀取並整理可讀的中繼資料。"""

from __future__ import annotations

import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image

from .errors import ConversionError
from .ffmpeg import FFmpegTools, MediaInfo, StreamInfo, probe
from .kinds import MediaKind, primary_kind
from .paths import human_size


@dataclass(frozen=True)
class InfoRow:
    label: str
    value: str


@dataclass
class FileSummary:
    path: Path
    kind: MediaKind
    rows: list[InfoRow] = field(default_factory=list)
    streams: list[StreamInfo] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    raw: dict = field(default_factory=dict)

    @property
    def title(self) -> str:
        return self.path.name


def _duration_text(seconds: float) -> str:
    if seconds <= 0:
        return "—"
    total = round(seconds)
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def describe(path: str | Path, tools: FFmpegTools) -> FileSummary:
    """回傳檔案的摘要資訊。

    這個函式不會修改任何檔案，也不會上傳資料。
    """
    target = Path(path)
    if not target.exists():
        raise ConversionError(f"找不到檔案：{target}")

    kind = primary_kind(target)
    summary = FileSummary(path=target, kind=kind)
    summary.rows.append(InfoRow("檔案名稱", target.name))
    summary.rows.append(InfoRow("檔案大小", human_size(target.stat().st_size)))
    summary.rows.append(InfoRow("類型", kind.value))

    if kind in (MediaKind.VIDEO, MediaKind.AUDIO):
        _describe_media(target, tools, summary)
    elif kind is MediaKind.IMAGE:
        _describe_image(target, summary)
    elif kind is MediaKind.PDF:
        _describe_pdf(target, summary)
    elif kind in (MediaKind.EPUB, MediaKind.CBZ):
        _describe_archive(target, summary)
    else:
        summary.warnings.append("這個檔案類型沒有可顯示的額外資訊。")

    return summary


def _describe_media(target: Path, tools: FFmpegTools, summary: FileSummary) -> None:
    if not tools.probing_available:
        summary.warnings.append("找不到 FFprobe，無法讀取媒體詳細資訊。")
        return
    info: MediaInfo = probe(target, tools)
    summary.raw = info.raw
    summary.streams = list(info.streams)

    summary.rows.append(InfoRow("容器格式", info.format_long_name or info.format_name or "—"))
    if info.duration:
        summary.rows.append(InfoRow("長度", _duration_text(info.duration)))
    if info.bit_rate:
        summary.rows.append(InfoRow("整體位元率", f"{info.bit_rate // 1000} kbps"))

    video = info.video_stream
    if video:
        summary.rows.append(InfoRow("視訊編碼", video.codec_long_name or video.codec_name))
        if video.resolution:
            summary.rows.append(InfoRow("解析度", video.resolution))
        if video.fps:
            summary.rows.append(InfoRow("影格率", f"{video.fps:.3g} fps"))
        if video.pixel_format:
            summary.rows.append(InfoRow("像素格式", video.pixel_format))

    audio = info.audio_stream
    if audio:
        summary.rows.append(InfoRow("音訊編碼", audio.codec_long_name or audio.codec_name))
        if audio.sample_rate:
            summary.rows.append(InfoRow("取樣率", f"{audio.sample_rate} Hz"))
        if audio.channels:
            summary.rows.append(InfoRow("聲道數", str(audio.channels)))


def _describe_image(target: Path, summary: FileSummary) -> None:
    try:
        with Image.open(target) as image:
            summary.rows.append(InfoRow("尺寸", f"{image.width} × {image.height}"))
            summary.rows.append(InfoRow("色彩模式", image.mode))
            summary.rows.append(InfoRow("圖片格式", image.format or "—"))
            frames = getattr(image, "n_frames", 1)
            if frames > 1:
                summary.rows.append(InfoRow("影格數", f"{frames}（動畫）"))
            dpi = image.info.get("dpi")
            if dpi:
                summary.rows.append(InfoRow("DPI", f"{round(dpi[0])} × {round(dpi[1])}"))
    except (OSError, ValueError) as exc:
        summary.warnings.append(f"無法讀取圖片資訊：{exc}")


def _describe_pdf(target: Path, summary: FileSummary) -> None:
    try:
        from pypdf import PdfReader

        reader = PdfReader(str(target))
        pages = len(reader.pages)
        summary.rows.append(InfoRow("頁數", str(pages)))
        if reader.is_encrypted:
            summary.rows.append(InfoRow("加密", "有（可能需要密碼）"))
        meta = reader.metadata
        if meta:
            for key, label in (
                ("/Title", "標題"),
                ("/Author", "作者"),
                ("/Creator", "建立工具"),
                ("/Producer", "產生器"),
            ):
                value = meta.get(key)
                if value:
                    summary.rows.append(InfoRow(label, str(value)))
    except Exception as exc:  # pypdf 的例外種類很多
        summary.warnings.append(f"無法讀取 PDF 資訊：{exc}")


def _describe_archive(target: Path, summary: FileSummary) -> None:
    images = {"jpg", "jpeg", "png", "gif", "webp", "bmp", "tif", "tiff", "avif"}
    try:
        with zipfile.ZipFile(target) as archive:
            names = [n for n in archive.namelist() if not n.endswith("/")]
            image_count = sum(1 for n in names if Path(n).suffix.lstrip(".").lower() in images)
            summary.rows.append(InfoRow("內容檔案數", str(len(names))))
            summary.rows.append(InfoRow("圖片頁數", str(image_count)))
    except (zipfile.BadZipFile, OSError) as exc:
        summary.warnings.append(f"無法讀取壓縮檔資訊：{exc}")
