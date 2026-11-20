"""命令列介面。

沒有參數時啟動圖形介面；也可以完全不開視窗直接批次轉換，
方便在伺服器、腳本或 CI 中使用。
"""

from __future__ import annotations

import argparse
import contextlib
import json
import sys
from pathlib import Path

from . import APP_NAME, __version__
from .converters import get_converter
from .converters.base import ConvertContext
from .core import modules
from .core.errors import ConversionCancelled, OpenConvertError
from .core.ffmpeg import discover
from .core.job import Job
from .core.kinds import SUPPORTED_EXTENSIONS, extension_of
from .core.office import discover as office_discover
from .core.targets import TARGETS, plan_groups, target_by_token


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="openconvert",
        description="OpenConvert — 免費、離線、跨平台的檔案轉換工具",
    )
    parser.add_argument("--version", action="version", version=f"{APP_NAME} {__version__}")
    sub = parser.add_subparsers(dest="command")

    convert = sub.add_parser("convert", help="批次轉換檔案（不開視窗）")
    convert.add_argument("inputs", nargs="+", help="檔案或資料夾")
    convert.add_argument("-t", "--to", required=True, help="目標格式，例如 mp4 / png / epub")
    convert.add_argument("-o", "--output", help="輸出資料夾（預設與來源相同）")
    convert.add_argument("--quality", choices=("high", "balanced", "small"), default="balanced")
    convert.add_argument("--max-size", type=int, default=0, help="最大邊長（像素），0 表示原始尺寸")
    convert.add_argument("--fps", type=int, default=0, help="影格率（GIF、抽影格、圖片轉影片）")
    convert.add_argument("--frame-seconds", type=float, default=2.0, help="圖片轉影片時每張圖片停留的秒數")
    convert.add_argument("--sheet", default="", help="Excel 工作表名稱（留空表示使用第一個工作表）")
    convert.add_argument("--rotate", default="", help="旋轉：90／180／270（圖片與影片）或 h／v（影片翻轉）")
    convert.add_argument("--flip", default="", help="圖片翻轉：h（水平）或 v（垂直）")
    convert.add_argument("--crop", default="", help="圖片裁切比例，例如 16:9、1:1")
    convert.add_argument("--start", default="", help="截取影片的開始時間（秒或 1:30）")
    convert.add_argument("--end", default="", help="截取影片的結束時間（秒或 1:30）")
    convert.add_argument("--pdf-password", default="", help="PDF 加密／解除密碼用的密碼")
    convert.add_argument("--pages", default="", help="PDF 抽取頁碼，例如 1-3,7")
    convert.add_argument("--dpi", type=int, default=150, help="PDF 轉圖片的解析度")
    convert.add_argument("--overwrite", action="store_true", help="允許覆蓋同名輸出檔")
    convert.add_argument("--ffmpeg", help="指定 ffmpeg 執行檔路徑")
    convert.add_argument("--ffprobe", help="指定 ffprobe 執行檔路徑")
    convert.add_argument("--office", help="指定 LibreOffice 的 soffice 執行檔路徑")
    convert.add_argument("-q", "--quiet", action="store_true", help="只輸出錯誤")

    probe = sub.add_parser("probe", help="輸出檔案的中繼資料（JSON）")
    probe.add_argument("file", help="要檢視的檔案")
    probe.add_argument("--ffmpeg")
    probe.add_argument("--ffprobe")

    sub.add_parser("formats", help="列出所有支援的目標格式")

    modules_parser = sub.add_parser("modules", help="管理引擎模組（FFmpeg／LibreOffice）")
    modules_sub = modules_parser.add_subparsers(dest="modules_command")
    modules_list = modules_sub.add_parser("list", help="列出模組與安裝狀態")
    modules_list.add_argument(
        "--dest", default=None, help="安裝基底目錄（預設為程式旁的 tools/，不可寫時用使用者資料夾）"
    )
    modules_install = modules_sub.add_parser("install", help="下載並安裝模組")
    modules_install.add_argument("module", help="模組 id，例如 ffmpeg、libreoffice")
    modules_install.add_argument(
        "--dest", default=None, help="安裝基底目錄（預設為程式旁的 tools/，不可寫時用使用者資料夾）"
    )
    modules_remove = modules_sub.add_parser("remove", help="移除已安裝的模組")
    modules_remove.add_argument("module", help="模組 id")
    modules_remove.add_argument("--dest", default=None, help="安裝基底目錄")
    return parser


# --------------------------------------------------------------------------- 子命令


