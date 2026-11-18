"""資源路徑解析。

同時支援「從原始碼執行」與「PyInstaller 打包後執行」兩種情境。
"""

from __future__ import annotations

import sys
from pathlib import Path


def is_frozen() -> bool:
    """是否在 PyInstaller 產生的執行檔中執行。"""
    return bool(getattr(sys, "frozen", False))


def bundle_dir() -> Path:
    """唯讀資源所在目錄（打包後為 ``sys._MEIPASS``）。"""
    if is_frozen():
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            return Path(meipass)
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def app_dir() -> Path:
    """應用程式所在目錄（可寫資源、隨附工具放這裡）。

    打包後是執行檔所在目錄（``dist/OpenConvert/``）；從原始碼執行時是
    專案根目錄，這樣 ``tools/`` 的位置在兩種情境下語意一致。
    """
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def tools_dir() -> Path:
    """舊版引擎位置（0.4.0 相容；使用者也可以手動放執行檔）。"""
    return app_dir() / "tools"


def modules_dir() -> Path:
    """引擎模組目錄（0.5.0 起）：程式旁的 ``modules/``，內容視為暫存、可隨時刪除重下。"""
    return app_dir() / "modules"


def user_modules_dir() -> Path:
    """使用者層級的引擎模組目錄（程式目錄不可寫時的備援）。"""
    from .settings import data_dir

    return data_dir() / "engines"


def module_search_dirs() -> tuple[Path, ...]:
    """模組可能被安裝的位置，順序即優先順序。"""
    return (modules_dir(), tools_dir(), user_modules_dir())


def find_asset(*parts: str) -> Path | None:
    for base in (bundle_dir(), app_dir()):
        candidate = base.joinpath(*parts)
        if candidate.exists():
            return candidate
    return None
