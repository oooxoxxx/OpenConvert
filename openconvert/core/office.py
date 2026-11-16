"""LibreOffice 偵測與無介面轉換。

Office 文件（DOCX／ODT／RTF／PPTX／XLSX…）的完整排版轉換需要 LibreOffice，
它的角色與 FFmpeg 相同：**外部程式，不隨本專案散布**，由使用者自行安裝。
找不到時其他功能完全不受影響，只有 Office 相關目標會回報明確錯誤。
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from .errors import ConversionError
from .resources import tools_dir

CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


@dataclass(frozen=True)
class OfficeTools:
    soffice: Path | None = None
    bundled: bool = False

    @property
    def available(self) -> bool:
        return self.soffice is not None

    @property
    def version(self) -> str | None:
        return version_of(self.soffice)


def _bundled_candidates() -> Iterable[Path]:
    """安裝包內附的 LibreOffice（Full 版本）。"""
    local = tools_dir()
    if sys.platform == "win32":
        yield local / "libreoffice" / "program" / "soffice.exe"
        yield local / "libreoffice" / "LibreOffice" / "program" / "soffice.exe"
        yield local / "LibreOffice" / "program" / "soffice.exe"
        yield local / "soffice" / "program" / "soffice.exe"
    elif sys.platform == "darwin":
        yield local / "libreoffice" / "LibreOffice.app" / "Contents" / "MacOS" / "soffice"
    else:
        yield local / "libreoffice" / "program" / "soffice"


def _candidate_paths() -> Iterable[Path]:
    if sys.platform == "win32":
        for root in (
            os.environ.get("PROGRAMFILES", r"C:\Program Files"),
            os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)"),
        ):
            if root:
                yield Path(root) / "LibreOffice" / "program" / "soffice.exe"
    elif sys.platform == "darwin":
        yield Path("/Applications/LibreOffice.app/Contents/MacOS/soffice")
    else:
        for binary in ("soffice", "libreoffice"):
            found = shutil.which(binary)
            if found:
                yield Path(found)


def is_bundled(path: Path | None) -> bool:
    """判斷某個 soffice 是否來自安裝包內附的 tools/。"""
    if path is None:
        return False
    try:
        bundled_root = tools_dir().resolve()
        return bundled_root in path.resolve().parents
    except OSError:  # pragma: no cover - 路徑無法解析時保守回傳 False
        return False


def locate(override: str | None = None) -> Path | None:
    """依序尋找：使用者指定 → 安裝包內附 → 系統 PATH → 常見安裝位置。"""
    if override:
        candidate = Path(override).expanduser()
        if candidate.is_file():
            return candidate
        found = shutil.which(override)
        return Path(found) if found else None

    for candidate in _bundled_candidates():
        if candidate.is_file():
            return candidate

    found = shutil.which("soffice") or shutil.which("libreoffice")
    if found:
        return Path(found)
    for candidate in _candidate_paths():
        if candidate.is_file():
            return candidate
    return None


def discover(override: str | None = None) -> OfficeTools:
    found = locate(override)
    return OfficeTools(soffice=found, bundled=is_bundled(found))


def version_of(binary: Path | None) -> str | None:
    if binary is None:
        return None
    try:
        out = subprocess.run(
            [str(binary), "--version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            creationflags=CREATE_NO_WINDOW,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    lines = (out.stdout or "").strip().splitlines()
    return lines[0].strip() if lines else None


def convert_to(
    tools: OfficeTools,
    source: Path,
    dest: Path,
    extension: str,
    *,
    timeout: int = 240,
) -> Path:
    """用 LibreOffice 把 ``source`` 轉成 ``extension`` 並放到 ``dest``。

    每次都用獨立的暫時設定檔（UserInstallation），避免與已開啟的
    LibreOffice 或同時執行的其他工作互相鎖定。
    """
    if tools.soffice is None:
        raise ConversionError(
            "找不到 LibreOffice。Office 文件轉換需要 LibreOffice，請安裝後重新啟動，"
            "或在「設定」中指定 soffice 路徑。"
        )

    ext = extension.lower().lstrip(".")
    workdir = Path(tempfile.mkdtemp(prefix="openconvert-office-"))
    profile = workdir / "profile"
    outdir = workdir / "out"
    outdir.mkdir(parents=True, exist_ok=True)

    command = [
        str(tools.soffice),
        "--headless",
        "--norestore",
        "--invisible",
        "--nologo",
        "--nolockcheck",
        "--nofirststartwizard",
        f"-env:UserInstallation={profile.as_uri()}",
        "--convert-to",
        ext,
        "--outdir",
        str(outdir),
        str(source),
    ]
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            creationflags=CREATE_NO_WINDOW,
        )
        produced = _pick_output(outdir, source.stem, ext)
        if produced is None:
            detail = (result.stderr or result.stdout or "").strip()[-500:]
            raise ConversionError(
                f"LibreOffice 無法把「{source.name}」轉成 {ext.upper()}。",
                detail=detail,
            )
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            produced.replace(dest)
        except OSError:
            shutil.copyfile(produced, dest)
        return dest
    except subprocess.TimeoutExpired as exc:
        raise ConversionError(
            f"LibreOffice 轉換「{source.name}」逾時（{timeout} 秒）。檔案可能過大或已損壞。",
            detail=str(exc),
        ) from exc
    except OSError as exc:
        raise ConversionError(f"無法執行 LibreOffice：{exc}", detail=str(exc)) from exc
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def _pick_output(outdir: Path, stem: str, ext: str) -> Path | None:
    candidate = outdir / f"{stem}.{ext}"
    if candidate.exists():
        return candidate
    matches = sorted(outdir.glob(f"*.{ext}"))
    return matches[0] if matches else None


__all__ = ["OfficeTools", "convert_to", "discover", "is_bundled", "locate", "version_of"]