def _cmd_formats() -> int:
    current = ""
    for spec in TARGETS:
        if spec.category != current:
            current = spec.category
            print(f"\n[{current}]")
        flag = " (合併)" if spec.group_kinds else ""
        hint = f"  — {spec.description}" if spec.description else ""
        print(f"  {spec.token:<12} {spec.label}{flag}{hint}")
    print()
    return 0


def _expand_inputs(inputs: list[str], quiet: bool) -> list[Path]:
    paths: list[Path] = []
    for raw in inputs:
        path = Path(raw).expanduser()
        if path.is_dir():
            for child in sorted(path.rglob("*")):
                if child.is_file() and extension_of(child) in SUPPORTED_EXTENSIONS:
                    paths.append(child)
        elif path.is_file():
            paths.append(path)
        elif not quiet:
            print(f"略過（不存在）：{raw}", file=sys.stderr)
    return paths


def _cmd_convert(args: argparse.Namespace) -> int:
    spec = target_by_token(args.to)
    if spec is None:
        print(f"不支援的目標格式：{args.to}", file=sys.stderr)
        print("可用格式：openconvert formats", file=sys.stderr)
        return 2

    tools = discover(args.ffmpeg, args.ffprobe)
    if spec.needs_ffmpeg and not tools.available:
        print(
            "找不到 FFmpeg，無法轉換影片或音訊。\n"
            "  可執行：openconvert modules install ffmpeg\n"
            "  或以 --ffmpeg 指定執行檔，或自行安裝 FFmpeg。",
            file=sys.stderr,
        )
        return 3

    office_tools = office_discover(args.office)
    if spec.needs_office and not office_tools.available:
        print(
            "找不到 LibreOffice，無法轉換 Office 文件。\n"
            "  可執行：openconvert modules install libreoffice\n"
            "  或以 --office 指定 soffice 路徑，或自行安裝 LibreOffice。",
            file=sys.stderr,
        )
        return 3

    paths = _expand_inputs(args.inputs, args.quiet)
    accepted = [path for path in paths if spec.accepts(path)]
    if not accepted:
        print("沒有可以轉換成這個格式的檔案。", file=sys.stderr)
        return 2

    fps = max(0, args.fps)
    rotate_raw = str(args.rotate or "").strip().lower()
    options = {
        "quality": args.quality,
        "quality_jpeg": 90,
        "max_dimension": args.max_size,
        "pages": args.pages,
        "dpi": args.dpi,
        "gif_fps": fps or 12,
        "frame_fps": fps or 1,
        "video_fps": fps or 30,
        "frame_seconds": args.frame_seconds,
        "sheet": args.sheet,
        "rotate_degrees": int(rotate_raw) if rotate_raw in ("90", "180", "270") else rotate_raw,
        "rotate_mode": rotate_raw,
        "flip_axis": str(args.flip or "").strip().lower(),
        "crop_ratio": args.crop,
        "split_start": args.start,
        "split_end": args.end,
        "pdf_password": args.pdf_password,
    }

    groups = plan_groups(spec, accepted)
    output_dir = Path(args.output).expanduser() if args.output else None
    failed = 0

    for index, group in enumerate(groups, start=1):
        job = Job.create(group, spec, options)
        prefix = f"[{index}/{len(groups)}] {job.display_name} → {spec.label}"

        def on_progress(fraction: float, message: str, _prefix: str = prefix) -> None:
            if args.quiet:
                return
            bar_width = 24
            filled = int(fraction * bar_width)
            bar = "█" * filled + "·" * (bar_width - filled)
            print(f"\r{_prefix}  [{bar}] {fraction * 100:3.0f}%", end="", flush=True)

        ctx = ConvertContext(
            job=job,
            output_dir=output_dir,
            overwrite=args.overwrite,
            tools=tools,
            progress=on_progress,
            office=office_tools,
        )

        if not args.quiet:
            print(prefix)
        try:
            outputs = get_converter(spec.converter).convert(ctx)
            job.finish(outputs)
            if not args.quiet:
                print("\r" + " " * 90 + "\r", end="")
                for output in outputs:
                    print(f"  ✓ {output}")
        except ConversionCancelled:
            failed += 1
            print("\n  ✗ 已取消", file=sys.stderr)
        except OpenConvertError as exc:
            failed += 1
            print(f"\n  ✗ {exc.user_message}", file=sys.stderr)
        except Exception as exc:  # pragma: no cover - 未預期錯誤
            failed += 1
            print(f"\n  ✗ 未預期的錯誤：{exc}", file=sys.stderr)

    if not args.quiet:
        print(f"\n完成 {len(groups) - failed} 個，失敗 {failed} 個。")
    return 0 if failed == 0 else 1


