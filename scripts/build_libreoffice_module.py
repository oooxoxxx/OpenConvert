"""建立「精簡版 LibreOffice」模組。

從官方 MSI（管理員安裝模式解壓）取出可攜目錄樹，移除 OpenConvert 用不到的
元件（圖庫、範本、精靈、字典、Basic 巨集、Python、其他語言資源……），
只保留 headless 轉換需要的部分，最後打包成 ZIP。

刪除了什麼會完整記錄在 ``STRIP-MANIFEST.txt``，方便事後審查與還原。

用法：

    python scripts/build_libreoffice_module.py                 # 用 .cache 裡的官方 MSI
    python scripts/build_libreoffice_module.py --msi <路徑>
    python scripts/build_libreoffice_module.py --out assets
"""

from __future__ import annotations

import argparse
import hashlib
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from openconvert.core import modules  # noqa: E402
from openconvert.core.errors import ModuleError  # noqa: E402

#: 要整個移除的目錄（相對於 LibreOffice 根目錄）
REMOVE_DIRS = (
    "share/gallery",
    "share/template",
    "share/templates",
    "share/wizards",
    "share/autotext",
    "share/basic",
    "share/Scripts",
    "share/scripts",
    "share/dict",
    "share/extensions",
    "share/palette",
    "share/wordbook",
    "share/uno_packages",
    "share/cli_uno",
    "share/java",
    "program/classes",
    "program/python-core-*/**",
    "program/python",
    "program/python.exe",
    "program/pythonw.exe",
    "program/libpyuno*",
    "program/pyuno*",
    "readmes",
)

#: 要移除的檔案（支援萬用字元）
REMOVE_FILES = (
    "program/README*",
    "program/*.txt.orig",
    "*.readme",
    "readmes/*",
)

#: 語言資源只保留這些（大小寫不敏感）
KEEP_LANGS = ("zh-tw", "zh-hant", "en-us", "en")

LANG_RESOURCE_DIRS = ("program/resource",)


def _human(num_bytes: float) -> str:
    size = num_bytes
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"  # pragma: no cover


def _dir_size(path: Path) -> int:
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())


def _find_soffice(extracted: Path) -> Path:
    found = modules._find_file(extracted, ("soffice.exe" if sys.platform == "win32" else "soffice",))
    if found is None:
        raise SystemExit("MSI 解壓後找不到 soffice。")
    program_dir = found.parent
    if program_dir.name.lower() != "program":
        raise SystemExit(f"LibreOffice 目錄結構非預期：{program_dir}")
    return program_dir.parent


