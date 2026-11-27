"""GUI 煙霧測試（offscreen，不需要實體螢幕）。"""

from __future__ import annotations

from pathlib import Path

import pytest

from openconvert.core.job import JobStatus
from openconvert.core.settings import Settings
from openconvert.gui.pages.convert import ConvertPage
from openconvert.runner import ConversionQueue


@pytest.fixture
def notify():
    calls: list[tuple[str, str]] = []

    def _notify(message: str, kind: str = "info") -> None:
        calls.append((message, kind))

    _notify.calls = calls  # type: ignore[attr-defined]
    return _notify


@pytest.fixture
def window(qtbot, tools):
    from openconvert.gui.main_window import MainWindow

    settings = Settings(theme="dark")
    main = MainWindow(settings)
    qtbot.addWidget(main)
    return main


def test_main_window_has_all_pages(window):
    assert window._stack.count() == 5
    assert len(window._sidebar.buttons) == 5


def test_navigation_switches_pages(window):
    window._navigate(3)
    assert window._stack.currentIndex() == 3
    window._navigate(0)
    assert window._stack.currentIndex() == 0


def test_theme_toggle_switches_between_dark_and_light(window):
    assert window._settings.theme == "dark"
    window._toggle_theme()
    assert window._settings.theme == "light"
    window._toggle_theme()
    assert window._settings.theme == "dark"


@pytest.fixture
def clip_pair(tools, tmp_path: Path) -> list[Path]:
    if not tools.available:
        pytest.skip("系統沒有 FFmpeg")
    import subprocess

    paths = []
    for name in ("c1.mp4", "c2.mp4"):
        path = tmp_path / name
        subprocess.run(
            [
                str(tools.ffmpeg),
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-f",
                "lavfi",
                "-i",
                "testsrc=duration=0.4:size=160x120:rate=10",
                "-c:v",
                "libx264",
                "-preset",
                "ultrafast",
                "-pix_fmt",
                "yuv420p",
                str(path),
            ],
            check=True,
        )
        paths.append(path)
    return paths


def test_convert_page_lists_available_targets(qtbot, tools, png_file: Path, notify):
    settings = Settings()
    queue = ConversionQueue(settings)
    page = ConvertPage(settings, tools, queue, notify)
    qtbot.addWidget(page)

    page.add_paths([png_file])

    # 加入圖片後，類別應自動切到「圖片」，清單只列該類別
    tokens = [token for token in page._tokens if token]
    assert "png" in tokens
    assert "jpg" in tokens
    assert "epub" not in tokens
    assert page._table.rowCount() == 1
    assert page._start_button.isEnabled()
    assert page._stack.currentIndex() == 1

    # 切到「全部類別」後就能看到其他類別的格式
    index = page._category_combo.findData(None)
    page._category_combo.setCurrentIndex(index)
    tokens = [token for token in page._tokens if token]
    assert "epub" in tokens
    assert "video-merge" in tokens


def test_convert_page_search_filters_formats(qtbot, tools, png_file: Path, notify):
    settings = Settings()
    queue = ConversionQueue(settings)
    page = ConvertPage(settings, tools, queue, notify)
    qtbot.addWidget(page)

    page.add_paths([png_file])
    page._category_combo.setCurrentIndex(page._category_combo.findData(None))
    page._search_edit.setText("pdf")

    tokens = [token for token in page._tokens if token]
    assert tokens and all("pdf" in token for token in tokens)
    assert "img-pdf" in tokens


def test_convert_page_ignores_unsupported_files(qtbot, tools, tmp_path: Path, notify):
    text = tmp_path / "note.xyz"
    text.write_text("hello", encoding="utf-8")

    settings = Settings()
    queue = ConversionQueue(settings)
    page = ConvertPage(settings, tools, queue, notify)
    qtbot.addWidget(page)

    page.add_paths([text])

    assert page._table.rowCount() == 0
    assert page._stack.currentIndex() == 0
    assert not page._start_button.isEnabled()


def test_convert_page_runs_real_conversion(qtbot, tools, png_file: Path, tmp_path: Path, notify):
    out = tmp_path / "gui-out"
    settings = Settings(output_dir=str(out))
    queue = ConversionQueue(settings)
    page = ConvertPage(settings, tools, queue, notify)
    qtbot.addWidget(page)

    page.add_paths([png_file])
    page._target_combo.setCurrentIndex(page._tokens.index("jpg"))

    with qtbot.waitSignal(queue.all_finished, timeout=30000):
        page._start()

    assert (out / "sample.jpg").exists()
    assert page._jobs[0].status.value == "done"
    assert page._start_button.text() == "開始轉換"
    assert not page.has_running_jobs


def test_clear_removes_everything(qtbot, tools, png_file: Path, notify):
    settings = Settings()
    queue = ConversionQueue(settings)
    page = ConvertPage(settings, tools, queue, notify)
    qtbot.addWidget(page)

    page.add_paths([png_file])
    page._clear_all()

    assert page._table.rowCount() == 0
    assert page._stack.currentIndex() == 0


def test_convert_page_default_target_differs_from_source(qtbot, tools, png_file: Path, notify):
    settings = Settings()
    queue = ConversionQueue(settings)
    page = ConvertPage(settings, tools, queue, notify)
    qtbot.addWidget(page)

    page.add_paths([png_file])

    assert page._current_token() != "png"
    assert page._current_token() == "jpg"


