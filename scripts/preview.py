"""開發用：渲染各頁面截圖，方便檢查版面。

預設使用原生 Qt 平台外掛，但把視窗設為「不顯示於螢幕」（WA_DontShowOnScreen），
因此不會真的彈出視窗，字型也能正常解析。

用法：
    python scripts/preview.py [輸出目錄]
    set OPENCONVERT_PREVIEW_OFFSCREEN=1   # 完全無視窗環境時使用 offscreen
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

if os.environ.get("OPENCONVERT_PREVIEW_OFFSCREEN") == "1":
    os.environ["QT_QPA_PLATFORM"] = "offscreen"

# 不要污染真正的使用者設定
os.environ.setdefault("OPENCONVERT_CONFIG_DIR", tempfile.mkdtemp(prefix="openconvert-preview-"))
os.environ.setdefault("OPENCONVERT_DATA_DIR", tempfile.mkdtemp(prefix="openconvert-preview-data-"))

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtCore import Qt

from openconvert.app import create_application
from openconvert.core.settings import Settings
from openconvert.gui.main_window import MainWindow

PAGES = ("convert", "inspect", "history", "settings", "about")


def main() -> int:
    out_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("preview")
    out_dir.mkdir(parents=True, exist_ok=True)

    app = create_application([])

    for theme_name in ("dark", "light"):
        settings = Settings(theme=theme_name)
        window = MainWindow(settings)
        window.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
        window.resize(1180, 760)
        window.show()
        app.processEvents()

        for index, name in enumerate(PAGES):
            window._navigate(index)
            app.processEvents()
            target = out_dir / f"{theme_name}-{name}.png"
            window.grab().save(str(target))
            print(f"saved {target}")

        if theme_name == "dark":
            _render_filled_view(app, window, out_dir)

        window.close()
        app.processEvents()

    return 0


def _render_filled_view(app, window: MainWindow, out_dir: Path) -> None:
    """加入幾個示範檔案，檢查佇列表格與選項面板的實際樣貌。"""
    from PIL import Image

    folder = Path(tempfile.mkdtemp(prefix="openconvert-demo-"))
    for index in range(3):
        Image.new("RGB", (120, 90), (30 * index, 90, 170)).save(folder / f"photo_{index + 1}.png")

    window._navigate(0)
    window._convert_page.add_paths(sorted(folder.glob("*.png")))
    app.processEvents()

    target = out_dir / "dark-convert-filled.png"
    window.grab().save(str(target))
    print(f"saved {target}")


if __name__ == "__main__":
    raise SystemExit(main())
