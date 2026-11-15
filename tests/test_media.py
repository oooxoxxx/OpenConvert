"""影片與音訊轉換測試（需要系統 FFmpeg）。"""

from __future__ import annotations

from pathlib import Path

import pytest

from openconvert.core.ffmpeg import probe
from openconvert.core.paths import human_size

from .conftest import make_noise_wav, require_ffmpeg
from .helpers import run_conversion


def test_ffmpeg_is_available_for_media_tests(tools):
    if not tools.available:
        pytest.skip("系統沒有 FFmpeg")


def test_video_to_mp3_extracts_audio(tools, sample_mp4: Path):
    _job, outputs = run_conversion([sample_mp4], "mp3", tools, output_dir=sample_mp4.parent / "out")

    assert len(outputs) == 1
    assert outputs[0].suffix == ".mp3"
    info = probe(outputs[0], tools)
    assert info.audio_stream is not None
    assert info.audio_stream.codec_name in ("mp3",)
    assert info.video_stream is None


def test_video_to_webm(tools, sample_mp4: Path, tmp_path: Path):
    _job, outputs = run_conversion([sample_mp4], "webm", tools, output_dir=tmp_path)

    assert outputs[0].suffix == ".webm"
    info = probe(outputs[0], tools)
    assert info.video_stream is not None
    assert info.video_stream.codec_name in ("vp9",)


def test_video_to_gif(tools, sample_mp4: Path, tmp_path: Path):
    _job, outputs = run_conversion(
        [sample_mp4], "video-gif", tools, output_dir=tmp_path, max_dimension=120, gif_fps=8
    )

    assert outputs[0].suffix == ".gif"
    assert outputs[0].stat().st_size > 0
    assert not (tmp_path / "clip.video-gif").exists()


def test_wav_to_flac(tools, tmp_path: Path):
    require_ffmpeg(tools)
    source = make_noise_wav(tmp_path / "tone.wav")
    _job, outputs = run_conversion([source], "flac", tools, output_dir=tmp_path / "out")

    assert outputs[0].suffix == ".flac"
    info = probe(outputs[0], tools)
    assert info.audio_stream is not None
    assert info.audio_stream.codec_name == "flac"


def test_video_resize_limits_dimensions(tools, sample_mp4: Path, tmp_path: Path):
    _job, outputs = run_conversion([sample_mp4], "mp4", tools, output_dir=tmp_path, max_dimension=80)

    info = probe(outputs[0], tools)
    assert info.video_stream is not None
    assert max(info.video_stream.width, info.video_stream.height) <= 80


def test_probe_reports_duration(tools, sample_mp4: Path):
    info = probe(sample_mp4, tools)
    assert 0.5 <= info.duration <= 2.0
    assert info.size_bytes > 0
    assert info.video_stream is not None
    assert info.audio_stream is not None
    assert human_size(info.size_bytes)


def test_video_to_m4v(tools, sample_mp4: Path, tmp_path: Path):
    _job, outputs = run_conversion([sample_mp4], "m4v", tools, output_dir=tmp_path)

    assert outputs[0].suffix == ".m4v"
    info = probe(outputs[0], tools)
    assert info.video_stream is not None
    assert info.video_stream.codec_name == "h264"


def test_video_to_wmv(tools, sample_mp4: Path, tmp_path: Path):
    _job, outputs = run_conversion([sample_mp4], "wmv", tools, output_dir=tmp_path)

    assert outputs[0].suffix == ".wmv"
    info = probe(outputs[0], tools)
    assert info.video_stream is not None
    assert info.video_stream.codec_name in ("wmv2", "wmv3")


def test_wav_to_aiff(tools, tmp_path: Path):
    require_ffmpeg(tools)
    source = make_noise_wav(tmp_path / "tone.wav")
    _job, outputs = run_conversion([source], "aiff", tools, output_dir=tmp_path / "out")

    assert outputs[0].suffix == ".aiff"
    info = probe(outputs[0], tools)
    assert info.audio_stream is not None


def test_extract_frames(tools, sample_mp4: Path, tmp_path: Path):
    _job, outputs = run_conversion(
        [sample_mp4], "video-frames", tools, output_dir=tmp_path / "out", frame_fps=5
    )

    assert len(outputs) >= 3
    assert all(path.suffix == ".png" for path in outputs)
    assert outputs[0].parent.name == "clip_frames"

    from PIL import Image

    with Image.open(outputs[0]) as image:
        assert image.width > 0


def test_images_to_video(tools, png_series: list[Path], tmp_path: Path):
    _job, outputs = run_conversion(
        png_series, "images-video", tools, output_dir=tmp_path / "out", frame_seconds=1
    )

    assert outputs[0].suffix == ".mp4"
    info = probe(outputs[0], tools)
    assert info.video_stream is not None
    assert 2.4 <= info.duration <= 3.6


def test_missing_ffmpeg_gives_readable_error(png_file: Path):
    from openconvert.core.errors import FFmpegNotFoundError
    from openconvert.core.ffmpeg import FFmpegTools

    with pytest.raises(FFmpegNotFoundError):
        run_conversion([png_file], "mp3", FFmpegTools())
