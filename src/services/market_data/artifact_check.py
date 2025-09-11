"""Unified artifact existence checks for bars and Level 2.

All tools should use these helpers to determine whether data is present.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal, TypedDict

from src.core.config import get_config
from src.services.market_data.l2_paths import with_source_suffix


class NeedResult(TypedDict, total=False):
    hourly: bool
    seconds: bool
    l2: bool
    reason: str
    paths: dict[str, str]


def _bar_path(symbol: str, timeframe: str, date_str: str) -> Path:
    cfg = get_config()
    return cfg.get_data_file_path(
        "ib_download", symbol=symbol, timeframe=timeframe, date_str=date_str
    )


def has_hourly(symbol: str, date_str: str) -> bool:
    return _bar_path(symbol, "1 hour", date_str).exists()


def has_seconds(symbol: str, date_str: str) -> bool:
    return _bar_path(symbol, "1 sec", date_str).exists()


def has_l2(
    symbol: str, date_str: str, source: Literal["databento"] = "databento"
) -> bool:
    cfg = get_config()
    base = cfg.get_data_file_path("level2", symbol=symbol, date_str=date_str)
    return with_source_suffix(base, source).exists() or base.exists()


def compute_needs(symbol: str, date_str: str) -> NeedResult:
    """Return what is needed for this (symbol, date)."""
    cfg = get_config()
    hourly_path = _bar_path(symbol, "1 hour", date_str)
    seconds_path = _bar_path(symbol, "1 sec", date_str)
    l2_base = cfg.get_data_file_path("level2", symbol=symbol, date_str=date_str)
    h = hourly_path.exists()
    s = seconds_path.exists()
    l2 = has_l2(symbol, date_str)
    return {
        "hourly": not h,
        "seconds": not s,
        "l2": not l2,
        "paths": {
            "hourly": str(hourly_path),
            "seconds": str(seconds_path),
            "l2_base": str(l2_base),
        },
    }
