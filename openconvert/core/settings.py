"""使用者設定的讀寫與持久化。"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

import platformdirs

APP_DIR_NAME = "OpenConvert"

#: 允許的主題值
THEMES = ("system", "dark", "light")

#: 可讓測試或可攜式版本覆寫設定位置
CONFIG_DIR_ENV = "OPENCONVERT_CONFIG_DIR"
DATA_DIR_ENV = "OPENCONVERT_DATA_DIR"


def config_dir() -> Path:
    override = os.environ.get(CONFIG_DIR_ENV)
    if override:
        return Path(override)
    return Path(platformdirs.user_config_dir(APP_DIR_NAME, appauthor=False))


def data_dir() -> Path:
    override = os.environ.get(DATA_DIR_ENV)
    if override:
        return Path(override)
    return Path(platformdirs.user_data_dir(APP_DIR_NAME, appauthor=False))


def settings_path() -> Path:
    return config_dir() / "settings.json"


@dataclass
class Settings:
    """應用程式設定。所有欄位都必須有預設值。"""

    theme: str = "system"
    output_dir: str | None = None
    overwrite: bool = False
    concurrency: int = 2
    ffmpeg_path: str | None = None
    ffprobe_path: str | None = None
    office_path: str | None = None
    keep_history: bool = True
    play_sound: bool = True
    last_format: str = "mp4"
    window_geometry: str | None = None
    last_page: int = 0
    extra: dict = field(default_factory=dict)

    # ------------------------------------------------------------------ 驗證

    def normalized(self) -> Settings:
        """回傳一份經過範圍檢查的副本，避免損壞的設定讓程式崩潰。"""
        data = asdict(self)
        data["theme"] = self.theme if self.theme in THEMES else "system"
        data["concurrency"] = max(1, min(8, int(self.concurrency or 2)))
        for key in ("output_dir", "ffmpeg_path", "ffprobe_path", "office_path"):
            value = data.get(key)
            data[key] = str(value) if value else None
        data["last_page"] = max(0, int(self.last_page or 0))
        data.pop("extra", None)
        return Settings(**data)

    # ------------------------------------------------------------------ 讀寫

    @classmethod
    def load(cls, path: Path | None = None) -> Settings:
        target = Path(path) if path else settings_path()
        if not target.exists():
            return cls()
        try:
            raw = json.loads(target.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return cls()
        if not isinstance(raw, dict):
            return cls()
        known = {f.name for f in fields(cls)}
        payload = {k: v for k, v in raw.items() if k in known and k != "extra"}
        try:
            return cls(**payload).normalized()
        except TypeError:  # pragma: no cover - 型別異常時回退預設值
            return cls()

    def save(self, path: Path | None = None) -> None:
        target = Path(path) if path else settings_path()
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = asdict(self.normalized())
        payload.pop("extra", None)

        # 原子寫入，避免寫到一半斷電造成設定檔損毀
        handle, tmp_name = tempfile.mkstemp(dir=str(target.parent), suffix=".tmp")
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, ensure_ascii=False, indent=2)
            os.replace(tmp_name, target)
        except BaseException:
            Path(tmp_name).unlink(missing_ok=True)
            raise

    # ------------------------------------------------------------------ 便利

    def resolved_output_dir(self) -> Path | None:
        if not self.output_dir:
            return None
        path = Path(self.output_dir)
        return path if path.is_dir() else None
