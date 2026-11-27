"""封裝與解壓：ZIP、7z、tar.gz、tar.zst，以及多格式解壓。"""

from __future__ import annotations

import shutil
import tarfile
import tempfile
import zipfile
from pathlib import Path, PureWindowsPath

from ..core.errors import ConversionError
from ..core.paths import resolve_output_dir
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


def _safe_member(name: str) -> str | None:
    """過濾不安全的路徑（絕對路徑、磁碟機、上層跳脫、空段落）。"""
    normalized = name.replace("\\", "/")
    if (
        not normalized
        or normalized.startswith(("/", "~"))
        or PureWindowsPath(name).drive
        or any(":" in part for part in normalized.split("/"))
    ):
        return None
    parts = normalized.split("/")
    if any(part in ("", ".", "..") for part in parts):
        return None
    return normalized


def _copy_stream(source, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("wb") as handle:
        shutil.copyfileobj(source, handle)


def _archive_stem(source: Path) -> str:
    """去掉完整的壓縮副檔名，避免產生 ``name.tar_extracted``。"""
    lowered = source.name.lower()
    for suffix in (".tar.gz", ".tar.zst", ".tar.bz2", ".tar.xz", ".tgz", ".tbz", ".tbz2", ".txz"):
        if lowered.endswith(suffix):
            return source.name[: -len(suffix)]
    return source.stem


class ArchiveConverter(Converter):
    name = "archive"

    def convert(self, ctx: ConvertContext) -> list[Path]:
        self.ensure_source_exists(ctx)
        token = ctx.token
        if token == "archive-extract":
            return self._extract(ctx)
        return self._pack(ctx, token)

    # ------------------------------------------------------------ 打包

    def _pack(self, ctx: ConvertContext, token: str) -> list[Path]:
        sources = ctx.sources
        first = sources[0]
        extension = ctx.job.target.extension
        name = f"{first.stem}_archive" if len(sources) > 1 else first.stem
        dest = ctx.resolve_output(first.with_name(name), extension)
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
        elif extension == "7z":
            self._write_7z(ctx, dest, entries)
        elif extension == "tar.zst":
            self._write_tar_zst(ctx, dest, entries)
        else:  # pragma: no cover - 目標宣告已窮舉
            raise ConversionError(f"不支援的封裝格式：{extension}")

        ctx.report(1.0, "完成")
        self._verify(dest)
        return [dest]

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

    def _write_7z(self, ctx: ConvertContext, dest: Path, entries: list[tuple[Path, str]]) -> None:
        try:
            import py7zr
        except ImportError as exc:  # pragma: no cover - 依賴缺失
            raise ConversionError("打包 7z 需要 py7zr 套件，請執行 pip install py7zr。") from exc

        try:
            with py7zr.SevenZipFile(dest, "w") as archive:
                for index, (path, arcname) in enumerate(entries):
                    ctx.check_cancel()
                    ctx.report(index / len(entries) * 0.95, f"打包 {index + 1}/{len(entries)}")
                    archive.write(str(path), arcname)
        except (OSError, py7zr.exceptions.ArchiveError) as exc:
            raise ConversionError(f"無法寫入 7z：{exc}", detail=str(exc)) from exc

    def _write_tar_zst(self, ctx: ConvertContext, dest: Path, entries: list[tuple[Path, str]]) -> None:
        try:
            import zstandard as zstd
        except ImportError as exc:  # pragma: no cover - 依賴缺失
            raise ConversionError("打包 tar.zst 需要 zstandard 套件，請執行 pip install zstandard。") from exc

        try:
            with (
                dest.open("wb") as raw,
                zstd.ZstdCompressor(level=6).stream_writer(raw) as compressor,
                tarfile.open(fileobj=compressor, mode="w|") as archive,
            ):
                for index, (path, arcname) in enumerate(entries):
                    ctx.check_cancel()
                    ctx.report(index / len(entries) * 0.95, f"打包 {index + 1}/{len(entries)}")
                    archive.add(path, arcname=arcname, recursive=False)
        except (OSError, tarfile.TarError, zstd.ZstdError) as exc:
            raise ConversionError(f"無法寫入 tar.zst：{exc}", detail=str(exc)) from exc

    # ------------------------------------------------------------ 解壓

    def _extract(self, ctx: ConvertContext) -> list[Path]:
        source = ctx.source
        out_dir = resolve_output_dir(source, ctx.output_dir, f"{_archive_stem(source)}_extracted")
        ctx.track(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        suffix = source.suffix.lower()
        written = 0
        if suffix == ".zip":
            written = self._extract_zip(ctx, source, out_dir)
        elif suffix == ".7z":
            written = self._extract_7z(ctx, source, out_dir)
        elif suffix in (".tar", ".gz", ".zst", ".bz2", ".xz", ".tgz", ".tbz", ".tbz2", ".txz"):
            written = self._extract_tar(ctx, source, out_dir)
        else:
            raise ConversionError(f"不支援解壓的格式：{suffix or source.name}")

        if not written:
            raise ConversionError("壓縮檔中沒有可解壓的檔案。")
        ctx.report(1.0, "完成")
        return [out_dir]

    def _extract_zip(self, ctx: ConvertContext, source: Path, out_dir: Path) -> int:
        written = 0
        try:
            with zipfile.ZipFile(source) as archive:
                members = [info for info in archive.infolist() if not info.is_dir()]
                for index, info in enumerate(members):
                    ctx.check_cancel()
                    safe = _safe_member(info.filename)
                    if safe is None:
                        ctx.log(f"略過不安全的路徑：{info.filename}")
                        continue
                    ctx.report(index / max(1, len(members)) * 0.95, f"解壓 {index + 1}/{len(members)}")
                    with archive.open(info) as src:
                        _copy_stream(src, out_dir / safe)
                    written += 1
        except (zipfile.BadZipFile, OSError) as exc:
            raise ConversionError(f"無法解壓「{source.name}」：{exc}", detail=str(exc)) from exc
        return written

    def _extract_7z(self, ctx: ConvertContext, source: Path, out_dir: Path) -> int:
        try:
            import py7zr
        except ImportError as exc:  # pragma: no cover - 依賴缺失
            raise ConversionError("解壓 7z 需要 py7zr 套件，請執行 pip install py7zr。") from exc

        try:
            with py7zr.SevenZipFile(source, "r") as archive:
                names = [name for name in archive.getnames() if not archive.getinfo(name).is_directory]
                safe_names = [name for name in names if _safe_member(name) is not None]
                if not safe_names:
                    raise ConversionError("壓縮檔中沒有可解壓的檔案。")
                if len(safe_names) == len(names):
                    archive.extractall(path=str(out_dir))
                    return len(safe_names)

                # 有不安全路徑：先解到暫存目錄，再只複製安全檔案
                with tempfile.TemporaryDirectory(prefix="openconvert-7z-") as folder:
                    temp_dir = Path(folder)
                    archive.extractall(path=str(temp_dir))
                    for name in safe_names:
                        src = temp_dir / name
                        if src.is_file():
                            dest = out_dir / name
                            dest.parent.mkdir(parents=True, exist_ok=True)
                            shutil.copyfile(src, dest)
                return len(safe_names)
        except (OSError, py7zr.exceptions.ArchiveError) as exc:
            raise ConversionError(f"無法解壓「{source.name}」：{exc}", detail=str(exc)) from exc

    def _extract_tar(self, ctx: ConvertContext, source: Path, out_dir: Path) -> int:
        if source.suffix.lower() == ".zst":
            try:
                import zstandard as zstd
            except ImportError as exc:  # pragma: no cover - 依賴缺失
                raise ConversionError(
                    "解壓 tar.zst 需要 zstandard 套件，請執行 pip install zstandard。"
                ) from exc

            try:
                with (
                    source.open("rb") as raw,
                    zstd.ZstdDecompressor().stream_reader(raw) as reader,
                    tarfile.open(fileobj=reader, mode="r|") as archive,
                ):
                    # stream 模式的 tar 不能預先 list()，否則會要求回退 seek。
                    return self._extract_tar_members(ctx, archive, out_dir)
            except (OSError, tarfile.TarError, zstd.ZstdError) as exc:
                raise ConversionError(f"無法解壓「{source.name}」：{exc}", detail=str(exc)) from exc

        try:
            with tarfile.open(source, "r:*") as archive:
                return self._extract_tar_members(ctx, archive, out_dir, archive.getmembers())
        except (OSError, tarfile.TarError) as exc:
            raise ConversionError(f"無法解壓「{source.name}」：{exc}", detail=str(exc)) from exc

    def _extract_tar_members(
        self,
        ctx: ConvertContext,
        archive: tarfile.TarFile,
        out_dir: Path,
        members: list[tarfile.TarInfo] | None = None,
    ) -> int:
        written = 0
        items = archive if members is None else members
        total = len(members) if members is not None else None
        for index, member in enumerate(items):
            if not member.isfile():
                continue
            ctx.check_cancel()
            safe = _safe_member(member.name)
            if safe is None:
                ctx.log(f"略過不安全的路徑：{member.name}")
                continue
            fraction = index / max(1, total) * 0.95 if total is not None else 0.0
            label = f"解壓 {index + 1}/{total}" if total is not None else f"解壓第 {index + 1} 個項目"
            ctx.report(fraction, label)
            handle = archive.extractfile(member)
            if handle is not None:
                with handle:
                    _copy_stream(handle, out_dir / safe)
                written += 1
        return written

    # ------------------------------------------------------------ 檢查

    @staticmethod
    def _verify(path: Path) -> None:
        if not path.exists() or path.stat().st_size == 0:
            path.unlink(missing_ok=True)
            raise ConversionError("封裝失敗，沒有產生有效檔案。")


def _same_file(a: Path, b: Path) -> bool:
    try:
        return a.resolve() == b.resolve()
    except OSError:  # pragma: no cover - 路徑無法解析時退化為字串比較
        return str(a).lower() == str(b).lower()
