"""測試用的轉換輔助函式。"""

from __future__ import annotations

from pathlib import Path

from openconvert.converters import get_converter
from openconvert.converters.base import ConvertContext
from openconvert.core.ffmpeg import FFmpegTools
from openconvert.core.job import Job
from openconvert.core.targets import target_by_token


def run_conversion(
    sources: list[Path],
    token: str,
    tools: FFmpegTools,
    output_dir: Path | None = None,
    overwrite: bool = False,
    progress=None,
    **options,
) -> tuple[Job, list[Path]]:
    """直接呼叫轉換器，不經過 Qt。"""
    spec = target_by_token(token)
    assert spec is not None, f"未知的目標格式：{token}"

    job = Job.create([Path(s) for s in sources], spec, options)
    job.start()
    ctx = ConvertContext(
        job=job,
        output_dir=Path(output_dir) if output_dir else None,
        overwrite=overwrite,
        tools=tools,
        progress=progress or (lambda *_args: None),
    )
    converter = get_converter(spec.converter)
    try:
        outputs = converter.convert(ctx)
    except BaseException:
        ctx.cleanup()
        raise
    job.finish(outputs)

    # 不變式：每個輸出的副檔名必須符合目標格式（多輸出時輸出的是資料夾）
    for output in outputs:
        assert output.exists(), f"輸出不存在：{output}"
        if output.is_file():
            assert output.suffix.lower() == f".{spec.extension}", (
                f"{spec.token} 產生了非預期的副檔名：{output.name}"
            )
    return job, outputs
