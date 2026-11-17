"""引擎模組的命令列工具（本地開發與發佈流程共用）。

一般使用者不需要這個腳本：GUI 的「設定 → 引擎模組」或
``openconvert modules install <id>`` 就是完整的使用方式。

這個腳本提供兩個開發／發佈用的模式：

    python scripts/fetch_tools.py                     # 安裝全部模組到 tools/
    python scripts/fetch_tools.py --only ffmpeg
    python scripts/fetch_tools.py --dest dist/OpenConvert/tools
    python scripts/fetch_tools.py --collect assets/   # 只下載＋驗證（發佈引擎資產用）
    python scripts/fetch_tools.py --list              # 顯示清單與狀態

引擎的下載來源與 SHA-256 都定義在 ``openconvert/modules/manifest.json``。
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from openconvert.core import modules  # noqa: E402
from openconvert.core.errors import OpenConvertError  # noqa: E402


def _human(num_bytes: float) -> str:
    size = num_bytes
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"  # pragma: no cover


def print_list() -> int:
    manifest = modules.load_manifest()
    platform = modules.platform_key()
    print(f"平台：{platform}　清單頻道：{manifest.get('channel', '?')}")
    for module_id in modules.module_ids():
        spec = modules.get_module(module_id)
        state = modules.status(module_id)
        if spec is None:
            print(f"  [此平台未提供] {module_id}")
            continue
        status = "已安裝" if state.installed else "未安裝"
        location = f"　位置：{state.install_dir}" if state.install_dir else ""
        version = f"　版本：{state.version}" if state.installed else f"　版本：{spec.version}"
        size = _human(spec.size)
        print(f"  {module_id:12} {spec.label}（{size}，{spec.license}）　{status}{version}{location}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="下載／安裝引擎模組（開發與發佈用）")
    parser.add_argument("--dest", default=None, help="安裝基底目錄（預設依 resources 自動決定）")
    parser.add_argument("--only", default=None, help="只處理指定模組，例如 ffmpeg；all 表示全部")
    parser.add_argument("--collect", default=None, help="只下載＋驗證並收集到指定資料夾（發佈用）")
    parser.add_argument("--list", action="store_true", help="列出清單與狀態後結束")
    args = parser.parse_args(argv)

    try:
        if args.list:
            return print_list()

        ids = modules.module_ids()
        if args.only and args.only.lower() != "all":
            if args.only not in ids:
                print(f"錯誤：沒有「{args.only}」模組。可用：{', '.join(ids)}", file=sys.stderr)
                return 1
            ids = [args.only]

        if args.collect:
            target = Path(args.collect)
            target.mkdir(parents=True, exist_ok=True)
            for module_id in ids:
                spec = modules.get_module(module_id)
                if spec is None:
                    print(f"略過 {module_id}（此平台未提供）")
                    continue
                source = spec.origin_url or spec.url
                print(f"收集 {module_id}：{source}")
                # 收集時一律從上游取得；鏡像 Release 通常就是這個流程要建立的
                archive = modules.download_archive(module_id, use_origin=bool(spec.origin_url))
                shutil.copy2(archive, target / archive.name)
                print(f"  → {target / archive.name}（{_human(archive.stat().st_size)}，雜湊驗證通過）")
            print(f"\n已收集到 {target.resolve()}")
            return 0

        base = Path(args.dest).resolve() if args.dest else None
        for module_id in ids:
            spec = modules.get_module(module_id)
            if spec is None:
                print(f"略過 {module_id}（此平台未提供）")
                continue
            print(f"安裝 {module_id} {spec.version}（{_human(spec.size)}）")

            def on_progress(fraction: float, message: str, _id: str = module_id) -> None:
                print(f"  {_id} {fraction * 100:5.1f}%  {message}")

            path = modules.install(module_id, progress=on_progress, base=base)
            print(f"  已安裝到 {path}")

        dest = base or modules.target_base()
        notices = modules.write_notices(dest)
        if notices:
            print(f"已寫入 {notices}")
        print("\n完成。")
        return 0
    except OpenConvertError as exc:
        print(f"錯誤：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
