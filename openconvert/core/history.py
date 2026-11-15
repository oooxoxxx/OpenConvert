"""轉換紀錄（JSON Lines）。

紀錄只保存在本機，不會上傳。每一行是一筆獨立的 JSON 物件，
因此即使程式中途結束，已寫入的紀錄仍然完整可讀。
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .settings import data_dir

#: 保留的最大紀錄筆數，避免檔案無限成長
MAX_ENTRIES = 1000


def history_path() -> Path:
    return data_dir() / "history.jsonl"


@dataclass
class HistoryEntry:
    timestamp: float
    sources: list[str]
    target_label: str
    status: str
    outputs: list[str] = field(default_factory=list)
    error: str | None = None
    duration_seconds: float = 0.0

    @property
    def when(self) -> str:
        return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(self.timestamp))


def append_entry(entry: HistoryEntry, path: Path | None = None) -> None:
    target = path or history_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(asdict(entry), ensure_ascii=False)
    with target.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def load_entries(limit: int = 200, path: Path | None = None) -> list[HistoryEntry]:
    target = path or history_path()
    if not target.exists():
        return []
    entries: list[HistoryEntry] = []
    try:
        with target.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    raw = json.loads(line)
                except ValueError:
                    continue  # 跳過損壞的行，不讓整份紀錄失效
                if not isinstance(raw, dict):
                    continue
                try:
                    entries.append(
                        HistoryEntry(
                            timestamp=float(raw.get("timestamp", 0)),
                            sources=list(raw.get("sources") or []),
                            target_label=str(raw.get("target_label", "")),
                            status=str(raw.get("status", "unknown")),
                            outputs=list(raw.get("outputs") or []),
                            error=raw.get("error"),
                            duration_seconds=float(raw.get("duration_seconds") or 0),
                        )
                    )
                except (TypeError, ValueError):
                    continue
    except OSError:
        return []
    return entries[-limit:][::-1]


def trim(path: Path | None = None, keep: int = MAX_ENTRIES) -> None:
    """把紀錄檔裁剪到最多 ``keep`` 筆。"""
    target = path or history_path()
    if not target.exists():
        return
    try:
        lines = [ln for ln in target.read_text(encoding="utf-8").splitlines() if ln.strip()]
    except OSError:
        return
    if len(lines) <= keep:
        return
    target.write_text("\n".join(lines[-keep:]) + "\n", encoding="utf-8")


def clear(path: Path | None = None) -> None:
    target = path or history_path()
    target.unlink(missing_ok=True)
