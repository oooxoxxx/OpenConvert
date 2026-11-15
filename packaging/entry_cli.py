"""PyInstaller 進入點（命令列，保留主控台輸出）。"""

from __future__ import annotations

import sys

from openconvert.cli import main

if __name__ == "__main__":
    sys.exit(main())