def _cmd_probe(args: argparse.Namespace) -> int:
    from .core.inspect import describe

    tools = discover(args.ffmpeg, args.ffprobe)
    try:
        summary = describe(Path(args.file), tools)
    except OpenConvertError as exc:
        print(exc.user_message, file=sys.stderr)
        return 1

    payload = {
        "path": str(summary.path),
        "kind": summary.kind.value,
        "details": {row.label: row.value for row in summary.rows},
        "streams": [
            {
                "index": stream.index,
                "type": stream.codec_type,
                "codec": stream.codec_name,
                "width": stream.width,
                "height": stream.height,
                "fps": round(stream.fps, 3),
                "sample_rate": stream.sample_rate,
                "channels": stream.channels,
                "bit_rate": stream.bit_rate,
            }
            for stream in summary.streams
        ],
        "warnings": summary.warnings,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def _cmd_modules(args: argparse.Namespace) -> int:
    command = args.modules_command or "list"
    base = Path(args.dest).resolve() if getattr(args, "dest", None) else None
    try:
        if command == "list":
            manifest = modules.load_manifest()
            platform = modules.platform_key()
            print(f"平台：{platform}　頻道：{manifest.get('channel', '?')}")
            provided = 0
            for module_id in modules.module_ids():
                spec = modules.get_module(module_id)
                state = modules.status(module_id, base)
                if spec is None:
                    print(f"  [此平台未提供] {module_id}")
                    continue
                provided += 1
                size = f"{spec.size / 1e6:.0f} MB" if spec.size else "?"
                if state.installed:
                    print(
                        f"  {module_id:12} {spec.label}\n"
                        f"               已安裝（{state.version}）　位置：{state.install_dir}"
                    )
                else:
                    print(
                        f"  {module_id:12} {spec.label}\n"
                        f"               未安裝　大小：約 {size}　授權：{spec.license}"
                    )
            if provided == 0:
                print(f"\n此平台（{platform}）目前沒有提供任何引擎模組。")
                print("可自行安裝系統版 FFmpeg／LibreOffice，或把執行檔放進 tools/。")
            return 0

        if command == "install":
            spec = modules.get_module(args.module)
            if spec is None:
                print(f"沒有「{args.module}」模組，或此平台沒有提供。", file=sys.stderr)
                return 2

            print(f"安裝 {args.module}（{spec.label}，約 {spec.size / 1e6:.0f} MB，{spec.license}）")

            def on_progress(fraction: float, message: str) -> None:
                filled = int(fraction * 24)
                bar = "█" * filled + "·" * (24 - filled)
                print(f"\r  [{bar}] {fraction * 100:3.0f}%  {message}", end="", flush=True)

            path = modules.install(args.module, progress=on_progress, base=base)
            print("\r" + " " * 110 + "\r", end="")
            print(f"  ✓ 已安裝到 {path}")
            notices = modules.write_notices(base or modules.target_base(), base)
            if notices:
                print(f"  ✓ 授權聲明：{notices}")
            return 0

        if command == "remove":
            if modules.remove(args.module, base):
                print(f"已移除 {args.module}。")
            else:
                print(f"{args.module} 目前沒有安裝。")
            return 0
    except ConversionCancelled:
        print("\n  ✗ 已取消", file=sys.stderr)
        return 130
    except OpenConvertError as exc:
        print(f"錯誤：{exc.user_message}", file=sys.stderr)
        return 1
    return 2


# --------------------------------------------------------------------------- 入口


def _force_utf8_streams() -> None:
    """讓輸出在非 UTF-8 主控台（例如 Windows 的 cp1252）也能印中文。

    冷凍後的執行檔重新導向輸出時會沿用系統地區編碼，遇到中文或箭頭字元會直接
    UnicodeEncodeError；這裡統一把 stdout/stderr 改成 UTF-8 並以替代字元收尾。
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        with contextlib.suppress(ValueError, OSError):  # pragma: no cover - 少數替代實作不支援
            reconfigure(encoding="utf-8", errors="replace")


def main(argv: list[str] | None = None) -> int:
    _force_utf8_streams()
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        from .app import main as gui_main

        return gui_main([])
    if args.command == "formats":
        return _cmd_formats()
    if args.command == "convert":
        return _cmd_convert(args)
    if args.command == "probe":
        return _cmd_probe(args)
    if args.command == "modules":
        return _cmd_modules(args)

    parser.print_help()
    return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
