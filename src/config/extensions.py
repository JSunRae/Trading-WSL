"""Config extension accessors for gap/RVOL scanner & recorder.

Non-breaking: importable even if env vars absent.
"""

from __future__ import annotations

import os
from functools import lru_cache

from src.core.config import get_config

ENV_PREFIX = "GAP_SCANNER_"


@lru_cache(maxsize=1)
def _env(key: str, default: str) -> str:
    return os.getenv(key, default)


def min_gap_pct() -> float:
    try:
        return float(_env(f"{ENV_PREFIX}MIN_GAP_PCT", "4"))
    except ValueError:
        return 4.0


def min_rvol() -> float:
    try:
        return float(_env(f"{ENV_PREFIX}MIN_RVOL", "2"))
    except ValueError:
        return 2.0


def refresh_seconds() -> int:
    try:
        return max(3, int(_env(f"{ENV_PREFIX}REFRESH_SEC", "10")))
    except ValueError:
        return 10


def price_min() -> float:
    return 1.0  # hard constraint


def price_max() -> float:
    return 30.0  # hard constraint


def exchanges() -> list[str]:
    raw = _env(f"{ENV_PREFIX}EXCHANGES", "NYSE,NASDAQ,ARCA")
    return [x.strip().upper() for x in raw.split(",") if x.strip()]


def etf_blacklist_file() -> str | None:
    path = _env(f"{ENV_PREFIX}ETF_BLACKLIST_FILE", "")
    return path or None


def fallback_universe_csv() -> str | None:
    path = _env(f"{ENV_PREFIX}FALLBACK_UNIVERSE_CSV", "")
    return path or None


def data_base_path():  # convenience
    return get_config().data_paths.base_path


def runtime_state_path() -> str:
    return str(data_base_path() / "runtime" / "gap_recorder_state.json")


def hidden_symbols_path() -> str:
    return str(data_base_path() / "runtime" / "gap_hidden_symbols.txt")


def all_settings() -> dict[str, object]:
    return {
        "min_gap_pct": min_gap_pct(),
        "min_rvol": min_rvol(),
        "refresh_seconds": refresh_seconds(),
        "price_min": price_min(),
        "price_max": price_max(),
        "exchanges": exchanges(),
        "etf_blacklist_file": etf_blacklist_file(),
        "fallback_universe_csv": fallback_universe_csv(),
    }
