"""字幕轉換：SRT、WebVTT、ASS/SSA。

只處理「時間軸 + 文字」；ASS 的複雜排版樣式不會原樣保留，
但文字、斜體與粗體會盡量對應。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from ..core.errors import ConversionError
from ..core.paths import resolve_output
from ..core.textio import read_text, write_text
from .base import ConvertContext, Converter

_TIME = re.compile(r"(?:(\d+):)?(\d{1,2}):(\d{1,2})[.,](\d{1,3})")
_ASS_TIME = re.compile(r"(\d+):(\d{2}):(\d{2})[.:](\d{1,2})")
_ASS_TAG = re.compile(r"\{[^}]*\}")


@dataclass
class Cue:
    start: float  # 秒
    end: float
    text: str


# --------------------------------------------------------------------------- 解析


def _parse_time(raw: str) -> float:
    match = _TIME.search(raw.strip())
    if not match:
        raise ValueError(raw)
    hours = int(match.group(1) or 0)
    minutes = int(match.group(2))
    seconds = int(match.group(3))
    millis = int(match.group(4).ljust(3, "0")[:3])
    return hours * 3600 + minutes * 60 + seconds + millis / 1000


def _parse_ass_time(raw: str) -> float:
    match = _ASS_TIME.search(raw.strip())
    if not match:
        raise ValueError(raw)
    hours, minutes, seconds = (int(match.group(i)) for i in (1, 2, 3))
    centis = int(match.group(4).ljust(2, "0")[:2])
    return hours * 3600 + minutes * 60 + seconds + centis / 100


def parse_srt(text: str) -> list[Cue]:
    cues: list[Cue] = []
    blocks = re.split(r"\r?\n\s*\r?\n", text.replace("\ufeff", "").strip())
    for block in blocks:
        lines = block.splitlines()
        if lines and lines[0].strip().isdigit():
            lines = lines[1:]
        if not lines or "-->" not in lines[0]:
            continue
        start_raw, end_raw = lines[0].split("-->", 1)
        try:
            start, end = _parse_time(start_raw), _parse_time(end_raw)
        except ValueError:
            continue
        cues.append(Cue(start, end, "\n".join(lines[1:]).strip()))
    return cues


def parse_vtt(text: str) -> list[Cue]:
    lines = text.replace("\ufeff", "").splitlines()
    blocks: list[list[str]] = []
    current: list[str] = []
    for line in lines:
        if not line.strip():
            if current:
                blocks.append(current)
                current = []
            continue
        if not current and (
            line.startswith("WEBVTT")
            or line.startswith("NOTE")
            or line.startswith("STYLE")
            or line.startswith("REGION")
        ):
            continue
        current.append(line)
    if current:
        blocks.append(current)

    cues: list[Cue] = []
    for block in blocks:
        index = next((i for i, line in enumerate(block) if "-->" in line), None)
        if index is None:
            continue
        start_raw, rest = block[index].split("-->", 1)
        end_raw = rest.strip().split(" ")[0]
        try:
            start, end = _parse_time(start_raw), _parse_time(end_raw)
        except ValueError:
            continue
        cues.append(Cue(start, end, "\n".join(block[index + 1 :]).strip()))
    return cues


def parse_ass(text: str) -> list[Cue]:
    cues: list[Cue] = []
    section = ""
    fields: list[str] | None = None
    for line in text.replace("\ufeff", "").splitlines():
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            section = stripped[1:-1].strip().lower()
            fields = None
            continue
        if section != "events":
            continue
        if stripped.lower().startswith("format:"):
            fields = [part.strip().lower() for part in stripped.split(":", 1)[1].split(",")]
            continue
        if not stripped.lower().startswith("dialogue:"):
            continue

        payload = stripped.split(":", 1)[1]
        if fields:
            parts = payload.split(",", len(fields) - 1)
            data = dict(zip(fields, parts, strict=False))
            start_raw = data.get("start", "")
            end_raw = data.get("end", "")
            body = data.get("text", "")
        else:
            parts = payload.split(",", 9)
            if len(parts) < 10:
                continue
            start_raw, end_raw, body = parts[1], parts[2], parts[9]

        try:
            start, end = _parse_ass_time(start_raw), _parse_ass_time(end_raw)
        except ValueError:
            continue
        cues.append(Cue(start, end, _ass_to_plain(body)))
    return cues


def _ass_to_plain(text: str) -> str:
    text = _ASS_TAG.sub("", text)
    text = text.replace("\\N", "\n").replace("\\n", "\n")
    return text.replace("\\h", " ").strip()


# --------------------------------------------------------------------------- 輸出


def _srt_time(seconds: float) -> str:
    millis = max(0, round(seconds * 1000))
    hours, rest = divmod(millis, 3_600_000)
    minutes, rest = divmod(rest, 60_000)
    secs, ms = divmod(rest, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{ms:03d}"


def _vtt_time(seconds: float) -> str:
    return _srt_time(seconds).replace(",", ".")


def _ass_time(seconds: float) -> str:
    centis = max(0, round(seconds * 100))
    hours, rest = divmod(centis, 360_000)
    minutes, rest = divmod(rest, 6000)
    secs, cs = divmod(rest, 100)
    return f"{hours:d}:{minutes:02d}:{secs:02d}.{cs:02d}"


def _strip_tags(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text).strip()


def _html_to_ass(text: str) -> str:
    replacements = (
        ("<i>", r"{\i1}"),
        ("</i>", r"{\i0}"),
        ("<em>", r"{\i1}"),
        ("</em>", r"{\i0}"),
        ("<b>", r"{\b1}"),
        ("</b>", r"{\b0}"),
        ("<strong>", r"{\b1}"),
        ("</strong>", r"{\b0}"),
        ("<u>", r"{\u1}"),
        ("</u>", r"{\u0}"),
        ("<br>", "\\N"),
        ("<br/>", "\\N"),
        ("<br />", "\\N"),
    )
    text = text.replace("{", r"\{").replace("}", r"\}")
    for source, target in replacements:
        text = re.sub(source, lambda _m, t=target: t, text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    return text.replace("\n", "\\N").strip()


def to_srt(cues: list[Cue]) -> str:
    blocks = []
    for index, cue in enumerate(cues, start=1):
        body = _strip_tags(cue.text)
        blocks.append(f"{index}\n{_srt_time(cue.start)} --> {_srt_time(cue.end)}\n{body}")
    return "\n\n".join(blocks) + "\n"


def to_vtt(cues: list[Cue]) -> str:
    blocks = ["WEBVTT"]
    for cue in cues:
        body = _strip_tags(cue.text)
        blocks.append(f"{_vtt_time(cue.start)} --> {_vtt_time(cue.end)}\n{body}")
    return "\n\n".join(blocks) + "\n"


_ASS_HEADER = """[Script Info]
; Generated by OpenConvert
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Noto Sans TC,64,&H00FFFFFF,&H000000FF,&H00000000,&H64000000,0,0,0,0,100,100,0,0,1,3,0,2,60,60,60,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def to_ass(cues: list[Cue]) -> str:
    lines = [_ASS_HEADER.rstrip("\n")]
    for cue in cues:
        body = _html_to_ass(cue.text)
        lines.append(f"Dialogue: 0,{_ass_time(cue.start)},{_ass_time(cue.end)},Default,,0,0,0,,{body}")
    return "\n".join(lines) + "\n"


