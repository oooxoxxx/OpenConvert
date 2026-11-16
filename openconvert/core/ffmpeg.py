"""FFmpeg / FFprobe 的尋找、探測與執行。"""

from __future__ import annotations

import contextlib
import json
import os
import shutil
import subprocess
import sys
import threading
from collections import deque
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from .errors import ConversionCancelled, ConversionError, FFmpegNotFoundError
from .resources import tools_dir

CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


def _creation_flags() -> int:
    return CREATE_NO_WINDOW


def _exe(name: str) -> str:
    return f"{name}.exe" if sys.platform == "win32" else name


@dataclass(frozen=True)
class FFmpegTools:
    ffmpeg: Path | None = None
    ffprobe: Path | None = None
    bundled: bool = False

    @property
    def available(self) -> bool:
        return self.ffmpeg is not None

    @property
    def probing_available(self) -> bool:
        return self.ffprobe is not None


def is_bundled(path: Path | None) -> bool:
    """判斷某個執行檔是否來自安裝包內附的 tools/。"""
    if path is None:
        return False
    try:
        bundled_root = tools_dir().resolve()
        return bundled_root in path.resolve().parents
    except OSError:  # pragma: no cover - 路徑無法解析時保守回傳 False
        return False


def _candidates(name: str) -> Iterable[Path]:
    exe = _exe(name)
    local = tools_dir()
    yield local / exe
    yield local / "bin" / exe
    for folder in ("ffmpeg", "ffmpeg/bin"):
        yield local / folder / exe


def _search_path(name: str) -> Path | None:
    found = shutil.which(name)
    if found:
        return Path(found)
    if sys.platform == "win32":  # pragma: no cover - 平台相依
        exe = _exe(name)
        for root in (
            Path(os.environ.get("PROGRAMFILES", r"C:\Program Files")) / "ffmpeg" / "bin",
            Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Links",
            Path(r"C:\ProgramData\chocolatey\bin"),
            Path(r"C:\ffmpeg\bin"),
        ):
            candidate = root / exe
            if candidate.exists():
                return candidate
        # winget 安裝後，PATH 不一定會立刻更新到既有程序；
        # 直接到 WinGet 的套件目錄找一次。
        packages = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Packages"
        if packages.is_dir():
            try:
                for entry in packages.iterdir():
                    if "ffmpeg" not in entry.name.lower():
                        continue
                    for candidate in entry.glob(f"**/bin/{exe}"):
                        if candidate.is_file():
                            return candidate
            except OSError:
                pass
    return None


def locate(name: str, override: str | None = None) -> Path | None:
    """依序尋找：使用者指定 → 隨附工具 → 系統 PATH → 常見安裝位置。"""
    if override:
        candidate = Path(override).expanduser()
        if candidate.is_dir():
            candidate = candidate / _exe(name)
        if candidate.is_file():
            return candidate
        return None
    for candidate in _candidates(name):
        if candidate.is_file():
            return candidate
    return _search_path(name)


def discover(ffmpeg_override: str | None = None, ffprobe_override: str | None = None) -> FFmpegTools:
    ffmpeg = locate("ffmpeg", ffmpeg_override)
    return FFmpegTools(
        ffmpeg=ffmpeg,
        ffprobe=locate("ffprobe", ffprobe_override),
        bundled=is_bundled(ffmpeg),
    )


