"""文字檔編碼偵測與讀寫。

使用者的來源檔可能來自 Windows（Big5／cp950）、對岸（GB18030）或網路
（UTF-8），因此讀取時依序嘗試常見編碼，而不是假設一定是 UTF-8。
"""

from __future__ import annotations

from pathlib import Path

#: 依序嘗試的編碼。cp950（Big5）放前面是因為本專案主要使用者是繁體中文。
_ENCODINGS = ("utf-8-sig", "utf-16", "cp950", "gb18030", "shift_jis", "cp1252")


def decode_bytes(data: bytes) -> tuple[str, str]:
    """回傳 ``(文字, 使用的編碼)``；無法辨識時以 latin-1 取代。"""
    if not data:
        return "", "utf-8"

    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        try:
            return data.decode("utf-16"), "utf-16"
        except UnicodeDecodeError:
            pass

    for encoding in _ENCODINGS:
        try:
            return data.decode(encoding), encoding
        except (UnicodeDecodeError, LookupError):
            continue

    return data.decode("latin-1", "replace"), "latin-1"


def read_text(path: str | Path) -> str:
    return decode_bytes(Path(path).read_bytes())[0]


def write_text(path: str | Path, text: str, *, bom: bool = False) -> None:
    """以 UTF-8 寫入；``bom=True`` 時加上 BOM（Excel 讀 CSV 時較不易亂碼）。"""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8-sig" if bom else "utf-8", newline="\n")


__all__ = ["decode_bytes", "read_text", "write_text"]
