"""輸出路徑規劃：唯一檔名、避免覆蓋來源、多輸出路徑。"""

from __future__ import annotations

import re
from pathlib import Path

from .errors import OutputConflictError

# Windows 保留字元（跨平台寬鬆處理，避免產出其他系統無法開啟的檔名）
_ILLEGAL_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_RESERVED_NAMES = {
    "con",
    "prn",
    "aux",
    "nul",
    *(f"com{i}" for i in range(1, 10)),
    *(f"lpt{i}" for i in range(1, 10)),
}


def sanitize_stem(stem: str) -> str:
    """把檔案主檔名清理成安全的字串。"""
    cleaned = _ILLEGAL_CHARS.sub("_", stem).strip(" .")
    if not cleaned:
        cleaned = "output"
    if cleaned.lower() in _RESERVED_NAMES:
        cleaned = f"_{cleaned}"
    return cleaned


def unique_path(candidate: Path) -> Path:
    """若路徑已存在，回傳 ``名稱 (1).ext``、``名稱 (2).ext``……"""
    if not candidate.exists():
        return candidate
    stem, suffix = candidate.stem, candidate.suffix
    index = 1
    while True:
        alt = candidate.with_name(f"{stem} ({index}){suffix}")
        if not alt.exists():
            return alt
        index += 1


def unique_dir(candidate: Path) -> Path:
    """若目錄已存在，回傳 ``名稱 (1)``、``名稱 (2)``……"""
    if not candidate.exists():
        return candidate
    index = 1
    while True:
        alt = candidate.with_name(f"{candidate.name} ({index})")
        if not alt.exists():
            return alt
        index += 1


def _same_file(a: Path, b: Path) -> bool:
    try:
        return a.resolve() == b.resolve()
    except OSError:  # pragma: no cover - 路徑無法解析時退化為字串比較
        return str(a).lower() == str(b).lower()


def resolve_output(
    source: Path,
    output_dir: Path | None,
    extension: str,
    *,
    overwrite: bool = False,
) -> Path:
    """決定單一輸出檔的路徑。

    保證三件事：

    1. 不會等於來源檔案。
    2. 預設情況下不會覆蓋既有檔案。
    3. 輸出目錄會被建立。
    """
    ext = extension.lower().lstrip(".")
    base_dir = Path(output_dir) if output_dir else source.parent
    base_dir.mkdir(parents=True, exist_ok=True)

    candidate = base_dir / f"{sanitize_stem(source.stem)}.{ext}"

    if _same_file(candidate, source):
        candidate = base_dir / f"{sanitize_stem(source.stem)}_converted.{ext}"

    if overwrite:
        if _same_file(candidate, source):  # pragma: no cover - 前面已處理
            raise OutputConflictError("輸出位置與來源檔案相同，已阻止覆蓋原始檔。")
        return candidate

    return unique_path(candidate)


def resolve_output_dir(source: Path, output_dir: Path | None, name: str) -> Path:
    """為多輸出轉換（例如 PDF → 圖片）建立新的空目錄。"""
    base_dir = Path(output_dir) if output_dir else source.parent
    base_dir.mkdir(parents=True, exist_ok=True)
    candidate = base_dir / f"{sanitize_stem(name)}"
    if _same_file(candidate, source.parent):
        candidate = base_dir / f"{sanitize_stem(name)}_out"
    return unique_dir(candidate)


def human_size(num_bytes: int) -> str:
    """把位元組數轉成人看得懂的單位。"""
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"  # pragma: no cover - 不可達
