"""GUI 共用小工具：開啟檔案 / 資料夾、時間格式。"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices


def open_path(path: str | Path) -> bool:
    """用系統預設程式開啟檔案或資料夾。"""
    target = Path(path)
    if not target.exists():
        return False
    if target.is_dir():
        return QDesktopServices.openUrl(QUrl.fromLocalFile(str(target)))
    return QDesktopServices.openUrl(QUrl.fromLocalFile(str(target)))


def reveal_in_folder(path: str | Path) -> None:
    """在檔案總管 / Finder 中選取該檔案。"""
    target = Path(path)
    try:
        if sys.platform == "win32":
            if target.exists():
                subprocess.Popen(["explorer", "/select,", str(target)])
            else:
                _open_directory(target.parent)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", "-R", str(target)])
        else:
            _open_directory(target.parent)
    except OSError:
        _open_directory(target.parent)


def _open_directory(directory: Path) -> None:
    QDesktopServices.openUrl(QUrl.fromLocalFile(str(directory)))


def open_outputs(outputs: list[Path]) -> None:
    """依輸出數量決定要開資料夾還是選取檔案。"""
    if not outputs:
        return
    if len(outputs) == 1:
        target = outputs[0]
        if target.is_dir():
            open_path(target)
        else:
            reveal_in_folder(target)
        return
    open_path(outputs[0].parent)


def human_time(seconds: float) -> str:
    if seconds < 1:
        return "< 1 秒"
    if seconds < 60:
        return f"{seconds:.0f} 秒"
    minutes, secs = divmod(round(seconds), 60)
    if minutes < 60:
        return f"{minutes} 分 {secs:02d} 秒"
    hours, minutes = divmod(minutes, 60)
    return f"{hours} 小時 {minutes:02d} 分"


def timestamp_text(value: float) -> str:
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(value))