def extract_msi(msi: Path, dest: Path) -> None:
    if sys.platform != "win32":
        raise SystemExit("MSI 解壓縮只能在 Windows 上執行。")
    result = subprocess.run(
        ["msiexec.exe", "/a", str(msi), "/qn", f"TARGETDIR={dest}"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        raise SystemExit(f"msiexec 解壓失敗（code {result.returncode}）：{(result.stderr or '')[-300:]}")


def strip_tree(root: Path, removed: list[tuple[str, int]]) -> None:
    def remove(relative: str) -> None:
        target = root / relative
        if target.is_dir():
            size = _dir_size(target)
            shutil.rmtree(target, ignore_errors=True)
            removed.append((relative + "/", size))
        elif target.exists():
            size = target.stat().st_size
            target.unlink()
            removed.append((relative, size))

    for item in REMOVE_DIRS:
        if item.endswith("/**"):
            pattern = item[:-3]
            for match in sorted(root.glob(pattern)):
                remove(match.relative_to(root).as_posix())
        else:
            remove(item)
    for pattern in REMOVE_FILES:
        for match in sorted(root.glob(pattern)):
            remove(match.relative_to(root).as_posix())

    # 語言資源：只保留 KEEP_LANGS
    for resource_dir in LANG_RESOURCE_DIRS:
        base = root / resource_dir
        if not base.is_dir():
            continue
        for child in sorted(base.iterdir()):
            if child.is_dir() and child.name.lower() not in KEEP_LANGS:
                size = _dir_size(child)
                relative = child.relative_to(root).as_posix()
                shutil.rmtree(child, ignore_errors=True)
                removed.append((relative + "/", size))


def write_reports(root: Path, removed: list[tuple[str, int]], version: str) -> None:
    lines = [
        "LibreOffice 精簡模組 — 移除項目清單",
        "=" * 56,
        f"版本：{version}",
        "",
        "以下目錄／檔案已從官方安裝樹移除；OpenConvert 的 headless 轉換不需要它們。",
        "如需完整功能，請安裝官方 LibreOffice（OpenConvert 會優先使用系統已安裝的版本）。",
        "",
    ]
    for relative, size in sorted(removed, key=lambda item: -item[1]):
        lines.append(f"  {size / (1 << 20):8.1f} MB  {relative}")
    lines += [
        "",
        "合計移除：" + _human(sum(size for _path, size in removed)),
    ]
    (root / "STRIP-MANIFEST.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")

    notices = [
        "OpenConvert — 已安裝的第三方引擎",
        "=" * 56,
        "",
        "本目錄中的 LibreOffice 為官方安裝樹的精簡版本（MPL-2.0）。",
        "移除項目見 STRIP-MANIFEST.txt；原始碼與完整授權見 https://www.libreoffice.org/ 。",
        "",
    ]
    (root / "THIRD-PARTY-NOTICES.txt").write_text("\n".join(notices) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="建立精簡版 LibreOffice 模組")
    parser.add_argument("--msi", default=None, help="官方 MSI 路徑（預設依 manifest 的 build 來源下載）")
    parser.add_argument("--out", default="assets", help="輸出資料夾（預設 assets/）")
    args = parser.parse_args(argv)

    manifest = modules.load_manifest()
    entry = manifest["modules"].get("libreoffice")
    if not isinstance(entry, dict):
        raise SystemExit("manifest 中沒有 libreoffice 模組。")
    build = (entry.get("build") or {}).get(modules.platform_key())
    if not isinstance(build, dict) or not build.get("origin_url"):
        raise SystemExit(
            f"manifest 中沒有 libreoffice 在 {modules.platform_key()} 的建置來源（build.origin_url）。"
        )

    version = str(build.get("version") or "unknown")
    if args.msi:
        msi = Path(args.msi)
    else:
        msi = modules.cache_dir() / Path(build["origin_url"]).name
        if not msi.exists():
            print("下載官方 MSI（SHA-256 驗證）…")
            msi = modules.download_file(
                build["origin_url"],
                str(build.get("origin_sha256") or ""),
                size=int(build.get("origin_size") or 0),
                label="LibreOffice 官方安裝包",
            )
    if not msi.exists():
        raise SystemExit(f"找不到 MSI：{msi}")

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    output = out_dir / f"LibreOffice_{version}_win64_stripped.zip"
    if output.exists():
        print(f"已存在，跳過：{output}")
        return 0

    print(f"來源：{msi.name}（{_human(msi.stat().st_size)}）")
    with tempfile.TemporaryDirectory(prefix="openconvert-lo-strip-") as folder:
        extracted = Path(folder) / "extracted"
        print("解壓 MSI（管理員安裝模式）…")
        extract_msi(msi, extracted)
        root = _find_soffice(extracted)

        before = _dir_size(root)
        removed: list[tuple[str, int]] = []
        print("剝離不需要的元件…")
        strip_tree(root, removed)
        after = _dir_size(root)
        write_reports(root, removed, version)

        print(
            f"大小：{_human(before)} → {_human(after)}（移除 {_human(before - after)}，"
            f"{len(removed)} 個項目）"
        )

        print(f"打包 {output.name} …")
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as bundle:
            for item in sorted(root.rglob("*")):
                if item.is_file():
                    bundle.write(item, item.relative_to(root).as_posix())

    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    print(f"輸出：{output}（{_human(output.stat().st_size)}）")
    print(f"SHA-256：{digest}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ModuleError as exc:
        print(f"錯誤：{exc}", file=sys.stderr)
        raise SystemExit(1) from exc
