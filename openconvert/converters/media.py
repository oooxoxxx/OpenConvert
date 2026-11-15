"""影片與音訊轉換（FFmpeg）。

編碼選擇刻意寫死在表裡，而不是讓使用者挑選任意編碼器：
一般使用者不需要知道 libx264 與 libvpx-vp9 的差別，
但需要「選了就能播」的保證。
"""

from __future__ import annotations

from pathlib import Path

from ..core.errors import ConversionError, FFmpegNotFoundError
from ..core.ffmpeg import MediaInfo, probe, run_ffmpeg
from ..core.paths import resolve_output
from .base import ConvertContext, Converter

#: 容器 → (視訊編碼器, 音訊編碼器)
VIDEO_CODECS: dict[str, tuple[str, str]] = {
    "mp4": ("libx264", "aac"),
    "mov": ("libx264", "aac"),
    "mkv": ("libx264", "aac"),
    "webm": ("libvpx-vp9", "libopus"),
    "avi": ("mpeg4", "libmp3lame"),
}

#: 格式 → 音訊編碼器
AUDIO_CODECS: dict[str, str] = {
    "mp3": "libmp3lame",
    "m4a": "aac",
    "aac": "aac",
    "wav": "pcm_s16le",
    "flac": "flac",
    "ogg": "libvorbis",
    "opus": "libopus",
}

#: 沒有位元率概念的編碼器
LOSSLESS_AUDIO = frozenset({"wav", "flac"})

#: 品質預設 → (x264 CRF, VP9 CRF, 音訊 kbps)
QUALITY_PRESETS: dict[str, tuple[int, int, int]] = {
    "high": (18, 28, 192),
    "balanced": (23, 33, 160),
    "small": (28, 38, 112),
}

DEFAULT_MAX_FPS = 60


def _scale_filter(max_dimension: int | None) -> str | None:
    if not max_dimension or max_dimension <= 0:
        return None
    return (
        f"scale=w='min(iw,{max_dimension})':h='min(ih,{max_dimension})'"
        ":force_original_aspect_ratio=decrease:force_divisible_by=2"
    )


