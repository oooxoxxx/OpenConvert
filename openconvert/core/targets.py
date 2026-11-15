"""轉換目標（格式 / 操作）的宣告。

這裡只描述「有哪些目標」，不包含任何實作。UI 依此產生下拉選單，
轉換器依 ``converter`` 欄位被選出。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .kinds import MediaKind, kinds_for

CATEGORY_ORDER = ("影片", "音訊", "圖片", "PDF", "電子書")

# 副檔名別名，只用於「預設目標不要跟來源相同」的判斷。
_EXT_ALIASES = {"jpeg": "jpg", "tif": "tiff"}


@dataclass(frozen=True)
class TargetSpec:
    token: str
    label: str
    category: str
    converter: str
    extension: str
    kinds: frozenset[MediaKind]
    group_kinds: frozenset[MediaKind] = frozenset()
    group_min: int = 2
    needs_ffmpeg: bool = False
    description: str = ""

    def accepts(self, path: str | Path) -> bool:
        return bool(set(kinds_for(path)) & self.kinds)

    def is_group(self, path: str | Path) -> bool:
        return bool(set(kinds_for(path)) & self.group_kinds)


Video = MediaKind.VIDEO
Audio = MediaKind.AUDIO
Image = MediaKind.IMAGE
Pdf = MediaKind.PDF
Epub = MediaKind.EPUB
Cbz = MediaKind.CBZ


TARGETS: tuple[TargetSpec, ...] = (
    # ---------------------------------------------------------------- 影片
    TargetSpec(
        "mp4",
        "MP4 影片",
        "影片",
        "media",
        "mp4",
        frozenset({Video}),
        needs_ffmpeg=True,
        description="H.264 + AAC，相容性最好",
    ),
    TargetSpec(
        "mkv",
        "MKV 影片",
        "影片",
        "media",
        "mkv",
        frozenset({Video}),
        needs_ffmpeg=True,
        description="H.264 + AAC，可容納多字幕軌",
    ),
    TargetSpec(
        "webm",
        "WebM 影片",
        "影片",
        "media",
        "webm",
        frozenset({Video}),
        needs_ffmpeg=True,
        description="VP9 + Opus，適合網頁",
    ),
    TargetSpec(
        "mov",
        "MOV 影片",
        "影片",
        "media",
        "mov",
        frozenset({Video}),
        needs_ffmpeg=True,
        description="Apple QuickTime 容器",
    ),
    TargetSpec(
        "avi",
        "AVI 影片",
        "影片",
        "media",
        "avi",
        frozenset({Video}),
        needs_ffmpeg=True,
        description="舊式容器，相容老舊播放器",
    ),
    TargetSpec(
        "video-gif",
        "GIF 動畫",
        "影片",
        "media",
        "gif",
        frozenset({Video}),
        needs_ffmpeg=True,
        description="無聲動圖，建議縮小解析度",
    ),
    # ---------------------------------------------------------------- 音訊
    TargetSpec(
        "mp3",
        "MP3 音訊",
        "音訊",
        "media",
        "mp3",
        frozenset({Audio, Video}),
        needs_ffmpeg=True,
        description="最通用的音訊格式",
    ),
    TargetSpec(
        "m4a",
        "M4A 音訊",
        "音訊",
        "media",
        "m4a",
        frozenset({Audio, Video}),
        needs_ffmpeg=True,
        description="AAC 音訊，Apple 裝置常用",
    ),
    TargetSpec("aac", "AAC 音訊", "音訊", "media", "aac", frozenset({Audio, Video}), needs_ffmpeg=True),
    TargetSpec(
        "wav",
        "WAV 音訊",
        "音訊",
        "media",
        "wav",
        frozenset({Audio, Video}),
        needs_ffmpeg=True,
        description="無壓縮，檔案較大",
    ),
    TargetSpec(
        "flac",
        "FLAC 音訊",
        "音訊",
        "media",
        "flac",
        frozenset({Audio, Video}),
        needs_ffmpeg=True,
        description="無損壓縮",
    ),
    TargetSpec("ogg", "OGG 音訊", "音訊", "media", "ogg", frozenset({Audio, Video}), needs_ffmpeg=True),
    TargetSpec(
        "opus",
        "Opus 音訊",
        "音訊",
        "media",
        "opus",
        frozenset({Audio, Video}),
        needs_ffmpeg=True,
        description="低流量下音質最好",
    ),
    # ---------------------------------------------------------------- 圖片
    TargetSpec("png", "PNG 圖片", "圖片", "image", "png", frozenset({Image}), description="支援透明背景"),
    TargetSpec(
        "jpg", "JPEG 圖片", "圖片", "image", "jpg", frozenset({Image}), description="有損壓縮，適合照片"
    ),
    TargetSpec(
        "webp", "WebP 圖片", "圖片", "image", "webp", frozenset({Image}), description="檔案小、支援透明"
    ),
    TargetSpec("bmp", "BMP 圖片", "圖片", "image", "bmp", frozenset({Image})),
    TargetSpec(
        "tiff", "TIFF 圖片", "圖片", "image", "tiff", frozenset({Image}), description="印刷與掃描常用"
    ),
    TargetSpec(
        "ico", "ICO 圖示", "圖片", "image", "ico", frozenset({Image}), description="Windows 圖示，支援多尺寸"
    ),
    TargetSpec("image-gif", "GIF 圖片", "圖片", "image", "gif", frozenset({Image})),
    TargetSpec(
        "img-pdf",
        "合併為 PDF",
        "圖片",
        "image",
        "pdf",
        frozenset({Image}),
        group_kinds=frozenset({Image}),
        group_min=1,
        description="多張圖片合成一份 PDF",
    ),
    # ---------------------------------------------------------------- PDF
    TargetSpec(
        "pdf-merge",
        "合併 PDF",
        "PDF",
        "pdf",
        "pdf",
        frozenset({Pdf}),
        group_kinds=frozenset({Pdf}),
        group_min=2,
        description="把多份 PDF 依序合併",
    ),
    TargetSpec(
        "pdf-extract", "抽取頁面", "PDF", "pdf", "pdf", frozenset({Pdf}), description="用頁碼範圍產生新 PDF"
    ),
    TargetSpec(
        "pdf-png", "PDF → PNG", "PDF", "pdf", "png", frozenset({Pdf}), description="每頁輸出成一張 PNG"
    ),
    TargetSpec(
        "pdf-jpg", "PDF → JPEG", "PDF", "pdf", "jpg", frozenset({Pdf}), description="每頁輸出成一張 JPEG"
    ),
    # ---------------------------------------------------------------- 電子書
    TargetSpec(
        "epub",
        "EPUB 電子書",
        "電子書",
        "ebook",
        "epub",
        frozenset({Cbz, Image}),
        group_kinds=frozenset({Image}),
        group_min=1,
        description="可由 CBZ 或整批圖片產生",
    ),
    TargetSpec(
        "cbz",
        "CBZ 漫畫",
        "電子書",
        "ebook",
        "cbz",
        frozenset({Epub, Image}),
        group_kinds=frozenset({Image}),
        group_min=1,
        description="可由 EPUB 或整批圖片產生",
    ),
)

TARGETS_BY_TOKEN: dict[str, TargetSpec] = {spec.token: spec for spec in TARGETS}


def target_by_token(token: str) -> TargetSpec | None:
    return TARGETS_BY_TOKEN.get(token)


def collected_kinds(paths: list[str] | list[Path]) -> set[MediaKind]:
    found: set[MediaKind] = set()
    for path in paths:
        found.update(kinds_for(path))
    return found


def available_targets(paths: list[str] | list[Path]) -> list[TargetSpec]:
    """回傳目前佇列可用的目標，依類別排序。"""
    kinds = collected_kinds(paths)
    if not kinds:
        return []
    result: list[TargetSpec] = []
    for spec in TARGETS:
        if not (spec.kinds & kinds):
            continue
        if spec.group_kinds:
            eligible = sum(1 for p in paths if spec.is_group(p))
            if eligible < spec.group_min:
                continue
        result.append(spec)
    result.sort(
        key=lambda s: (
            CATEGORY_ORDER.index(s.category) if s.category in CATEGORY_ORDER else 99,
            TARGETS.index(s),
        )
    )
    return result


def preferred_target(paths: list[str] | list[Path], last_token: str | None) -> TargetSpec | None:
    """選擇預設目標：優先沿用上次使用且仍可用的格式。

    沒有歷史紀錄時，挑第一個「輸出格式和來源不同」的目標，
    避免預設把 PNG 轉成 PNG 這種沒有意義的選擇。
    """
    options = available_targets(paths)
    if not options:
        return None
    if last_token:
        for spec in options:
            if spec.token == last_token:
                return spec
    source_exts = {
        _EXT_ALIASES.get(Path(p).suffix.lower().lstrip("."), Path(p).suffix.lower().lstrip("."))
        for p in paths
    }
    for spec in options:
        if spec.extension not in source_exts:
            return spec
    return options[0]


def plan_groups(spec: TargetSpec, paths: list[str] | list[Path]) -> list[list[Path]]:
    """依目標規格，把檔案分成「一次轉換一組」的分組。

    群組型目標（合併 PDF、圖片轉 PDF、圖片轉電子書）會把所有符合的檔案
    收在同一組；其餘檔案各自獨立成一個工作。
    """
    path_list = [Path(p) for p in paths]
    if not spec.group_kinds:
        return [[p] for p in path_list]

    eligible = [p for p in path_list if spec.is_group(p)]
    others = [p for p in path_list if not spec.is_group(p)]

    groups: list[list[Path]] = []
    if len(eligible) >= spec.group_min:
        groups.append(eligible)
    else:
        groups.extend([[p] for p in eligible])
    groups.extend([[p] for p in others])
    return groups
