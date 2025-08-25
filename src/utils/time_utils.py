"""Centralized US/Eastern time utilities for gap/RVOL scanner.

Keeps all trading session time calculations consistent to avoid drift bugs.
"""

from __future__ import annotations

from datetime import datetime, time
from zoneinfo import ZoneInfo

US_EASTERN = ZoneInfo("US/Eastern")

RTH_OPEN_ET = time(9, 30)
RTH_CLOSE_ET = time(16, 0)
TRADING_DAY_MINUTES = 390  # 6.5 hours


def now_eastern() -> datetime:
    return datetime.now(US_EASTERN)


def today_open_dt() -> datetime:
    n = now_eastern()
    return datetime.combine(n.date(), RTH_OPEN_ET, US_EASTERN)


def today_close_dt() -> datetime:
    n = now_eastern()
    return datetime.combine(n.date(), RTH_CLOSE_ET, US_EASTERN)


def is_premarket(ts: datetime | None = None) -> bool:
    ts = ts or now_eastern()
    return ts.time() < RTH_OPEN_ET


def elapsed_session_minutes(ts: datetime | None = None) -> float:
    ts = ts or now_eastern()
    if ts.time() < RTH_OPEN_ET:
        return 0.0
    open_dt = today_open_dt()
    if ts >= today_close_dt():
        return TRADING_DAY_MINUTES
    delta = ts - open_dt
    return max(0.0, delta.total_seconds() / 60.0)


def normalized_time_fraction(ts: datetime | None = None) -> float:
    """Return clamped fraction of session elapsed in [0.1, 1.0].

    Pre-market returns 0.1 floor to avoid huge RVOL early spikes.
    """
    minutes = elapsed_session_minutes(ts)
    frac = minutes / TRADING_DAY_MINUTES if TRADING_DAY_MINUTES else 0.0
    return min(1.0, max(0.1, frac if minutes > 0 else 0.1))


def format_ts(ts: datetime | None) -> str:
    if not ts:
        return ""
    return ts.astimezone(US_EASTERN).strftime("%H:%M:%S")
