"""封裝：把佇列中的檔案打包成 ZIP 或 tar.gz。"""

from __future__ import annotations

import tarfile
import zipfile
from pathlib import Path

from ..core.errors import ConversionError
from ..core.paths import resolve_output
from .base import ConvertContext, Converter


def _arcnames(sources: list[Path]) -> list[str]:
    """同名檔案加上序號，避免壓縮檔內互相覆蓋。"""
    used: dict[str, int] = {}
    result: list[str] = []
    for path in sources:
        name = path.name or "file"
        count = used.get(name, 0)
        used[name] = count + 1
        if count:
            name = f"{path.stem} ({count}){path.suffix}"
        result.append(name)
    return result


class ArchiveConverter(Converter):
    name = "archive"

    def convert(self, ctx: ConvertContext) -> list[Path]:
        self.ensure_source_exists(ctx)

        sources = ctx.sources
        first = sources[0]
        extension = ctx.job.target.extension
        name = f"{first.stem}_archive" if len(sources) > 1 else first.stem
        dest = resolve_output(first.with_name(name), ctx.output_dir, extension, overwrite=ctx.overwrite)
        ctx.track(dest)

        entries = [
            (path, arcname)
            for path, arcname in zip(sources, _arcnames(sources), strict=True)
            if not _same_file(path, dest)
        ]
        if not entries:
            raise ConversionError("沒有可打包的檔案。")

        if extension == "zip":
            self._write_zip(ctx, dest, entries)
        elif extension == "tar.gz":
            self._write_tar(ctx, dest, entries)
        else:  # pragma: no cover - 目標宣告已窮舉
            raise ConversionError(f"不支援的封裝格式：{extension}")

        ctx.report(1.0, "完成")
        if not dest.exists() or dest.stat().st_size == 0:
            dest.unlink(missing_ok=True)
            raise ConversionError("封裝失敗，沒有產生有效檔案。")
        return [dest]

    # ------------------------------------------------------------ 格式

    def _write_zip(self, ctx: ConvertContext, dest: Path, entries: list[tuple[Path, str]]) -> None:
        try:
            with zipfile.ZipFile(dest, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
                for index, (path, arcname) in enumerate(entries):
                    ctx.check_cancel()
                    ctx.report(index / len(entries) * 0.95, f"打包 {index + 1}/{len(entries)}")
                    archive.write(path, arcname=arcname)
        except OSError as exc:
            raise ConversionError(f"無法寫入 ZIP：{exc}", detail=str(exc)) from exc

    def _write_tar(self, ctx: ConvertContext, dest: Path, entries: list[tuple[Path, str]]) -> None:
        try:
            with tarfile.open(dest, "w:gz") as archive:
                for index, (path, arcname) in enumerate(entries):
                    ctx.check_cancel()
                    ctx.report(index / len(entries) * 0.95, f"打包 {index + 1}/{len(entries)}")
                    archive.add(path, arcname=arcname, recursive=False)
        except (OSError, tarfile.TarError) as exc:
            raise ConversionError(f"無法寫入 tar.gz：{exc}", detail=str(exc)) from exc


def _same_file(a: Path, b: Path) -> bool:
    try:
        return a.resolve() == b.resolve()
    except OSError:  # pragma: no cover - 路徑無法解析時退化為字串比較
        return str(a).lower() == str(b).lower()


__all__ = ["ArchiveConverter"]
