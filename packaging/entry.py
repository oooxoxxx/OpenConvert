"""PyInstaller 進入點（GUI 模式，不開主控台視窗）。"""

from __future__ import annotations

import sys

from openconvert.app import main

if __name__ == "__main__":
    sys.exit(main())
