"""轉換工作（Job）的資料模型與狀態機。

刻意不依賴 Qt，方便在 CLI 與測試中重用。
"""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from .targets import TargetSpec


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"
    SKIPPED = "skipped"

    @property
    def is_terminal(self) -> bool:
        return self in (
            JobStatus.DONE,
            JobStatus.FAILED,
            JobStatus.CANCELLED,
            JobStatus.SKIPPED,
        )

    @property
    def label(self) -> str:
        return _STATUS_LABELS[self]


_STATUS_LABELS: dict[JobStatus, str] = {
    JobStatus.PENDING: "等待中",
    JobStatus.RUNNING: "轉換中",
    JobStatus.DONE: "完成",
    JobStatus.FAILED: "失敗",
    JobStatus.CANCELLED: "已取消",
    JobStatus.SKIPPED: "略過",
}


def new_job_id() -> str:
    return uuid.uuid4().hex[:12]


@dataclass
class Job:
    """一次轉換。``sources`` 只有一個元素是常態；合併類操作會有多個。"""

    id: str
    sources: list[Path]
    target: TargetSpec
    options: dict[str, Any] = field(default_factory=dict)
    status: JobStatus = JobStatus.PENDING
    progress: float = 0.0
    message: str = ""
    outputs: list[Path] = field(default_factory=list)
    error: str | None = None
    error_detail: str | None = None
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    finished_at: float | None = None
    cancel_event: threading.Event = field(default_factory=threading.Event, repr=False)

    # ------------------------------------------------------------ 工廠

    @classmethod
    def create(cls, sources: list[Path], target: TargetSpec, options: dict[str, Any] | None = None) -> Job:
        return cls(
            id=new_job_id(), sources=[Path(s) for s in sources], target=target, options=dict(options or {})
        )

    # ------------------------------------------------------------ 屬性

    @property
    def source(self) -> Path:
        return self.sources[0]

    @property
    def is_group(self) -> bool:
        return len(self.sources) > 1

    @property
    def display_name(self) -> str:
        if len(self.sources) == 1:
            return self.sources[0].name
        return f"{self.sources[0].name} 等 {len(self.sources)} 個檔案"

    @property
    def duration_seconds(self) -> float:
        if self.started_at is None:
            return 0.0
        end = self.finished_at if self.finished_at is not None else time.time()
        return max(0.0, end - self.started_at)

    @property
    def is_terminal(self) -> bool:
        return self.status.is_terminal

    # ------------------------------------------------------------ 狀態轉移

    def start(self) -> None:
        if self.status.is_terminal:
            raise RuntimeError(f"工作 {self.id} 已結束，無法重新啟動")
        self.status = JobStatus.RUNNING
        self.started_at = time.time()
        self.progress = 0.0
        self.message = ""

    def report(self, fraction: float, message: str = "") -> None:
        self.progress = max(0.0, min(1.0, float(fraction)))
        if message:
            self.message = message

    def finish(self, outputs: list[Path]) -> None:
        self.outputs = [Path(p) for p in outputs]
        self.progress = 1.0
        self.status = JobStatus.DONE
        self.message = "完成"
        self.finished_at = time.time()

    def fail(self, message: str, detail: str | None = None) -> None:
        self.status = JobStatus.FAILED
        self.error = message
        self.error_detail = detail
        self.message = message
        self.finished_at = time.time()

    def skip(self, reason: str) -> None:
        self.status = JobStatus.SKIPPED
        self.message = reason
        self.finished_at = time.time()

    def cancel(self) -> None:
        """請求取消；實際中止由執行中的轉換器負責。"""
        self.cancel_event.set()
        if self.status is JobStatus.PENDING:
            self.status = JobStatus.CANCELLED
            self.message = "已取消"
            self.finished_at = time.time()

    @property
    def is_cancelled(self) -> bool:
        return self.cancel_event.is_set()

    # ------------------------------------------------------------ 序列化

    def snapshot(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "sources": [str(p) for p in self.sources],
            "target": self.target.token,
            "target_label": self.target.label,
            "status": self.status.value,
            "progress": round(self.progress, 4),
            "outputs": [str(p) for p in self.outputs],
            "error": self.error,
            "duration_seconds": round(self.duration_seconds, 3),
        }
