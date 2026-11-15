"""GUI 套件。"""

from __future__ import annotations

__all__ = ["MainWindow"]


def __getattr__(name: str):
    # 延遲匯入，讓 `import openconvert` 不需要 GUI 相依
    if name == "MainWindow":
        from .main_window import MainWindow

        return MainWindow
    raise AttributeError(name)
