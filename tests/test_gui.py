"""GUI 煙霧測試（offscreen，不需要實體螢幕）。"""

from __future__ import annotations

from pathlib import Path

import pytest

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


def test_convert_page_lists_available_targets(qtbot, tools, png_file: Path, notify):
    settings = Settings()
    queue = ConversionQueue(settings)
    page = ConvertPage(settings, tools, queue, notify)
    qtbot.addWidget(page)

    page.add_paths([png_file])

    tokens = [token for token in page._tokens if token]
    assert "png" in tokens
    assert "jpg" in tokens
    assert "epub" in tokens
    assert page._table.rowCount() == 1
    assert page._start_button.isEnabled()
    assert page._stack.currentIndex() == 1


def test_convert_page_ignores_unsupported_files(qtbot, tools, tmp_path: Path, notify):
    text = tmp_path / "note.txt"
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

    page._target_combo.setCurrentIndex(page._tokens.index("jpg"))
    assert not page._image_quality_spin.isHidden()

    page._target_combo.setCurrentIndex(page._tokens.index("bmp"))
    assert page._image_quality_spin.isHidden()

    page._target_combo.setCurrentIndex(page._tokens.index("webp"))
    assert not page._image_quality_spin.isHidden()


def test_inspect_page_loads_image(qtbot, tools, png_file: Path, notify):
    from openconvert.gui.pages.inspect import InspectPage

    page = InspectPage(tools, notify)
    qtbot.addWidget(page)

    page.load(png_file)

    assert page._stack.currentIndex() == 1
    html = page._viewer.toHtml()
    assert "80" in html and "60" in html
