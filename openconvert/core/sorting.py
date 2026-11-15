"""檔名自然排序。"""

from __future__ import annotations

import re

_NUMBER = re.compile(r"(\d+)")


def natural_key(name: str) -> tuple:
    """讓 ``page2`` 排在 ``page10`` 之前。"""
    parts = _NUMBER.split(name.lower())
    return tuple(int(part) if part.isdigit() else part for part in parts)


__all__ = ["natural_key"]