def version_of(binary: Path | None) -> str | None:
    if binary is None:
        return None
    try:
        out = subprocess.run(
            [str(binary), "-version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=20,
            creationflags=_creation_flags(),
        )
    except (OSError, subprocess.SubprocessError):
        return None
    first = (out.stdout or "").splitlines()
    return first[0].strip() if first else None


# --------------------------------------------------------------------------- 探測


@dataclass(frozen=True)
class StreamInfo:
    index: int
    codec_type: str
    codec_name: str
    codec_long_name: str = ""
    width: int = 0
    height: int = 0
    fps: float = 0.0
    sample_rate: int = 0
    channels: int = 0
    bit_rate: int = 0
    pixel_format: str = ""
    language: str = ""
    duration: float = 0.0

    @property
    def resolution(self) -> str:
        return f"{self.width}×{self.height}" if self.width and self.height else ""

    @property
    def summary(self) -> str:
        parts = [self.codec_name or "?"]
        if self.codec_type == "video":
            if self.resolution:
                parts.append(self.resolution)
            if self.fps:
                parts.append(f"{self.fps:.3g} fps")
            if self.pixel_format:
                parts.append(self.pixel_format)
        elif self.codec_type == "audio":
            if self.sample_rate:
                parts.append(f"{self.sample_rate} Hz")
            if self.channels:
                parts.append(f"{self.channels} 聲道")
        return " · ".join(parts)


@dataclass(frozen=True)
class MediaInfo:
    path: Path
    format_name: str = ""
    format_long_name: str = ""
    duration: float = 0.0
    size_bytes: int = 0
    bit_rate: int = 0
    streams: tuple[StreamInfo, ...] = ()
    raw: dict = field(default_factory=dict)

    @property
    def video_stream(self) -> StreamInfo | None:
        return next((s for s in self.streams if s.codec_type == "video"), None)

    @property
    def audio_stream(self) -> StreamInfo | None:
        return next((s for s in self.streams if s.codec_type == "audio"), None)


def _to_float(value: object) -> float:
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return 0.0


def _to_int(value: object) -> int:
    try:
        return int(float(str(value)))
    except (TypeError, ValueError):
        return 0


def _parse_fps(raw: str | None) -> float:
    if not raw or raw in ("0/0", "N/A"):
        return 0.0
    if "/" in raw:
        num, _, den = raw.partition("/")
        try:
            denominator = float(den)
            return float(num) / denominator if denominator else 0.0
        except ValueError:
            return 0.0
    return _to_float(raw)


def probe(path: str | Path, tools: FFmpegTools) -> MediaInfo:
    """以 ffprobe 取得媒體資訊；失敗時拋出 :class:`ConversionError`。"""
    if tools.ffprobe is None:
        raise FFmpegNotFoundError("找不到 FFprobe，無法讀取媒體資訊。")

    source = Path(path)
    command = [
        str(tools.ffprobe),
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        str(source),
    ]
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
            creationflags=_creation_flags(),
        )
    except subprocess.TimeoutExpired as exc:  # pragma: no cover - 極端情況
        raise ConversionError("讀取媒體資訊逾時。", detail=str(exc)) from exc
    except OSError as exc:
        raise ConversionError(f"無法執行 FFprobe：{exc}", detail=str(exc)) from exc

    if result.returncode != 0:
        raise ConversionError(
            "無法讀取此檔案的媒體資訊，可能已損壞或不是媒體檔。",
            detail=(result.stderr or "").strip()[-2000:],
        )

    try:
        data = json.loads(result.stdout or "{}")
    except ValueError as exc:
        raise ConversionError("FFprobe 回傳的資訊無法解析。", detail=str(exc)) from exc

    fmt = data.get("format") or {}
    streams: list[StreamInfo] = []
    for item in data.get("streams") or []:
        if not isinstance(item, dict):
            continue
        streams.append(
            StreamInfo(
                index=_to_int(item.get("index")),
                codec_type=str(item.get("codec_type") or ""),
                codec_name=str(item.get("codec_name") or ""),
                codec_long_name=str(item.get("codec_long_name") or ""),
                width=_to_int(item.get("width")),
                height=_to_int(item.get("height")),
                fps=_parse_fps(item.get("avg_frame_rate") or item.get("r_frame_rate")),
                sample_rate=_to_int(item.get("sample_rate")),
                channels=_to_int(item.get("channels")),
                bit_rate=_to_int(item.get("bit_rate")),
                pixel_format=str(item.get("pix_fmt") or ""),
                language=str((item.get("tags") or {}).get("language") or ""),
                duration=_to_float(item.get("duration")),
            )
        )

    return MediaInfo(
        path=source,
        format_name=str(fmt.get("format_name") or ""),
        format_long_name=str(fmt.get("format_long_name") or ""),
        duration=_to_float(fmt.get("duration")),
        size_bytes=_to_int(fmt.get("size")) or (source.stat().st_size if source.exists() else 0),
        bit_rate=_to_int(fmt.get("bit_rate")),
        streams=tuple(streams),
        raw=data,
    )


# --------------------------------------------------------------------------- 執行


def _parse_progress_time(key: str, value: str) -> float | None:
    """``out_time_us`` 與 ``out_time_ms`` 都是微秒（ffmpeg 的歷史包袱）。"""
    if key not in ("out_time_us", "out_time_ms"):
        return None
    try:
        micros = float(value)
    except (TypeError, ValueError):
        return None
    if micros < 0:
        return None
    return micros / 1_000_000.0


