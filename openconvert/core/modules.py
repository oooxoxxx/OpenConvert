"""引擎模組管理：按需從 GitHub 下載、驗證、安裝與移除。

設計原則：

- **需要什麼下載什麼**：主程式不內附引擎；使用者要做影片才需要 FFmpeg、
  要轉 Office 才需要 LibreOffice。
- **完整性**：所有下載都會以 manifest 內的 SHA-256 驗證；不符就中止並刪除半成品。
- **不影響其他功能**：沒有網路或下載失敗時，只有需要該引擎的目標無法使用。
- **安裝位置**：優先放在程式旁的 ``tools/``（可攜式）；若該位置不可寫
  （例如裝在 Program Files），退回到使用者資料夾 ``engines/``。
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

from .errors import ConversionCancelled, ModuleError
from .resources import module_search_dirs, tools_dir, user_modules_dir

ProgressFn = Callable[[float, str], None]
CancelledFn = Callable[[], bool]

#: 供測試或進階使用者指向其他 manifest（必須經過雜湊驗證，不接受任意來源）
MANIFEST_ENV = "OPENCONVERT_MODULE_MANIFEST"
USER_AGENT = "OpenConvert-modules/1.0 (+https://github.com/oooxoxxx/OpenConvert)"

CHUNK = 1 << 20

SUPPORTED_ARCHIVES = ("zip", "tar.xz", "tar.gz", "tar.bz2", "msi")


# --------------------------------------------------------------------------- manifest


@dataclass(frozen=True)
class ModuleSpec:
    """一個引擎模組在某個平台上的固定下載資訊。"""

    id: str
    label: str
    purpose: str
    license: str
    homepage: str
    source: str
    source_page: str
    version: str
    url: str
    sha256: str
    size: int
    archive: str
    #: 上游原始網址；首次收集引擎資產時使用（鏡像 Release 還不存在）
    origin_url: str = ""


@dataclass
class ModuleState:
    """模組目前的安裝狀態。"""

    spec: ModuleSpec | None
    installed: bool = False
    install_dir: Path | None = None
    version: str = ""
    error: str = ""


def platform_key() -> str:
    import platform as _platform

    machine = _platform.machine().lower()
    arch = "arm64" if machine in ("arm64", "aarch64") else "x64"
    if sys.platform == "win32":
        return f"windows-{arch}"
    if sys.platform == "darwin":
        return f"macos-{arch}"
    return f"linux-{arch}"


def manifest_path() -> Path:
    return Path(__file__).resolve().parent.parent / "modules" / "manifest.json"


def load_manifest() -> dict[str, Any]:
    """讀取模組清單；``OPENCONVERT_MODULE_MANIFEST`` 可指向其他檔案（仍須結構正確）。"""
    override = os.environ.get(MANIFEST_ENV)
    path = Path(override) if override else manifest_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ModuleError(f"找不到模組清單：{path}") from exc
    except (OSError, ValueError) as exc:
        raise ModuleError(f"模組清單無法解析（{path.name}）：{exc}") from exc

    if not isinstance(data, dict) or "modules" not in data:
        raise ModuleError(f"模組清單格式不正確：{path}")
    return data


def module_ids() -> list[str]:
    return sorted(load_manifest()["modules"])


def get_module(module_id: str) -> ModuleSpec | None:
    """取得某模組在**目前平台**的規格；沒有對應平台或模組不存在時回傳 ``None``。"""
    data = load_manifest()
    entry = data["modules"].get(module_id)
    if not isinstance(entry, dict):
        return None
    target = (entry.get("targets") or {}).get(platform_key())
    if not isinstance(target, dict):
        return None
    try:
        return ModuleSpec(
            id=module_id,
            label=str(entry.get("label") or module_id),
            purpose=str(entry.get("purpose") or ""),
            license=str(entry.get("license") or ""),
            homepage=str(entry.get("homepage") or ""),
            source=str(entry.get("source") or ""),
            source_page=str(entry.get("source_page") or ""),
            version=str(target.get("version") or ""),
            url=str(target["url"]),
            sha256=str(target.get("sha256") or ""),
            size=int(target.get("size") or 0),
            archive=str(target.get("archive") or ""),
            origin_url=str((target.get("origin") or {}).get("url") or target.get("origin_url") or ""),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ModuleError(f"模組「{module_id}」的清單資料不完整：{exc}") from exc


def all_modules() -> list[ModuleSpec | None]:
    return [get_module(module_id) for module_id in module_ids()]


# --------------------------------------------------------------------------- 安裝位置


def _ensure_writable(base: Path) -> bool:
    try:
        base.mkdir(parents=True, exist_ok=True)
        probe = base / ".write-test"
        probe.write_bytes(b"")
        probe.unlink()
        return True
    except OSError:
        return False


def target_base() -> Path:
    """回傳第一個可寫的模組安裝基底目錄；都不可寫時回傳 ``tools/``（安裝時會報錯）。"""
    for base in module_search_dirs():
        if _ensure_writable(base):
            return base
    return tools_dir()


def install_dir(module_id: str) -> Path:
    return target_base() / module_id


def _marker(install_path: Path) -> Path:
    return install_path / ".openconvert-module.json"


def _write_marker(install_path: Path, spec: ModuleSpec, files: list[str]) -> None:
    payload = {
        "id": spec.id,
        "version": spec.version,
        "url": spec.url,
        "sha256": spec.sha256,
        "files": files,
    }
    _marker(install_path).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def installed_dir(module_id: str, base: Path | None = None) -> Path | None:
    """找到已安裝的模組；回傳 ``None`` 表示未安裝。"""
    candidates = ((base,) if base is not None else ()) + module_search_dirs()
    for root in candidates:
        candidate = root / module_id
        if not candidate.is_dir():
            continue
        if _marker(candidate).exists() or any(candidate.iterdir()):
            return candidate
    return None


def installed_version(module_id: str, base: Path | None = None) -> str:
    install_path = installed_dir(module_id, base)
    if install_path is None:
        return ""
    marker = _marker(install_path)
    if marker.exists():
        try:
            return str(json.loads(marker.read_text(encoding="utf-8")).get("version") or "")
        except (OSError, ValueError):
            return ""
    return "未知版本"


def status(module_id: str, base: Path | None = None) -> ModuleState:
    """回傳模組目前狀態；清單缺平台資料時 ``spec`` 為 ``None``。"""
    spec = get_module(module_id)
    install_path = installed_dir(module_id, base)
    if install_path is None:
        return ModuleState(spec=spec, installed=False)
    return ModuleState(
        spec=spec,
        installed=True,
        install_dir=install_path,
        version=installed_version(module_id, base),
    )


def remove(module_id: str, base: Path | None = None) -> bool:
    install_path = installed_dir(module_id, base)
    if install_path is None:
        return False
    shutil.rmtree(install_path, ignore_errors=True)
    return True


# --------------------------------------------------------------------------- 下載


def cache_dir() -> Path:
    base = user_modules_dir().parent / "module-cache"
    base.mkdir(parents=True, exist_ok=True)
    return base


def _sha256(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(CHUNK), b""):
            digest.update(block)
    return digest.hexdigest()


def _download(spec: ModuleSpec, progress: ProgressFn, cancelled: CancelledFn | None) -> Path:
    cache = cache_dir() / Path(spec.url).name
    if cache.exists() and (not spec.sha256 or _sha256(cache) == spec.sha256):
        progress(0.55, f"使用快取（{_human(cache.stat().st_size)}）")
        return cache

    partial = cache.with_suffix(cache.suffix + ".part")
    request = Request(spec.url, headers={"User-Agent": USER_AGENT})
    try:
        with urlopen(request, timeout=60) as response, partial.open("wb") as handle:
            total = int(response.headers.get("Content-Length") or spec.size or 0)
            received = 0
            while True:
                if cancelled and cancelled():
                    raise ConversionCancelled("已取消下載")
                block = response.read(CHUNK)
                if not block:
                    break
                handle.write(block)
                received += len(block)
                if total:
                    percent = received * 100 // total
                    progress(
                        0.05 + min(0.45, received / max(1, total) * 0.45),
                        f"下載中 {percent}%（{_human(received)} / {_human(total)}）",
                    )
                else:
                    progress(0.25, f"下載中（{_human(received)}）")
    except ConversionCancelled:
        partial.unlink(missing_ok=True)
        raise
    except (URLError, OSError) as exc:
        partial.unlink(missing_ok=True)
        raise ModuleError(
            f"無法下載「{spec.label}」：{exc}\n"
            "請確認網路連線後重試；沒有網路時可以改用 Full 版本或自行放置 tools/。"
        ) from exc

    if spec.sha256 and _sha256(partial) != spec.sha256:
        partial.unlink(missing_ok=True)
        raise ModuleError(
            f"下載的「{spec.label}」SHA-256 驗證失敗，已中止安裝。\n"
            "這可能是來源檔案變動或下載不完整；請重試，或向專案回報。"
        )
    partial.replace(cache)
    return cache


def _human(num_bytes: float) -> str:
    size = num_bytes
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"  # pragma: no cover


# --------------------------------------------------------------------------- 解壓與安裝


def _extract(archive_type: str, archive: Path, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    if archive_type == "zip":
        with zipfile.ZipFile(archive) as bundle:
            bundle.extractall(dest)
        return
    if archive_type in ("tar.xz", "tar.gz", "tar.bz2"):
        mode = {"tar.xz": "r:xz", "tar.gz": "r:gz", "tar.bz2": "r:bz2"}[archive_type]
        with tarfile.open(archive, mode) as bundle:
            try:
                bundle.extractall(dest, filter="data")
            except TypeError:  # Python 3.11 以前沒有 filter 參數
                bundle.extractall(dest)
        return
    if archive_type == "msi":
        if sys.platform != "win32":
            raise ModuleError("MSI 解壓縮只能在 Windows 上執行。")
        result = subprocess.run(
            ["msiexec.exe", "/a", str(archive), "/qn", f"TARGETDIR={dest}"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if result.returncode != 0:
            raise ModuleError(
                f"LibreOffice 安裝包解壓失敗（code {result.returncode}）："
                f"{(result.stderr or '').strip()[-300:]}"
            )
        return
    raise ModuleError(f"不支援的引擎壓縮格式：{archive_type}")


def _find_file(root: Path, names: tuple[str, ...]) -> Path | None:
    lowered = {name.lower() for name in names}
    for path in root.rglob("*"):
        if path.is_file() and path.name.lower() in lowered:
            return path
    return None


def _install_ffmpeg(extracted: Path, install_path: Path, spec: ModuleSpec) -> list[str]:
    exe = "ffmpeg.exe" if sys.platform == "win32" else "ffmpeg"
    probe = "ffprobe.exe" if sys.platform == "win32" else "ffprobe"
    found = _find_file(extracted, (exe,))
    probe_found = _find_file(extracted, (probe,))
    if found is None or probe_found is None:
        raise ModuleError("引擎壓縮檔內找不到 ffmpeg／ffprobe，安裝已中止。")

    shutil.copy2(found, install_path / exe)
    shutil.copy2(probe_found, install_path / probe)
    license_file = _find_file(extracted, ("LICENSE.txt", "LICENSE", "COPYING.GPLv3"))
    if license_file is not None:
        shutil.copy2(license_file, install_path / "LICENSE.txt")
    for binary in (install_path / exe, install_path / probe):
        binary.chmod(binary.stat().st_mode | 0o111)
    return [exe, probe]


def _install_libreoffice(extracted: Path, install_path: Path, spec: ModuleSpec) -> list[str]:
    soffice = "soffice.exe" if sys.platform == "win32" else "soffice"
    found = _find_file(extracted, (soffice,))
    if found is None:
        raise ModuleError("LibreOffice 安裝包內找不到 soffice，安裝已中止。")
    program_dir = found.parent
    if program_dir.name.lower() != "program":
        raise ModuleError(f"LibreOffice 目錄結構非預期：{program_dir}")

    shutil.copytree(program_dir.parent, install_path, dirs_exist_ok=True)
    for binary in install_path.rglob(soffice):
        binary.chmod(binary.stat().st_mode | 0o111)
    return [str((program_dir / soffice).relative_to(program_dir.parent))]


_INSTALLERS = {
    "ffmpeg": _install_ffmpeg,
    "libreoffice": _install_libreoffice,
}


def download_archive(
    module_id: str,
    *,
    cancelled: CancelledFn | None = None,
    use_origin: bool = False,
) -> Path:
    """只下載並驗證模組壓縮檔（供發佈流程收集資產用），不安裝。

    ``use_origin=True`` 時從上游原始網址下載——首次建立引擎鏡像 Release 時，
    manifest 指向的鏡像還不存在，必須先從上游取得。
    """
    cancelled = cancelled or (lambda: False)
    spec = get_module(module_id)
    if spec is None:
        raise ModuleError(f"沒有「{module_id}」模組，或它沒有支援 {platform_key()} 的版本。")
    if use_origin:
        if not spec.origin_url:
            raise ModuleError(f"模組「{module_id}」沒有設定上游來源（origin）。")
        spec = replace(spec, url=spec.origin_url)
    return _download(spec, lambda *_args: None, cancelled)


def install(
    module_id: str,
    *,
    progress: ProgressFn | None = None,
    cancelled: CancelledFn | None = None,
    base: Path | None = None,
) -> Path:
    """下載並安裝模組；回傳安裝目錄。

    Raises:
        ModuleError: 平台不支援、下載或驗證失敗、安裝位置不可寫。
        ConversionCancelled: 使用者取消。
    """
    progress = progress or (lambda *_args: None)
    cancelled = cancelled or (lambda: False)
    cancelled()

    spec = get_module(module_id)
    if spec is None:
        available = "、".join(module_ids()) or "（無）"
        raise ModuleError(
            f"沒有「{module_id}」模組，或它沒有支援 {platform_key()} 的版本。\n可用的模組：{available}"
        )
    if spec.archive not in SUPPORTED_ARCHIVES:
        raise ModuleError(f"模組「{module_id}」使用了不支援的壓縮格式：{spec.archive}")

    install_path = (base or target_base()) / module_id
    try:
        install_path.mkdir(parents=True, exist_ok=True)
        probe = install_path / ".write-test"
        probe.write_bytes(b"")
        probe.unlink()
    except OSError as exc:
        raise ModuleError(
            f"無法寫入安裝位置 {install_path}：{exc}\n"
            "請以系統管理員執行一次，或改用可攜式（解壓到可寫入的資料夾）安裝。"
        ) from exc

    progress(0.02, "準備下載")
    archive = _download(spec, progress, cancelled)
    progress(0.5, "驗證完成，解壓縮中")

    with tempfile.TemporaryDirectory(prefix=f"openconvert-{module_id}-") as folder:
        extracted = Path(folder) / "extracted"
        try:
            _extract(spec.archive, archive, extracted)
        except (OSError, zipfile.BadZipFile, tarfile.TarError) as exc:
            raise ModuleError(f"引擎壓縮檔無法解壓：{exc}") from exc

        progress(0.8, "安裝檔案（檔案較多時請稍候）")
        installer = _INSTALLERS.get(module_id)
        if installer is None:
            # 沒有專屬安裝器的模組：把整個解壓內容視為安裝內容
            shutil.copytree(extracted, install_path, dirs_exist_ok=True)
            files = ["<extracted>"]
        else:
            if install_path.exists():
                shutil.rmtree(install_path, ignore_errors=True)
            install_path.mkdir(parents=True)
            files = installer(extracted, install_path, spec)

        progress(0.95, "寫入安裝紀錄")
        _write_marker(install_path, spec, files)

    progress(1.0, f"已安裝 {spec.label} {spec.version}")
    return install_path


def write_notices(dest: Path, base: Path | None = None) -> Path | None:
    """把已安裝模組的授權與來源寫成聲明檔。"""
    installed: list[ModuleSpec] = []
    for module_id in module_ids():
        state = status(module_id, base)
        if state.installed and state.spec is not None:
            installed.append(state.spec)
    if not installed:
        return None

    lines = [
        "OpenConvert — 已安裝的第三方引擎",
        "=" * 60,
        "",
        "本目錄（tools/ 或 engines/）中的程式不是 OpenConvert 的一部分，各有自己的授權。",
        "OpenConvert 本身以 MIT 授權釋出（見 LICENSE）。",
        "",
    ]
    for spec in installed:
        lines += [
            f"[{spec.id}]",
            f"  版本    ：{spec.version}",
            f"  授權    ：{spec.license}",
            f"  來源    ：{spec.url}",
            f"  首頁    ：{spec.homepage}",
            f"  原始碼  ：{spec.source}",
            "",
        ]
    lines += [
        "FFmpeg 為 GPL 授權，原始碼可由 https://ffmpeg.org/download.html 取得；",
        "此處使用的是 BtbN 的 GPL 建置，建置腳本公開於 https://github.com/BtbN/FFmpeg-Builds 。",
        "LibreOffice 為 MPL-2.0 授權，原始碼與授權文字見 https://www.libreoffice.org/about-us/licenses/ 。",
        "",
    ]
    target = dest / "THIRD-PARTY-NOTICES.txt"
    target.write_text("\n".join(lines), encoding="utf-8")
    return target


__all__ = [
    "MANIFEST_ENV",
    "ModuleError",
    "ModuleSpec",
    "ModuleState",
    "all_modules",
    "download_archive",
    "get_module",
    "install",
    "installed_dir",
    "installed_version",
    "load_manifest",
    "module_ids",
    "platform_key",
    "remove",
    "status",
    "write_notices",
]