class MediaConverter(Converter):
    name = "media"

    # ------------------------------------------------------------ 對外介面

    def convert(self, ctx: ConvertContext) -> list[Path]:
        if not ctx.tools.available:
            raise FFmpegNotFoundError()

        self.ensure_source_exists(ctx)

        source = ctx.source
        token = ctx.token
        quality = str(ctx.option("quality", "balanced"))
        crf_x264, crf_vp9, audio_kbps = QUALITY_PRESETS.get(quality, QUALITY_PRESETS["balanced"])
        max_dimension = ctx.option("max_dimension")
        try:
            max_dimension = int(max_dimension) if max_dimension else None
        except (TypeError, ValueError):
            max_dimension = None

        duration = 0.0
        info: MediaInfo | None = None
        if ctx.tools.probing_available:
            try:
                info = probe(source, ctx.tools)
                duration = info.duration
            except ConversionError as exc:
                ctx.log(f"無法讀取媒體資訊，進度條可能不準確：{exc}")

        if token in AUDIO_CODECS:
            return self._convert_audio(ctx, source, token, info, audio_kbps)
        return self._convert_video(
            ctx, source, token, info, (crf_x264, crf_vp9), audio_kbps, max_dimension, duration
        )

    # ------------------------------------------------------------ 音訊

    def _convert_audio(
        self,
        ctx: ConvertContext,
        source: Path,
        token: str,
        info: MediaInfo | None,
        audio_kbps: int,
    ) -> list[Path]:
        if info is not None and info.audio_stream is None:
            raise ConversionError(f"「{source.name}」中沒有音訊串流。")

        dest = resolve_output(source, ctx.output_dir, ctx.job.target.extension, overwrite=ctx.overwrite)
        ctx.track(dest)
        codec = AUDIO_CODECS[token]

        args: list[str] = ["-i", str(source), "-vn", "-c:a", codec]
        if token not in LOSSLESS_AUDIO:
            args += ["-b:a", f"{audio_kbps}k"]
        if token == "ogg":
            args += ["-ar", "48000"]
        args.append(str(dest))

        ctx.report(0.02, "準備中")
        run_ffmpeg(
            ctx.tools,
            args,
            duration=info.duration if info else 0.0,
            on_progress=ctx.progress,
            cancelled=lambda: ctx.cancelled,
        )
        self._verify_output(dest)
        return [dest]

    # ------------------------------------------------------------ 影片

    def _convert_video(
        self,
        ctx: ConvertContext,
        source: Path,
        token: str,
        info: MediaInfo | None,
        crfs: tuple[int, int],
        audio_kbps: int,
        max_dimension: int | None,
        duration: float,
    ) -> list[Path]:
        if info is not None and info.video_stream is None:
            raise ConversionError(f"「{source.name}」中沒有視訊串流。")

        dest = resolve_output(source, ctx.output_dir, ctx.job.target.extension, overwrite=ctx.overwrite)
        ctx.track(dest)

        filters: list[str] = []
        if token == "video-gif":
            fps = int(ctx.option("gif_fps", 12) or 12)
            fps = max(5, min(30, fps))
            limit = max_dimension or 480
            chain = f"fps={fps},{_scale_filter(limit) or ''}"
            chain = chain.rstrip(",")
            chain += ",split[a][b];[a]palettegen=stats_mode=diff[p];[b][p]paletteuse=dither=bayer"
            args = [
                "-i",
                str(source),
                "-filter_complex",
                chain,
                "-loop",
                "0",
                str(dest),
            ]
            ctx.report(0.02, "準備中")
            run_ffmpeg(
                ctx.tools, args, duration=duration, on_progress=ctx.progress, cancelled=lambda: ctx.cancelled
            )
            self._verify_output(dest)
            return [dest]

        vcodec, acodec = VIDEO_CODECS[token]

        if info is not None and info.video_stream is not None:
            stream = info.video_stream
            if (
                max_dimension
                and stream.width
                and stream.height
                and max(stream.width, stream.height) <= max_dimension
            ):
                max_dimension = None  # 不需要放大
            if token == "avi" and stream.fps > 60:
                filters.append(f"fps={DEFAULT_MAX_FPS}")

        scale = _scale_filter(max_dimension)
        if scale:
            filters.insert(0, scale)

        args = ["-i", str(source), "-map", "0:v:0", "-map", "0:a:0?"]

        if vcodec == "libx264":
            args += ["-c:v", "libx264", "-preset", "medium", "-crf", str(crfs[0]), "-pix_fmt", "yuv420p"]
            if token in ("mp4", "mov"):
                args += ["-movflags", "+faststart"]
        elif vcodec == "libvpx-vp9":
            args += [
                "-c:v",
                "libvpx-vp9",
                "-crf",
                str(crfs[1]),
                "-b:v",
                "0",
                "-row-mt",
                "1",
                "-deadline",
                "good",
                "-cpu-used",
                "2",
            ]
        elif vcodec == "mpeg4":
            args += ["-c:v", "mpeg4", "-q:v", "4", "-pix_fmt", "yuv420p"]
        else:  # pragma: no cover - 表格已窮舉
            args += ["-c:v", vcodec]

        if filters:
            args += ["-vf", ",".join(filters)]

        if info is not None and info.audio_stream is None:
            args += ["-an"]
        else:
            args += ["-c:a", acodec]
            if acodec != "pcm_s16le":
                args += ["-b:a", f"{audio_kbps}k"]

        args.append(str(dest))

        ctx.report(0.02, "準備中")
        run_ffmpeg(
            ctx.tools, args, duration=duration, on_progress=ctx.progress, cancelled=lambda: ctx.cancelled
        )
        self._verify_output(dest)
        return [dest]

    # ------------------------------------------------------------ 檢查

    @staticmethod
    def _verify_output(path: Path) -> None:
        if not path.exists():
            raise ConversionError("轉換結束但沒有產生輸出檔案。")
        if path.stat().st_size == 0:
            path.unlink(missing_ok=True)
            raise ConversionError("輸出檔案是空的，轉換失敗。")
