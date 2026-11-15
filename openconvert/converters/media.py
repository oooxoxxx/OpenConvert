"""影片與音訊轉換（FFmpeg）。

編碼選擇刻意寫死在表裡，而不是讓使用者挑選任意編碼器：
一般使用者不需要知道 libx264 與 libvpx-vp9 的差別，
但需要「選了就能播」的保證。
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from PIL import Image, ImageOps

from ..core.errors import ConversionError, FFmpegNotFoundError
from ..core.ffmpeg import MediaInfo, probe, run_ffmpeg
from ..core.paths import resolve_output, resolve_output_dir
from ..core.sorting import natural_key
from .base import ConvertContext, Converter

#: 容器 → (視訊編碼器, 音訊編碼器)
VIDEO_CODECS: dict[str, tuple[str, str]] = {
    "mp4": ("libx264", "aac"),
    "mov": ("libx264", "aac"),
    "mkv": ("libx264", "aac"),
    "m4v": ("libx264", "aac"),
    "flv": ("libx264", "aac"),
    "ts": ("libx264", "aac"),
    "webm": ("libvpx-vp9", "libopus"),
    "avi": ("mpeg4", "libmp3lame"),
    "wmv": ("wmv2", "wmav2"),
    "ogv": ("libtheora", "libvorbis"),
}

#: 格式 → 音訊編碼器
AUDIO_CODECS: dict[str, str] = {
    "mp3": "libmp3lame",
    "m4a": "aac",
    "m4b": "aac",
    "aac": "aac",
    "wav": "pcm_s16le",
    "flac": "flac",
    "ogg": "libvorbis",
    "opus": "libopus",
    "aiff": "pcm_s16be",
    "wma": "wmav2",
    "ac3": "ac3",
}

#: 沒有位元率概念的編碼器
LOSSLESS_AUDIO = frozenset({"wav", "flac", "aiff"})

#: 品質預設 → (x264 CRF, VP9 CRF, 音訊 kbps)
QUALITY_PRESETS: dict[str, tuple[int, int, int]] = {
    "high": (18, 28, 192),
    "balanced": (23, 33, 160),
    "small": (28, 38, 112),
}

DEFAULT_MAX_FPS = 60
DEFAULT_VIDEO_FPS = 30
DEFAULT_FRAME_SECONDS = 2.0
DEFAULT_FRAME_FPS = 1


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

        if token == "images-video":
            return self._images_to_video(ctx, crf_x264, max_dimension)
        if token == "video-frames":
            return self._video_frames(ctx, max_dimension)

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
        if token == "wma":
            args += ["-ar", "44100"]
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
            if token in ("mp4", "mov", "m4v"):
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
        elif vcodec == "wmv2":
            args += ["-c:v", "wmv2", "-b:v", "2500k", "-pix_fmt", "yuv420p"]
        elif vcodec == "libtheora":
            args += ["-c:v", "libtheora", "-q:v", "7"]
        else:  # pragma: no cover - 表格已窮舉
            args += ["-c:v", vcodec]

        if filters:
            args += ["-vf", ",".join(filters)]

        if info is not None and info.audio_stream is None:
            args += ["-an"]
        elif acodec == "wmav2":
            args += ["-c:a", "wmav2", "-b:a", "128k"]
        elif acodec == "libvorbis":
            args += ["-c:a", "libvorbis", "-q:a", "5"]
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

    # ------------------------------------------------------------ 影片 → 影格

    def _video_frames(self, ctx: ConvertContext, max_dimension: int | None) -> list[Path]:
        source = ctx.source
        fps = int(ctx.option("frame_fps", DEFAULT_FRAME_FPS) or DEFAULT_FRAME_FPS)
        fps = max(1, min(60, fps))

        duration = 0.0
        if ctx.tools.probing_available:
            try:
                duration = probe(source, ctx.tools).duration
            except ConversionError as exc:
                ctx.log(f"無法讀取影片長度，進度條可能不準確：{exc}")

        out_dir = resolve_output_dir(source, ctx.output_dir, f"{source.stem}_frames")
        ctx.track(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        filters = [f"fps={fps}"]
        scale = _scale_filter(max_dimension)
        if scale:
            filters.append(scale)

        args = [
            "-i",
            str(source),
            "-vf",
            ",".join(filters),
            "-start_number",
            "1",
            str(out_dir / "frame_%05d.png"),
        ]
        ctx.report(0.02, "準備中")
        run_ffmpeg(
            ctx.tools, args, duration=duration, on_progress=ctx.progress, cancelled=lambda: ctx.cancelled
        )

        outputs = sorted(out_dir.glob("frame_*.png"))
        if not outputs:
            raise ConversionError("沒有產生任何影格，來源影片可能沒有視訊串流。")
        ctx.report(1.0, "完成")
        return outputs

    # ------------------------------------------------------------ 圖片 → 影片

    def _images_to_video(self, ctx: ConvertContext, crf: int, max_dimension: int | None) -> list[Path]:
        sources = sorted(ctx.sources, key=lambda path: natural_key(path.name))
        if not sources:
            raise ConversionError("沒有可合成影片的圖片。")

        fps = int(ctx.option("video_fps", DEFAULT_VIDEO_FPS) or DEFAULT_VIDEO_FPS)
        fps = max(1, min(60, fps))
        try:
            seconds = float(ctx.option("frame_seconds", DEFAULT_FRAME_SECONDS) or DEFAULT_FRAME_SECONDS)
        except (TypeError, ValueError):
            seconds = DEFAULT_FRAME_SECONDS
        seconds = max(0.1, min(60.0, seconds))

        limit = max_dimension or 1920
        width, height = self._target_size(sources[0], limit)

        first = sources[0]
        name = f"{first.stem}_video" if len(sources) > 1 else first.stem
        dest = resolve_output(first.with_name(name), ctx.output_dir, "mp4", overwrite=ctx.overwrite)
        ctx.track(dest)

        with tempfile.TemporaryDirectory(prefix="openconvert-slides-") as folder:
            workdir = Path(folder)
            frames: list[Path] = []
            for index, source in enumerate(sources):
                ctx.check_cancel()
                ctx.report(index / len(sources) * 0.6, f"處理圖片 {index + 1}/{len(sources)}")
                target = workdir / f"{index + 1:05d}.png"
                self._normalize_frame(source, target, width, height)
                frames.append(target)

            listing = workdir / "frames.txt"
            lines: list[str] = []
            for frame in frames:
                lines.append(f"file '{_concat_path(frame)}'")
                lines.append(f"duration {seconds:.3f}")
            # concat demuxer 需要最後一個檔案再出現一次，才會套用最後一段 duration
            lines.append(f"file '{_concat_path(frames[-1])}'")
            listing.write_text("\n".join(lines) + "\n", encoding="utf-8")

            args = [
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(listing),
                "-r",
                str(fps),
                "-t",
                f"{seconds * len(frames):.3f}",
                "-c:v",
                "libx264",
                "-preset",
                "medium",
                "-crf",
                str(crf),
                "-pix_fmt",
                "yuv420p",
                "-movflags",
                "+faststart",
                str(dest),
            ]
            ctx.report(0.65, "編碼影片")
            run_ffmpeg(
                ctx.tools,
                args,
                duration=seconds * len(frames),
                on_progress=ctx.progress,
                cancelled=lambda: ctx.cancelled,
            )

        self._verify_output(dest)
        return [dest]

    @staticmethod
    def _target_size(sample: Path, limit: int) -> tuple[int, int]:
        try:
            with Image.open(sample) as image:
                width, height = ImageOps.exif_transpose(image).size
        except (OSError, ValueError) as exc:
            raise ConversionError(f"無法讀取圖片「{sample.name}」：{exc}", detail=str(exc)) from exc

        if max(width, height) > limit:
            ratio = limit / max(width, height)
            width, height = round(width * ratio), round(height * ratio)
        width = max(2, width - width % 2)
        height = max(2, height - height % 2)
        return width, height

    @staticmethod
    def _normalize_frame(source: Path, target: Path, width: int, height: int) -> None:
        try:
            with Image.open(source) as image:
                frame = ImageOps.exif_transpose(image).convert("RGB")
                frame = ImageOps.pad(frame, (width, height), color="black", method=Image.Resampling.LANCZOS)
                frame.save(target, "PNG")
                frame.close()
        except (OSError, ValueError) as exc:
            raise ConversionError(f"無法處理圖片「{source.name}」：{exc}", detail=str(exc)) from exc

    # ------------------------------------------------------------ 檢查

    @staticmethod
    def _verify_output(path: Path) -> None:
        if not path.exists():
            raise ConversionError("轉換結束但沒有產生輸出檔案。")
        if path.stat().st_size == 0:
            path.unlink(missing_ok=True)
            raise ConversionError("輸出檔案是空的，轉換失敗。")


def _concat_path(path: Path) -> str:
    return path.as_posix().replace("'", "'\\''")