def test_image_quality_option_only_for_lossy_formats(qtbot, tools, png_file: Path, notify):
    settings = Settings()
    queue = ConversionQueue(settings)
    page = ConvertPage(settings, tools, queue, notify)
    qtbot.addWidget(page)

    page.add_paths([png_file])

    page._select_format_token("jpg")
    assert "image_quality" in page._option_widgets

    page._select_format_token("bmp")
    assert "image_quality" not in page._option_widgets

    page._select_format_token("webp")
    assert "image_quality" in page._option_widgets


def test_per_file_target_override(qtbot, tools, png_file: Path, tmp_path: Path, notify):
    from openconvert.core.job import JobStatus

    out = tmp_path / "gui-out"
    settings = Settings(output_dir=str(out))
    queue = ConversionQueue(settings)
    page = ConvertPage(settings, tools, queue, notify)
    qtbot.addWidget(page)

    from PIL import Image

    second = tmp_path / "second.png"
    Image.new("RGB", (40, 30), (0, 200, 0)).save(second)
    page.add_paths([png_file, second])

    # 兩個工作都跟隨全域（JPEG）
    assert all(job.target.token == "jpg" for job in page._jobs)

    # 第一個工作改成 WebP → 只有它變，另一個維持 JPEG
    page._on_job_target_changed(page._jobs[0].id, "webp")
    tokens = {job.target.token for job in page._jobs}
    assert tokens == {"webp", "jpg"}

    with qtbot.waitSignal(queue.all_finished, timeout=30000):
        page._start()

    assert (out / "sample.webp").exists()
    assert (out / "second.jpg").exists()
    statuses = {job.status for job in page._jobs}
    assert statuses == {JobStatus.DONE}


def test_group_target_skip_shows_reason(qtbot, tools, clip_pair: list[Path], notify):
    settings = Settings()
    queue = ConversionQueue(settings)
    page = ConvertPage(settings, tools, queue, notify)
    qtbot.addWidget(page)

    # 只有一個影片卻選「合併影片」→ 應標示略過並說明原因
    page.add_paths([clip_pair[0]])
    page._on_job_target_changed(page._jobs[0].id, "video-merge")

    assert len(page._jobs) == 1
    assert page._jobs[0].status is JobStatus.SKIPPED
    assert "至少" in (page._jobs[0].message or "")


def test_inspect_page_loads_image(qtbot, tools, png_file: Path, notify):
    from openconvert.gui.pages.inspect import InspectPage

    page = InspectPage(tools, notify)
    qtbot.addWidget(page)

    page.load(png_file)

    assert page._stack.currentIndex() == 1
    html = page._viewer.toHtml()
    assert "80" in html and "60" in html


def test_job_table_drag_order_updates_jobs_and_files(qtbot, tools, png_file: Path, tmp_path: Path, notify):
    from PIL import Image
    from PySide6.QtWidgets import QAbstractItemView

    second = tmp_path / "second.png"
    third = tmp_path / "third.png"
    Image.new("RGB", (20, 20), "green").save(second)
    Image.new("RGB", (20, 20), "blue").save(third)

    page = ConvertPage(Settings(), tools, ConversionQueue(Settings()), notify)
    qtbot.addWidget(page)
    page.add_paths([png_file, second, third])

    first, second_id, third_id = [job.id for job in page._jobs]
    assert page._table.dragDropMode() == QAbstractItemView.DragDropMode.InternalMove
    order = page._table._order_after_drop([first], 3)
    assert order == [second_id, third_id, first]

    page._table.orderChanged.emit(order)
    assert [job.id for job in page._jobs] == order
    assert page._table.job_ids() == order
    assert page._files == [second, third, png_file]

    page._move_job(first, -1)
    assert page._files == [second, png_file, third]


def test_pdf_split_option_is_exposed(qtbot, tools, pdf_file: Path, notify):
    page = ConvertPage(Settings(), tools, ConversionQueue(Settings()), notify)
    qtbot.addWidget(page)
    page.add_paths([pdf_file])
    page._select_format_token("pdf-split")

    assert "split_pages" in page._option_widgets
    page._option_widgets["split_pages"].setValue(3)
    assert page._collect_options()["split_pages"] == 3


def test_filename_template_reaches_job_options(qtbot, tools, png_file: Path, notify):
    settings = Settings(filename_template="{name}_{index}.{ext}")
    page = ConvertPage(settings, tools, ConversionQueue(settings), notify)
    qtbot.addWidget(page)
    page.add_paths([png_file])

    assert page._collect_options()["filename_template"] == "{name}_{index}.{ext}"
    assert page._jobs[0].options["filename_template"] == "{name}_{index}.{ext}"


def test_history_search_filters_and_selects_visible_entry(qtbot, monkeypatch, notify):
    from openconvert.core import history
    from openconvert.gui.pages.history import HistoryPage

    entries = [
        history.HistoryEntry(2, ["C:/tmp/video.mp4"], "MP4 影片", "done"),
        history.HistoryEntry(1, ["C:/tmp/report.xml"], "轉成 JSON", "done"),
    ]
    monkeypatch.setattr(history, "load_entries", lambda limit: entries)
    page = HistoryPage(notify)
    qtbot.addWidget(page)

    page._search_edit.setText("REPORT")
    assert page._table.rowCount() == 1
    assert page._table.item(0, 1).text() == "report.xml"
    page._table.selectRow(0)
    assert page._selected_entry() is entries[1]

    page._search_edit.setText("沒有這個檔案")
    assert page._table.rowCount() == 0
    assert page._table.isHidden()
    assert not page._empty.isHidden()
