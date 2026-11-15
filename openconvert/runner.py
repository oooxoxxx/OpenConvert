"""轉換佇列（Qt 執行緒池）。

GUI 只跟這個模組互動：丟入 ``Job``、接收訊號。
真正的轉換邏輯在 :mod:`openconvert.converters`，與 Qt 無關。
"""

from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal

from .converters import get_converter
from .converters.base import ConvertContext
from .core.errors import ConversionCancelled, OpenConvertError
from .core.ffmpeg import FFmpegTools
from .core.history import HistoryEntry, append_entry, trim
from .core.job import Job, JobStatus
from .core.kinds import kinds_for
from .core.settings import Settings

#: 進度訊號的最小間隔（秒），避免 UI 被大量訊號淹沒
PROGRESS_INTERVAL = 0.08


class _TaskSignals(QObject):
    started = Signal(str)
    progress = Signal(str, float, str)
    finished = Signal(str)


class _ConversionTask(QRunnable):
    def __init__(self, job: Job, settings: Settings, tools: FFmpegTools, signals: _TaskSignals) -> None:
        super().__init__()
        self.setAutoDelete(True)
        self.job = job
        self.settings = settings
        self.tools = tools
        self.signals = signals

    # ------------------------------------------------------------------ 執行

    def run(self) -> None:
        job = self.job
        contexts: list[ConvertContext] = []

        def on_progress(fraction: float, message: str) -> None:
            job.report(fraction, message)
            now = time.monotonic()
            if now - last_emit[0] >= PROGRESS_INTERVAL or fraction >= 1.0:
                last_emit[0] = now
                self.signals.progress.emit(job.id, job.progress, message)

        last_emit = [0.0]
        ctx = ConvertContext(
            job=job,
            output_dir=Path(self.settings.output_dir) if self.settings.output_dir else None,
            overwrite=bool(self.settings.overwrite),
            tools=self.tools,
            progress=on_progress,
        )
        contexts.append(ctx)

        succeeded = False
        try:
            job.start()
            self.signals.started.emit(job.id)

            if not self._is_supported():
                job.skip(f"此檔案類型無法轉換成 {job.target.label}")
                return

            converter = get_converter(job.target.converter)
            outputs = converter.convert(ctx)
            job.finish(outputs)
            succeeded = True
        except ConversionCancelled:
            job.status = JobStatus.CANCELLED
            job.message = "已取消"
            job.finished_at = time.time()
        except OpenConvertError as exc:
            job.fail(exc.user_message, exc.detail or None)
        except Exception as exc:  # 不預期的錯誤也要有人話訊息
            job.fail(f"轉換時發生未預期的錯誤：{exc}", repr(exc))
        finally:
            if not succeeded:
                for context in contexts:
                    context.cleanup()
            self._write_history(job)
            self.signals.finished.emit(job.id)

    def _is_supported(self) -> bool:
        allowed = self.job.target.kinds
        if not allowed:
            return True
        return all(set(kinds_for(source)) & allowed for source in self.job.sources)

    def _write_history(self, job: Job) -> None:
        if not self.settings.keep_history:
            return
        try:
            append_entry(
                HistoryEntry(
                    timestamp=job.finished_at or time.time(),
                    sources=[str(p) for p in job.sources],
                    target_label=job.target.label,
                    status=job.status.value,
                    outputs=[str(p) for p in job.outputs],
                    error=job.error,
                    duration_seconds=round(job.duration_seconds, 3),
                )
            )
            trim()
        except OSError:
            pass  # 寫紀錄失敗不應該讓轉換失敗


class ConversionQueue(QObject):
    """管理一批 ``Job`` 的執行、取消與進度回報。"""

    job_started = Signal(object)  # Job
    job_progress = Signal(object)  # Job
    job_finished = Signal(object)  # Job
    all_finished = Signal()

    def __init__(self, settings: Settings, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._settings = settings
        self._pool = QThreadPool(self)
        self._signals: dict[str, _TaskSignals] = {}
        self._jobs: dict[str, Job] = {}
        self._total = 0
        self._done = 0
        self._running = False
        self.apply_settings(settings)

    # ------------------------------------------------------------------ 設定

    def apply_settings(self, settings: Settings) -> None:
        self._settings = settings
        self._pool.setMaxThreadCount(max(1, min(8, int(settings.concurrency or 2))))

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def active_count(self) -> int:
        return self._pool.activeThreadCount()

    # ------------------------------------------------------------------ 控制

    def start_jobs(self, jobs: list[Job], tools: FFmpegTools) -> bool:
        """開始執行一批工作；已有工作進行中時回傳 ``False``。"""
        if self._running:
            return False
        if not jobs:
            return False

        self._jobs = {job.id: job for job in jobs}
        self._total = len(jobs)
        self._done = 0
        self._running = True

        for job in jobs:
            signals = _TaskSignals(self)
            signals.started.connect(self._on_started)
            signals.progress.connect(self._on_progress)
            signals.finished.connect(self._on_finished)
            self._signals[job.id] = signals
            self._pool.start(_ConversionTask(job, self._settings, tools, signals))

        return True

    def cancel(self, job_id: str) -> None:
        job = self._jobs.get(job_id)
        if job is not None and not job.is_terminal:
            job.cancel()

    def cancel_all(self) -> None:
        for job in self._jobs.values():
            if not job.is_terminal:
                job.cancel()

    def wait_for_done(self, timeout_ms: int = 30000) -> bool:
        """主要供測試使用：等待所有工作結束。"""
        return self._pool.waitForDone(timeout_ms)

    # ------------------------------------------------------------------ 訊號

    def _on_started(self, job_id: str) -> None:
        job = self._jobs.get(job_id)
        if job is not None:
            self.job_started.emit(job)

    def _on_progress(self, job_id: str, fraction: float, message: str) -> None:
        job = self._jobs.get(job_id)
        if job is not None:
            job.progress = fraction
            job.message = message
            self.job_progress.emit(job)

    def _on_finished(self, job_id: str) -> None:
        job = self._jobs.get(job_id)
        self._signals.pop(job_id, None)
        self._done += 1
        if job is not None:
            self.job_finished.emit(job)
        if self._done >= self._total:
            self._running = False
            self.all_finished.emit()
