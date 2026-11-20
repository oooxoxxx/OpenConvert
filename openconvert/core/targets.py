"""轉換目標（格式 / 操作）的宣告。

這裡只描述「有哪些目標」，不包含任何實作。UI 依此產生下拉選單，
轉換器依 ``converter`` 欄位被選出。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .kinds import ALL_KINDS, MediaKind, extension_of, kinds_for

CATEGORY_ORDER = ("影片", "音訊", "圖片", "PDF", "電子書", "文件", "資料", "字幕", "字型", "壓縮")

# 副檔名別名，只用於「預設目標不要跟來源相同」的判斷。
_EXT_ALIASES = {
    "jpeg": "jpg",
    "tif": "tiff",
    "heif": "heic",
    "aif": "aiff",
    "htm": "html",
    "markdown": "md",
}


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
    needs_office: bool = False
    description: str = ""
    #: 進一步限制來源副檔名（用於同一類型下差異很大的格式，例如 DOCX 與 RTF）。
    source_extensions: frozenset[str] = frozenset()

    def accepts(self, path: str | Path) -> bool:
        if self.source_extensions and extension_of(path) not in self.source_extensions:
            return False
        return bool(set(kinds_for(path)) & self.kinds)

    def is_group(self, path: str | Path) -> bool:
        return bool(set(kinds_for(path)) & self.group_kinds)


Video = MediaKind.VIDEO
Audio = MediaKind.AUDIO
Image = MediaKind.IMAGE
Pdf = MediaKind.PDF
Epub = MediaKind.EPUB
Cbz = MediaKind.CBZ
Text = MediaKind.TEXT
Markup = MediaKind.MARKUP
Office = MediaKind.OFFICE
Sheet = MediaKind.SHEET
Data = MediaKind.DATA
Subtitle = MediaKind.SUBTITLE
Font = MediaKind.FONT

DATA_KINDS = frozenset({Data, Sheet})


def _doc(
    token: str,
    label: str,
    extension: str,
    source: str,
    *,
    office: bool,
    description: str = "",
) -> TargetSpec:
    return TargetSpec(
        token,
        label,
        "文件",
        "document",
        extension,
        frozenset({Office}),
        needs_office=office,
        description=description,
        source_extensions=frozenset({source}),
    )


def _sheet(
    token: str,
    label: str,
    extension: str,
    sources: set[str],
    *,
    office: bool = True,
    description: str = "",
) -> TargetSpec:
    return TargetSpec(
        token,
        label,
        "文件",
        "document",
        extension,
        frozenset({Sheet}),
        needs_office=office,
        description=description,
        source_extensions=frozenset(sources),
    )


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
        "m4v",
        "M4V 影片",
        "影片",
        "media",
        "m4v",
        frozenset({Video}),
        needs_ffmpeg=True,
        description="H.264 + AAC，Apple 裝置常用",
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
        "flv",
        "FLV 影片",
        "影片",
        "media",
        "flv",
        frozenset({Video}),
        needs_ffmpeg=True,
        description="H.264 + AAC，舊式網頁播放器",
    ),
    TargetSpec(
        "wmv",
        "WMV 影片",
        "影片",
        "media",
        "wmv",
        frozenset({Video}),
        needs_ffmpeg=True,
        description="Windows Media 格式",
    ),
    TargetSpec(
        "ogv",
        "OGV 影片",
        "影片",
        "media",
        "ogv",
        frozenset({Video}),
        needs_ffmpeg=True,
        description="Theora + Vorbis，開源容器",
    ),
    TargetSpec(
        "ts",
        "TS 影片",
        "影片",
        "media",
        "ts",
        frozenset({Video}),
        needs_ffmpeg=True,
        description="H.264 + AAC，串流與錄影常用",
    ),
    TargetSpec(
        "video-merge",
        "合併影片",
        "影片",
        "media",
        "mp4",
        frozenset({Video}),
        group_kinds=frozenset({Video}),
        group_min=2,
        needs_ffmpeg=True,
        description="把多支影片依序合併成一支 MP4（合併型）；解析度不同會自動補邊對齊",
    ),
    TargetSpec(
        "video-split",
        "截取影片片段",
        "影片",
        "media",
        "mp4",
        frozenset({Video}),
        needs_ffmpeg=True,
        description="依起訖時間截取片段並轉存 MP4（重新編碼，切割點精準）",
    ),
    TargetSpec(
        "video-rotate",
        "影片旋轉／翻轉",
        "影片",
        "media",
        "mp4",
        frozenset({Video}),
        needs_ffmpeg=True,
        description="旋轉 90／180／270 度或水平／垂直翻轉，輸出 MP4",
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
    TargetSpec(
        "video-frames",
        "抽出影格（PNG）",
        "影片",
        "media",
        "png",
        frozenset({Video}),
        needs_ffmpeg=True,
        description="依指定影格率輸出 PNG，另存到新資料夾",
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
    TargetSpec(
        "m4b",
        "M4B 有聲書",
        "音訊",
        "media",
        "m4b",
        frozenset({Audio, Video}),
        needs_ffmpeg=True,
        description="AAC 有聲書容器，可記住播放位置",
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
    TargetSpec(
        "aiff",
        "AIFF 音訊",
        "音訊",
        "media",
        "aiff",
        frozenset({Audio, Video}),
        needs_ffmpeg=True,
        description="Apple 無壓縮音訊",
    ),
    TargetSpec(
        "wma",
        "WMA 音訊",
        "音訊",
        "media",
        "wma",
        frozenset({Audio, Video}),
        needs_ffmpeg=True,
        description="Windows Media 音訊",
    ),
    TargetSpec(
        "ac3",
        "AC3 音訊",
        "音訊",
        "media",
        "ac3",
        frozenset({Audio, Video}),
        needs_ffmpeg=True,
        description="電影常用的環繞音效格式",
    ),
    TargetSpec(
        "audio-merge",
        "合併音訊",
        "音訊",
        "media",
        "mp3",
        frozenset({Audio}),
        group_kinds=frozenset({Audio}),
        group_min=2,
        needs_ffmpeg=True,
        description="把多個音訊檔依序接成一份 MP3（合併型）；取樣率不同會自動重採樣",
    ),
    # ---------------------------------------------------------------- 圖片
    TargetSpec("png", "PNG 圖片", "圖片", "image", "png", frozenset({Image}), description="支援透明背景"),
    TargetSpec(
        "jpg", "JPEG 圖片", "圖片", "image", "jpg", frozenset({Image}), description="有損壓縮，適合照片"
    ),
    TargetSpec(
        "webp", "WebP 圖片", "圖片", "image", "webp", frozenset({Image}), description="檔案小、支援透明"
    ),
    TargetSpec(
        "avif",
        "AVIF 圖片",
        "圖片",
        "image",
        "avif",
        frozenset({Image}),
        description="新世代格式，壓縮率最佳、支援透明",
    ),
    TargetSpec(
        "heic",
        "HEIC 圖片",
        "圖片",
        "image",
        "heic",
        frozenset({Image}),
        description="iPhone 預設照片格式",
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
        "apng",
        "APNG 動畫",
        "圖片",
        "image",
        "png",
        frozenset({Image}),
        description="可保留動畫與透明的 PNG",
    ),
    TargetSpec(
        "img-rotate",
        "圖片旋轉",
        "圖片",
        "image",
        "png",
        frozenset({Image}),
        description="旋轉 90／180／270 度，輸出 PNG（動畫只處理第一格）",
    ),
    TargetSpec(
        "img-flip",
        "圖片翻轉",
        "圖片",
        "image",
        "png",
        frozenset({Image}),
        description="水平或垂直翻轉，輸出 PNG（動畫只處理第一格）",
    ),
    TargetSpec(
        "img-crop",
        "圖片裁切比例",
        "圖片",
        "image",
        "png",
        frozenset({Image}),
        description="置中裁切成指定比例（例如 16:9、1:1），輸出 PNG",
    ),
    TargetSpec(
        "images-video",
        "圖片轉影片",
        "圖片",
        "media",
        "mp4",
        frozenset({Image}),
        group_kinds=frozenset({Image}),
        group_min=1,
        needs_ffmpeg=True,
        description="整批圖片合成一支 MP4（合併型）",
    ),
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
    TargetSpec(
        "pdf-txt",
        "PDF → 純文字",
        "PDF",
        "pdf",
        "txt",
        frozenset({Pdf}),
        description="抽出文字層，掃描檔可能沒有文字",
    ),
    TargetSpec(
        "pdf-cbz",
        "PDF → CBZ",
        "PDF",
        "pdf",
        "cbz",
        frozenset({Pdf}),
        description="每頁轉成圖片後打包成漫畫壓縮檔",
    ),
    TargetSpec(
        "pdf-encrypt",
        "PDF 加密",
        "PDF",
        "pdf",
        "pdf",
        frozenset({Pdf}),
        description="為 PDF 加上開啟密碼（AES 加密），需在選項填入密碼",
    ),
    TargetSpec(
        "pdf-decrypt",
        "PDF 解除密碼",
        "PDF",
        "pdf",
        "pdf",
        frozenset({Pdf}),
        description="移除 PDF 的開啟密碼，需在選項填入原密碼",
    ),
    TargetSpec(
        "pdf-compress",
        "PDF 壓縮",
        "PDF",
        "pdf",
        "pdf",
        frozenset({Pdf}),
        description="重新壓縮 PDF 內容串流以縮小檔案（不影響版面）",
    ),
    # ---------------------------------------------------------------- 電子書
    TargetSpec(
        "epub",
        "EPUB 電子書",
        "電子書",
        "ebook",
        "epub",
        frozenset({Cbz, Image, Text, Markup}),
        group_kinds=frozenset({Image}),
        group_min=1,
        description="可由 CBZ、整批圖片、TXT／Markdown／HTML 產生",
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
    TargetSpec(
        "book-pdf",
        "CBZ → PDF",
        "電子書",
        "ebook",
        "pdf",
        frozenset({Cbz}),
        description="把整本漫畫壓縮檔轉成 PDF",
    ),
    TargetSpec(
        "epub-txt",
        "EPUB → 純文字",
        "電子書",
        "ebook",
        "txt",
        frozenset({Epub}),
        description="依閱讀順序抽出文字，不保留排版",
    ),
    TargetSpec(
        "epub-pdf",
        "EPUB → PDF",
        "電子書",
        "ebook",
        "pdf",
        frozenset({Epub}),
        needs_office=True,
        description="把整本 EPUB 排版成 PDF（需要 LibreOffice）；純圖片漫畫 EPUB 也支援",
    ),
    # ---------------------------------------------------------------- 文件
    TargetSpec(
        "md-html",
        "Markdown → HTML",
        "文件",
        "document",
        "html",
        frozenset({Text}),
        description="支援表格、程式碼區塊與標題",
        source_extensions=frozenset({"md", "markdown"}),
    ),
    TargetSpec(
        "html-md",
        "HTML → Markdown",
        "文件",
        "document",
        "md",
        frozenset({Markup}),
        description="保留標題、清單、連結與表格",
    ),
    TargetSpec(
        "html-txt",
        "HTML → 純文字",
        "文件",
        "document",
        "txt",
        frozenset({Markup}),
        description="去除標籤，保留段落",
    ),
    TargetSpec(
        "docx-txt",
        "DOCX → 純文字",
        "文件",
        "document",
        "txt",
        frozenset({Office}),
        description="段落、清單與表格依序輸出",
        source_extensions=frozenset({"docx"}),
    ),
    TargetSpec(
        "docx-md",
        "DOCX → Markdown",
        "文件",
        "document",
        "md",
        frozenset({Office}),
        description="標題、清單、粗斜體與表格",
        source_extensions=frozenset({"docx"}),
    ),
    TargetSpec(
        "docx-html",
        "DOCX → HTML",
        "文件",
        "document",
        "html",
        frozenset({Office}),
        description="保留標題與段落結構",
        source_extensions=frozenset({"docx"}),
    ),
    TargetSpec(
        "md-docx",
        "Markdown → DOCX",
        "文件",
        "document",
        "docx",
        frozenset({Text}),
        needs_office=True,
        description="Markdown 排版成 Word 文件（需要 LibreOffice）",
        source_extensions=frozenset({"md", "markdown"}),
    ),
    TargetSpec(
        "html-docx",
        "HTML → DOCX",
        "文件",
        "document",
        "docx",
        frozenset({Markup}),
        needs_office=True,
        description="網頁排版成 Word 文件（需要 LibreOffice）",
    ),
    TargetSpec(
        "md-pdf",
        "Markdown → PDF",
        "文件",
        "document",
        "pdf",
        frozenset({Text}),
        needs_office=True,
        description="先轉 HTML 再排版成 PDF（需要 LibreOffice）",
        source_extensions=frozenset({"md", "markdown"}),
    ),
    TargetSpec(
        "html-pdf",
        "HTML → PDF",
        "文件",
        "document",
        "pdf",
        frozenset({Markup}),
        needs_office=True,
        description="網頁排版成 PDF（需要 LibreOffice）",
    ),
    TargetSpec(
        "txt-pdf",
        "TXT → PDF",
        "文件",
        "document",
        "pdf",
        frozenset({Text}),
        needs_office=True,
        description="純文字排版成 PDF（需要 LibreOffice）",
        source_extensions=frozenset({"txt"}),
    ),
    _doc(
        "docx-pdf", "DOCX → PDF", "pdf", "docx", office=True, description="保留原始排版（需要 LibreOffice）"
    ),
    _doc("doc-pdf", "DOC → PDF", "pdf", "doc", office=True, description="舊版 Word 檔（需要 LibreOffice）"),
    _doc(
        "doc-docx",
        "DOC → DOCX",
        "docx",
        "doc",
        office=True,
        description="升級成新版 Word 格式（需要 LibreOffice）",
    ),
    _doc(
        "docx-odt",
        "DOCX → ODT",
        "odt",
        "docx",
        office=True,
        description="轉成 LibreOffice Writer 格式（需要 LibreOffice）",
    ),
    _doc(
        "odt-docx", "ODT → DOCX", "docx", "odt", office=True, description="轉成 Word 格式（需要 LibreOffice）"
    ),
    _doc(
        "odt-pdf",
        "ODT → PDF",
        "pdf",
        "odt",
        office=True,
        description="LibreOffice Writer 文件（需要 LibreOffice）",
    ),
    _doc("rtf-pdf", "RTF → PDF", "pdf", "rtf", office=True, description="富文字文件（需要 LibreOffice）"),
    _doc("pptx-pdf", "PPTX → PDF", "pdf", "pptx", office=True, description="簡報轉 PDF（需要 LibreOffice）"),
    _doc(
        "odp-pdf", "ODP → PDF", "pdf", "odp", office=True, description="LibreOffice 簡報（需要 LibreOffice）"
    ),
    _sheet("xlsx-pdf", "XLSX → PDF", "pdf", {"xlsx", "xlsm"}, description="試算表轉 PDF（需要 LibreOffice）"),
    _sheet("xls-pdf", "XLS → PDF", "pdf", {"xls"}, description="舊版 Excel（需要 LibreOffice）"),
    _sheet("xls-xlsx", "XLS → XLSX", "xlsx", {"xls"}, description="升級成新版 Excel（需要 LibreOffice）"),
    _sheet(
        "xlsx-ods",
        "XLSX → ODS",
        "ods",
        {"xlsx", "xlsm"},
        description="轉成 LibreOffice 試算表（需要 LibreOffice）",
    ),
    _sheet("ods-xlsx", "ODS → XLSX", "xlsx", {"ods"}, description="轉成 Excel 活頁簿（需要 LibreOffice）"),
    _sheet("ods-pdf", "ODS → PDF", "pdf", {"ods"}, description="LibreOffice 試算表（需要 LibreOffice）"),
    # ---------------------------------------------------------------- 資料
    TargetSpec(
        "data-json",
        "轉成 JSON",
        "資料",
        "data",
        "json",
        DATA_KINDS,
        description="CSV／TSV／XLSX／YAML／TOML → JSON",
    ),
    TargetSpec(
        "data-csv",
        "轉成 CSV",
        "資料",
        "data",
        "csv",
        DATA_KINDS,
        description="JSON／XLSX／TSV／YAML → CSV",
    ),
    TargetSpec(
        "data-xlsx",
        "轉成 XLSX",
        "資料",
        "data",
        "xlsx",
        DATA_KINDS,
        description="CSV／TSV／JSON → Excel 活頁簿",
    ),
    TargetSpec(
        "data-yaml",
        "轉成 YAML",
        "資料",
        "data",
        "yaml",
        DATA_KINDS,
        description="JSON／TOML／XLSX → YAML",
    ),
    TargetSpec(
        "data-toml",
        "轉成 TOML",
        "資料",
        "data",
        "toml",
        DATA_KINDS,
        description="JSON／YAML → TOML",
    ),
    # ---------------------------------------------------------------- 字幕
    TargetSpec(
        "sub-srt",
        "轉成 SRT",
        "字幕",
        "subtitle",
        "srt",
        frozenset({Subtitle}),
        description="最通用的字幕格式",
    ),
    TargetSpec(
        "sub-vtt",
        "轉成 WebVTT",
        "字幕",
        "subtitle",
        "vtt",
        frozenset({Subtitle}),
        description="網頁播放器使用的字幕格式",
    ),
    TargetSpec(
        "sub-ass",
        "轉成 ASS",
        "字幕",
        "subtitle",
        "ass",
        frozenset({Subtitle}),
        description="可指定字型與樣式的進階字幕",
    ),
    # ---------------------------------------------------------------- 字型
    TargetSpec(
        "font-woff",
        "轉成 WOFF",
        "字型",
        "font",
        "woff",
        frozenset({Font}),
        description="網頁字型，相容舊瀏覽器",
    ),
    TargetSpec(
        "font-woff2",
        "轉成 WOFF2",
        "字型",
        "font",
        "woff2",
        frozenset({Font}),
        description="網頁字型，壓縮率最高",
    ),
    TargetSpec(
        "font-ttf",
        "轉成 TTF",
        "字型",
        "font",
        "ttf",
        frozenset({Font}),
        description="WOFF／WOFF2 → TTF",
    ),
    # ---------------------------------------------------------------- 壓縮
    TargetSpec(
        "zip",
        "打包成 ZIP",
        "壓縮",
        "archive",
        "zip",
        frozenset(ALL_KINDS),
        group_kinds=frozenset(ALL_KINDS),
        group_min=1,
        description="把佇列中的檔案合成一個 ZIP",
    ),
    TargetSpec(
        "tar-gz",
        "打包成 tar.gz",
        "壓縮",
        "archive",
        "tar.gz",
        frozenset(ALL_KINDS),
        group_kinds=frozenset(ALL_KINDS),
        group_min=1,
        description="Unix 常見的壓縮封存格式",
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
    """回傳目前佇列可用的目標，依類別與宣告順序排序。"""
    kinds = collected_kinds(paths)
    if not kinds:
        return []
    result: list[TargetSpec] = []
    for spec in TARGETS:
        if not (spec.kinds & kinds):
            continue
        if not any(spec.accepts(path) for path in paths):
            continue
        # 只有「整組才有意義」的目標（例如合併 PDF）才需要檢查組員數量；
        # 混合型目標（例如 EPUB 也接受文字）就算來源不是圖片也應該出現。
        if spec.group_kinds and spec.kinds <= spec.group_kinds:
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
    source_exts = {_normalized_ext(Path(p).suffix) for p in paths}
    for spec in options:
        if spec.extension not in source_exts:
            return spec
    return options[0]


def _normalized_ext(suffix: str) -> str:
    ext = suffix.lower().lstrip(".")
    return _EXT_ALIASES.get(ext, ext)


def plan_groups(spec: TargetSpec, paths: list[str] | list[Path]) -> list[list[Path]]:
    """依目標規格，把檔案分成「一次轉換一組」的分組。

    群組型目標（合併 PDF、圖片轉 PDF、圖片轉電子書、打包）會把所有符合的
    檔案收在同一組；其餘檔案各自獨立成一個工作。
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
