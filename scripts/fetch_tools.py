"""下載外部引擎（FFmpeg／LibreOffice）並放進安裝包的 ``tools/``。

這是**建置期**工具，不是執行期功能：一般使用者拿到的是已經內含引擎的
「Full」版本，完全不需要網路，也不需要電腦上先裝任何東西。

固定版本與 SHA-256 記在 ``packaging/tools.lock.json``；下載後會先驗證雜湊，
再解壓縮並依 OpenConvert 的尋找順序放到 ``tools/``：

    tools/ffmpeg/ffmpeg.exe          # FFmpeg（GPL 完整版，含 libx264）
    tools/ffmpeg/ffprobe.exe
    tools/libreoffice/program/soffice.exe

用法：

    python scripts/fetch_tools.py                 # 抓目前平台所需的全部引擎
    python scripts/fetch_tools.py --only ffmpeg
    python scripts/fetch_tools.py --dest dist/OpenConvert/tools
    python scripts/fetch_tools.py --update-lock   # 重新計算並寫回 sha256
    python scripts/fetch_tools.py --check         # 只驗證快取檔的雜湊，不安裝
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
LOCK_PATH = ROOT / "packaging" / "tools.lock.json"
CACHE_ENV = "OPENCONVERT_TOOLS_CACHE"
CHUNK = 1 << 20
USER_AGENT = "OpenConvert-build/1.0 (+https://github.com/oooxoxxx/OpenConvert)"

ENGINE_ORDER = ("ffmpeg", "libreoffice")


# --------------------------------------------------------------------------- 基本工具


def platform_key() -> str:
    machine = platform.machine().lower()
    arch = "arm64" if machine in ("arm64", "aarch64") else "x64"
    if sys.platform == "win32":
        return f"windows-{arch}"
    if sys.platform == "darwin":
        return f"macos-{arch}"
    return f"linux-{arch}"


def cache_dir() -> Path:
    override = os.environ.get(CACHE_ENV)
    base = Path(override) if override else ROOT / ".cache" / "tools"
    base.mkdir(parents=True, exist_ok=True)
    return base


def default_dest() -> Path:
    packaged = ROOT / "dist" / "OpenConvert"
    return (packaged / "tools") if packaged.is_dir() else (ROOT / "tools")


def load_lock() -> dict:
    return json.loads(LOCK_PATH.read_text(encoding="utf-8"))


def save_lock(lock: dict) -> None:
    LOCK_PATH.write_text(json.dumps(lock, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(CHUNK), b""):
            digest.update(block)
    return digest.hexdigest()


def human(num_bytes: int) -> str:
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"  # pragma: no cover


# --------------------------------------------------------------------------- 下載


def download(url: str, dest: Path, expected_sha: str, expected_size: int = 0) -> Path:
    """下載並驗證 SHA-256；快取命中時不重抓。"""
    if dest.exists() and expected_sha and sha256_of(dest) == expected_sha:
        print(f"   快取命中：{dest.name}（{human(dest.stat().st_size)}）")
        return dest

    print(f"   下載 {url}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    request = Request(url, headers={"User-Agent": USER_AGENT})
    partial = dest.with_suffix(dest.suffix + ".part")
    try:
        with urlopen(request, timeout=60) as response, partial.open("wb") as handle:
            total = int(response.headers.get("Content-Length") or expected_size or 0)
            received = 0
            next_mark = 0
            while True:
                block = response.read(CHUNK)
                if not block:
                    break
                handle.write(block)
                received += len(block)
                if total and received >= next_mark:
                    percent = received * 100 // total
                    print(f"   …{percent:3d}%  ({human(received)} / {human(total)})")
                    next_mark = received + total // 10
    except Exception as exc:  # 網路錯誤要能一眼看出
        partial.unlink(missing_ok=True)
        raise SystemExit(f"下載失敗：{url}\n  {exc}") from exc

    actual = sha256_of(partial)
    if expected_sha and actual != expected_sha:
        partial.unlink(missing_ok=True)
        raise SystemExit(
            f"SHA-256 不符，已中止：{dest.name}\n  預期 {expected_sha}\n  實際 {actual}\n"
            "若上游改了檔案，請執行 --update-lock 重新產生雜湊。"
        )
    partial.replace(dest)
    print(f"   完成：{dest.name}（{human(dest.stat().st_size)}），雜湊驗證通過")
    return dest


# --------------------------------------------------------------------------- 解壓縮


def extract(archive_type: str, archive: Path, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    print(f"   解壓縮 {archive.name} → {dest}")
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
            raise SystemExit("MSI 解壓縮只能在 Windows 上執行。")
        command = [
            "msiexec.exe",
            "/a",
            str(archive),
            "/qn",
            f"TARGETDIR={dest}",
        ]
        print("   執行 msiexec /a（管理員安裝模式，只解壓不註冊）…")
        result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if result.returncode != 0:
            raise SystemExit(
                f"msiexec 解壓縮失敗（code {result.returncode}）：{(result.stderr or '').strip()[-300:]}"
            )
        return
    raise SystemExit(f"不支援的壓縮格式：{archive_type}")


# --------------------------------------------------------------------------- 安裝


def _find_file(root: Path, names: tuple[str, ...]) -> Path | None:
    lowered = {name.lower() for name in names}
    for path in root.rglob("*"):
        if path.is_file() and path.name.lower() in lowered:
            return path
    return None


def install_ffmpeg(extracted: Path, dest_tools: Path) -> dict:
    exe = "ffmpeg.exe" if sys.platform == "win32" else "ffmpeg"
    probe = "ffprobe.exe" if sys.platform == "win32" else "ffprobe"
    ffmpeg = _find_file(extracted, (exe,))
    if ffmpeg is None:
        raise SystemExit("解壓縮後找不到 ffmpeg 執行檔。")
    ffprobe = ffmpeg.parent / probe
    if not ffprobe.is_file():
        ffprobe = _find_file(extracted, (probe,))
    if ffprobe is None:
        raise SystemExit("解壓縮後找不到 ffprobe 執行檔。")

    target = dest_tools / "ffmpeg"
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)
    shutil.copy2(ffmpeg, target / exe)
    shutil.copy2(ffprobe, target / probe)

    license_file = _find_file(extracted, ("LICENSE.txt", "LICENSE", "COPYING.GPLv3"))
    if license_file is not None:
        shutil.copy2(license_file, target / "LICENSE.txt")

    for binary in (target / exe, target / probe):
        binary.chmod(binary.stat().st_mode | 0o111)
    print(f"   已放置 {target.relative_to(dest_tools.parent.parent)}")
    return {"path": str(target), "files": [exe, probe]}


def install_libreoffice(extracted: Path, dest_tools: Path) -> dict:
    soffice = "soffice.exe" if sys.platform == "win32" else "soffice"
    program_file = _find_file(extracted, (soffice,))
    if program_file is None:
        raise SystemExit("解壓縮後找不到 soffice 執行檔。")
    program_dir = program_file.parent
    if program_dir.name.lower() != "program":
        raise SystemExit(f"LibreOffice 目錄結構非預期：{program_dir}")
    root = program_dir.parent

    target = dest_tools / "libreoffice"
    if target.exists():
        shutil.rmtree(target)
    print(f"   複製 LibreOffice 目錄樹 → {target}（檔案較多，請稍候）")
    shutil.copytree(root, target, dirs_exist_ok=True)

    for binary in target.rglob(soffice):
        binary.chmod(binary.stat().st_mode | 0o111)
    print(f"   已放置 {target.relative_to(dest_tools.parent.parent)}")
    return {"path": str(target), "files": [str(program_dir.relative_to(root) / soffice)]}


# --------------------------------------------------------------------------- 授權聲明


def write_notices(dest_tools: Path, lock: dict, platform_id: str, installed: list[str]) -> None:
    lines = [
        "OpenConvert — 隨附的第三方引擎",
        "=" * 60,
        "",
        "本目錄（tools/）中的程式不是 OpenConvert 的一部分，各有自己的授權。",
        "OpenConvert 本身以 MIT 授權釋出（見 LICENSE）。",
        "",
    ]
    for name in installed:
        engine = lock["engines"][name]
        entry = engine["targets"][platform_id]
        lines += [
            f"[{name}]",
            f"  版本    ：{entry.get('version', '未知')}",
            f"  授權    ：{engine.get('license', '未知')}",
            f"  來源    ：{entry['url']}",
            f"  SHA-256 ：{entry.get('sha256', '')}",
            f"  首頁    ：{engine.get('homepage', '')}",
            f"  原始碼  ：{engine.get('source', '')}",
            "",
        ]
    lines += [
        "FFmpeg 為 GPL 授權，對應原始碼可由 https://ffmpeg.org/download.html 取得；",
        "此處使用的是 BtbN 的 GPL 建置，建置腳本公開於 https://github.com/BtbN/FFmpeg-Builds 。",
        "LibreOffice 為 MPL-2.0 授權，原始碼與授權文字見 https://www.libreoffice.org/about-us/licenses/ 。",
        "",
    ]
    notes = dest_tools / "THIRD-PARTY-NOTICES.txt"
    notes.write_text("\n".join(lines), encoding="utf-8")
    print(f"   已寫入 {notes}")


# --------------------------------------------------------------------------- 主流程


def fetch_engine(
    name: str,
    lock: dict,
    platform_id: str,
    dest_tools: Path,
    *,
    update_lock: bool,
    check_only: bool,
) -> str | None:
    engine = lock["engines"][name]
    targets = engine.get("targets", {})
    if platform_id not in targets:
        raise SystemExit(
            f"「{name}」在 {platform_id} 上沒有固定的下載來源。\n"
            f"  目前支援：{', '.join(sorted(targets)) or '（無）'}"
        )
    entry = targets[platform_id]
    archive_name = Path(entry["url"]).name
    archive = cache_dir() / archive_name

    expected_sha = entry.get("sha256", "")
    download(entry["url"], archive, expected_sha, int(entry.get("size") or 0))

    actual_sha = sha256_of(archive)
    if update_lock:
        entry["sha256"] = actual_sha
        entry["size"] = archive.stat().st_size
        print(f"   已更新 lock：{name} / {platform_id} → {actual_sha}")

    if check_only:
        return None

    with tempfile.TemporaryDirectory(prefix=f"openconvert-{name}-") as folder:
        extracted = Path(folder) / "extracted"
        extract(entry["archive"], archive, extracted)
        if name == "ffmpeg":
            result = install_ffmpeg(extracted, dest_tools)
        elif name == "libreoffice":
            result = install_libreoffice(extracted, dest_tools)
        else:  # pragma: no cover - 由 ENGINE_ORDER 控制
            raise SystemExit(f"未知的引擎：{name}")
    return result["path"]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="下載並放置外部引擎到安裝包的 tools/")
    parser.add_argument("--dest", default=None, help="放置位置（預設 dist/OpenConvert/tools 或 tools/）")
    parser.add_argument("--only", choices=("all", *ENGINE_ORDER), default="all", help="只處理指定引擎")
    parser.add_argument("--platform", default=None, help="覆寫平台代號，例如 windows-x64")
    parser.add_argument("--update-lock", action="store_true", help="把下載檔的真實雜湊寫回 lock")
    parser.add_argument("--check", action="store_true", help="只驗證雜湊，不解壓縮或安裝")
    args = parser.parse_args(argv)

    lock = load_lock()
    platform_id = args.platform or platform_key()
    dest_tools = Path(args.dest).resolve() if args.dest else default_dest()
    names = list(ENGINE_ORDER) if args.only == "all" else [args.only]

    print(f"平台：{platform_id}")
    print(f"目的：{dest_tools}")
    installed: list[str] = []
    try:
        for name in names:
            print(f"\n[{name}]")
            if fetch_engine(
                name,
                lock,
                platform_id,
                dest_tools,
                update_lock=args.update_lock,
                check_only=args.check,
            ):
                installed.append(name)
    except SystemExit as exc:
        print(f"錯誤：{exc}", file=sys.stderr)
        return 1

    if args.update_lock:
        save_lock(lock)
        print("\n已更新 packaging/tools.lock.json")

    if installed and not args.check:
        dest_tools.mkdir(parents=True, exist_ok=True)
        write_notices(dest_tools, lock, platform_id, installed)

    if args.check:
        print("\n雜湊檢查完成。")
    else:
        print(f"\n完成，已內附：{', '.join(installed) or '（無）'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