_PARSERS = {
    "srt": parse_srt,
    "vtt": parse_vtt,
    "ass": parse_ass,
    "ssa": parse_ass,
}


class SubtitleConverter(Converter):
    name = "subtitle"

    def convert(self, ctx: ConvertContext) -> list[Path]:
        self.ensure_source_exists(ctx)
        self.ensure_kind(ctx, {"subtitle"})

        source = ctx.source
        extension = source.suffix.lstrip(".").lower()
        parser = _PARSERS.get(extension)
        if parser is None:
            raise ConversionError(f"不支援的字幕格式：{source.suffix or source.name}")

        try:
            cues = parser(read_text(source))
        except OSError as exc:
            raise ConversionError(f"無法讀取「{source.name}」：{exc}", detail=str(exc)) from exc

        if not cues:
            raise ConversionError(f"「{source.name}」中找不到任何字幕。")

        token = ctx.token
        if token == "sub-srt":
            content = to_srt(cues)
        elif token == "sub-vtt":
            content = to_vtt(cues)
        elif token == "sub-ass":
            content = to_ass(cues)
        else:
            raise ConversionError(f"不支援的字幕目標：{token}")

        ctx.report(0.7, "寫入字幕")
        dest = resolve_output(source, ctx.output_dir, ctx.job.target.extension, overwrite=ctx.overwrite)
        ctx.track(dest)
        write_text(dest, content)
        ctx.report(1.0, "完成")

        if not dest.exists() or dest.stat().st_size == 0:
            dest.unlink(missing_ok=True)
            raise ConversionError("字幕轉換失敗，沒有產生有效檔案。")
        return [dest]


__all__ = [
    "Cue",
    "SubtitleConverter",
    "parse_ass",
    "parse_srt",
    "parse_vtt",
    "to_ass",
    "to_srt",
    "to_vtt",
]
