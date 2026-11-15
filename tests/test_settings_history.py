"""設定與紀錄的持久化測試。"""

from __future__ import annotations

import json
from pathlib import Path

from openconvert.core import history
from openconvert.core.settings import Settings, settings_path


def test_settings_roundtrip(tmp_path: Path):
    path = tmp_path / "settings.json"
    settings = Settings(theme="dark", concurrency=4, output_dir=str(tmp_path), overwrite=True)
    settings.save(path)

    loaded = Settings.load(path)

    assert loaded.theme == "dark"
    assert loaded.concurrency == 4
    assert loaded.output_dir == str(tmp_path)
    assert loaded.overwrite is True


def test_settings_defaults_when_file_missing(tmp_path: Path):
    loaded = Settings.load(tmp_path / "missing.json")
    assert loaded.theme == "system"
    assert loaded.concurrency == 2


def test_settings_ignores_corrupted_file(tmp_path: Path):
    path = tmp_path / "settings.json"
    path.write_text("{not json", encoding="utf-8")
    assert Settings.load(path).theme == "system"


def test_settings_unknown_keys_are_ignored(tmp_path: Path):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"theme": "light", "nope": 1}), encoding="utf-8")
    loaded = Settings.load(path)
    assert loaded.theme == "light"


def test_settings_normalizes_out_of_range_values(tmp_path: Path):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"concurrency": 99, "theme": "neon"}), encoding="utf-8")
    loaded = Settings.load(path)
    assert loaded.concurrency == 8
    assert loaded.theme == "system"


def test_settings_uses_env_override(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OPENCONVERT_CONFIG_DIR", str(tmp_path / "cfg"))
    assert settings_path().parent == tmp_path / "cfg"


def test_history_append_and_load(tmp_path: Path):
    path = tmp_path / "history.jsonl"
    for index in range(3):
        history.append_entry(
            history.HistoryEntry(
                timestamp=1000 + index,
                sources=[f"/tmp/file{index}.png"],
                target_label="JPG 圖片",
                status="done",
                outputs=[f"/tmp/out{index}.jpg"],
            ),
            path=path,
        )

    entries = history.load_entries(path=path)
    assert len(entries) == 3
    # 最新的排最前面
    assert entries[0].sources[0].endswith("file2.png")


def test_history_skips_corrupted_lines(tmp_path: Path):
    path = tmp_path / "history.jsonl"
    history.append_entry(
        history.HistoryEntry(timestamp=1, sources=["a"], target_label="X", status="done"),
        path=path,
    )
    with path.open("a", encoding="utf-8") as handle:
        handle.write("this is not json\n")
        handle.write("[1,2,3]\n")
    history.append_entry(
        history.HistoryEntry(timestamp=2, sources=["b"], target_label="Y", status="done"),
        path=path,
    )

    entries = history.load_entries(path=path)
    assert len(entries) == 2


def test_history_clear(tmp_path: Path):
    path = tmp_path / "history.jsonl"
    history.append_entry(
        history.HistoryEntry(timestamp=1, sources=["a"], target_label="X", status="done"),
        path=path,
    )
    history.clear(path=path)
    assert history.load_entries(path=path) == []


def test_history_trim_keeps_latest(tmp_path: Path):
    path = tmp_path / "history.jsonl"
    for index in range(10):
        history.append_entry(
            history.HistoryEntry(timestamp=index, sources=[str(index)], target_label="X", status="done"),
            path=path,
        )
    history.trim(path=path, keep=4)
    entries = history.load_entries(path=path, limit=100)
    assert len(entries) == 4
    assert entries[0].sources == ["9"]