def run_ffmpeg(
    tools: FFmpegTools,
    args: Sequence[str],
    *,
    duration: float = 0.0,
    on_progress: Callable[[float, str], None] | None = None,
    cancelled: Callable[[], bool] | None = None,
    timeout: float | None = None,
) -> None:
    """執行 FFmpeg 並回報進度。

    Raises:
        FFmpegNotFoundError: 找不到 ffmpeg。
        ConversionCancelled: 使用者取消。
        ConversionError: FFmpeg 回傳非零狀態。
    """
    if tools.ffmpeg is None:
        raise FFmpegNotFoundError()

    command = [
        str(tools.ffmpeg),
        "-hide_banner",
        "-nostdin",
        "-y",
        "-loglevel",
        "error",
        "-progress",
        "pipe:1",
        *[str(a) for a in args],
    ]

    try:
        proc = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=_creation_flags(),
        )
    except OSError as exc:
        raise ConversionError(f"無法啟動 FFmpeg：{exc}", detail=str(exc)) from exc

    stderr_tail: deque[str] = deque(maxlen=400)

    def drain_stderr() -> None:
        assert proc.stderr is not None
        try:
            for line in proc.stderr:
                stripped = line.rstrip()
                if stripped:
                    stderr_tail.append(stripped)
        except (ValueError, OSError):  # pragma: no cover - 串流關閉競態
            pass

    stderr_thread = threading.Thread(target=drain_stderr, name="ffmpeg-stderr", daemon=True)
    stderr_thread.start()

    stop_watch = threading.Event()

    def watch_cancel() -> None:
        while not stop_watch.wait(0.15):
            if cancelled and cancelled():
                _terminate(proc)
                return

    watcher = threading.Thread(target=watch_cancel, name="ffmpeg-cancel", daemon=True)
    watcher.start()

    speed = ""
    try:
        assert proc.stdout is not None
        for raw_line in proc.stdout:
            line = raw_line.strip()
            if not line or "=" not in line:
                continue
            key, _, value = line.partition("=")
            seconds = _parse_progress_time(key, value)
            if seconds is not None and duration > 0 and on_progress is not None:
                fraction = max(0.0, min(1.0, seconds / duration))
                on_progress(fraction, f"{fraction * 100:.0f}%{(' · ' + speed) if speed else ''}")
            elif key == "speed":
                speed = value.strip()
            elif key == "progress" and value.strip() == "end" and on_progress is not None:
                on_progress(1.0, "100%")
    finally:
        stop_watch.set()
        watcher.join(timeout=1.0)
        try:
            proc.wait(timeout=timeout or 10)
        except subprocess.TimeoutExpired:  # pragma: no cover - 極端情況
            _terminate(proc)
        try:
            if proc.stdout:
                proc.stdout.close()
        except OSError:  # pragma: no cover
            pass
        stderr_thread.join(timeout=2.0)

    if cancelled and cancelled():
        raise ConversionCancelled()

    if proc.returncode != 0:
        detail = "\n".join(stderr_tail)
        raise ConversionError(friendly_ffmpeg_error(detail), detail=detail)


def _terminate(proc: subprocess.Popen[str]) -> None:
    try:
        proc.terminate()
    except OSError:  # pragma: no cover - 程序已結束
        return
    try:
        proc.wait(timeout=3)
    except subprocess.TimeoutExpired:  # pragma: no cover
        with contextlib.suppress(OSError):
            proc.kill()


#: 常見 FFmpeg 錯誤 → 人話
_ERROR_HINTS: tuple[tuple[str, str], ...] = (
    ("No such file or directory", "找不到來源檔案，可能已被移動或刪除。"),
    ("Invalid data found when processing input", "檔案格式不正確或已損壞。"),
    ("Unknown encoder", "此 FFmpeg 版本不支援所需的編碼器，請改用完整版 FFmpeg。"),
    ("Encoder not found", "此 FFmpeg 版本不支援所需的編碼器，請改用完整版 FFmpeg。"),
    ("Permission denied", "沒有寫入權限，請改選其他輸出資料夾。"),
    ("No space left on device", "磁碟空間不足。"),
    ("Invalid argument", "轉換參數不適用於此檔案，請嘗試其他格式。"),
    ("does not contain any stream", "檔案中沒有可轉換的影音串流。"),
    ("Error while opening encoder", "無法初始化編碼器，請確認 FFmpeg 安裝完整。"),
)

_GENERIC_HINT = "轉換失敗。可能原因：檔案損壞、格式不支援，或輸出資料夾不可寫入。"


def friendly_ffmpeg_error(detail: str) -> str:
    """把 FFmpeg 的技術訊息轉成一句可讀的說明。"""
    lowered = detail.lower()
    for needle, message in _ERROR_HINTS:
        if needle.lower() in lowered:
            return message
    return _GENERIC_HINT
