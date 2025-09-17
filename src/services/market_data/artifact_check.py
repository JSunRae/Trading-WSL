"""Unified artifact existence checks for bars and Level 2.

All tools should use these helpers to determine whether data is present.

Adds a lightweight gap-computation API for IB bars using the compact
``bars_coverage_manifest.json`` generated from the append-only manifest.
"""

from __future__ import annotations

import json
from datetime import datetime
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


class GapInterval(TypedDict):
    start: str
    end: str


class BarsGapResult(TypedDict, total=False):
    symbol: str
    date: str
    bar_size: str
    needed: bool
    basis: Literal["coverage", "fs-only", "none"]
    target_window: dict[str, str]
    covered: list[GapInterval]
    gaps: list[GapInterval]
    path: str


class CoverageDay(TypedDict, total=False):
    date: str
    time_start: str | None
    time_end: str | None
    path: str
    filename: str
    rows: int


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


def _policy_target_window(date_str: str, bar_size: str) -> tuple[str, str]:
    """Return ISO-like start/end strings for the desired coverage window.

    We keep times ET-relative by convention; consumers should not assume tz.
    - 1 sec: 09:00–11:00
    - 1 min: 09:30–11:00 (same-day minimum; files may include prev-day lookback)
    - 1 hour: 09:30–16:00 (RTH)
    """
    b = bar_size.strip().lower()
    if b in ("1 sec", "1 secs", "seconds", "sec"):
        return f"{date_str}T09:00:00", f"{date_str}T11:00:00"
    if b in ("1 min", "1 mins", "minute", "minutes"):
        return f"{date_str}T09:30:00", f"{date_str}T11:00:00"
    if b in ("1 hour", "hour", "hours"):
        return f"{date_str}T09:30:00", f"{date_str}T16:00:00"
    # Default conservative same as minutes
    return f"{date_str}T09:30:00", f"{date_str}T11:00:00"


def _clip_to_day(
    start_iso: str | None, end_iso: str | None, date_str: str
) -> tuple[str, str] | None:
    """Clip a covered interval to the given date. Returns None if unusable."""
    if not start_iso or not end_iso:
        return None
    try:
        # Accept both naive and offset-aware strings
        def _parse(x: str) -> datetime:
            try:
                return datetime.fromisoformat(x)
            except Exception:
                # Best-effort fallback: strip timezone suffixes like 'Z'
                return datetime.fromisoformat(x.rstrip("Z"))

        s = _parse(start_iso)
        e = _parse(end_iso)
        day_start = datetime.fromisoformat(f"{date_str}T00:00:00")
        day_end = datetime.fromisoformat(f"{date_str}T23:59:59.999999")
        s2 = max(s, day_start)
        e2 = min(e, day_end)
        if e2 <= s2:
            return None
        return s2.isoformat(), e2.isoformat()
    except Exception:
        return None


def _subtract_interval(
    target: tuple[str, str], covered: tuple[str, str] | None
) -> list[GapInterval]:
    """Return the missing sub-intervals (0, 1, or 2) of target minus covered.

    Inputs are ISO-like strings; comparison is lexicographic-safe since they have
    the same date and fixed-width formatting.
    """
    t0, t1 = target
    if covered is None:
        return [{"start": t0, "end": t1}]
    c0, c1 = covered
    if c1 <= t0 or c0 >= t1:
        return [{"start": t0, "end": t1}]
    gaps: list[GapInterval] = []
    if c0 > t0:
        gaps.append({"start": t0, "end": c0})
    if c1 < t1:
        gaps.append({"start": c1, "end": t1})
    return gaps


def _find_coverage_day(
    coverage_path: Path, symbol: str, bar_size: str, date_str: str
) -> CoverageDay | None:
    """Return day object from coverage manifest for symbol/size/date, if any."""
    if not coverage_path.exists():
        return None
    data = json.loads(coverage_path.read_text())
    sym_u = symbol.upper()
    for entry in data.get("entries", []):
        if str(entry.get("symbol", "")).upper() != sym_u:
            continue
        if str(entry.get("bar_size", "")) != bar_size:
            continue
        for day in entry.get("days", []):
            if str(day.get("date")) == date_str:
                return day  # type: ignore[return-value]
    return None


def _fs_has_bar_size(symbol: str, date_str: str, bar_size: str) -> bool:
    b = bar_size.strip().lower()
    if b in ("1 hour", "hour", "hours"):
        return _bar_path(symbol, "1 hour", date_str).exists()
    if b in ("1 sec", "1 secs", "seconds", "sec"):
        return _bar_path(symbol, "1 sec", date_str).exists()
    return _bar_path(symbol, "1 min", date_str).exists()


def compute_bars_gaps(symbol: str, date_str: str, bar_size: str) -> BarsGapResult:  # noqa: C901
    """Compute desired vs covered intervals for bars and return gap details.

    This uses the compact coverage manifest when available; otherwise it falls
    back to filesystem presence checks and returns a coarse answer.
    """
    cfg = get_config()
    base = cfg.data_paths.base_path
    coverage_path = base / "bars_coverage_manifest.json"
    target0, target1 = _policy_target_window(date_str, bar_size)
    result: BarsGapResult = {
        "symbol": symbol.upper(),
        "date": date_str,
        "bar_size": bar_size,
        "needed": True,
        "basis": "none",
        "target_window": {"start": target0, "end": target1},
        "covered": [],
        "gaps": [{"start": target0, "end": target1}],
    }

    # Preferred: use coverage manifest
    try:
        day = _find_coverage_day(coverage_path, symbol, bar_size, date_str)
        if day is not None:
            covered = _clip_to_day(day.get("time_start"), day.get("time_end"), date_str)
            result["basis"] = "coverage"
            if covered is None:
                # treat as no coverage
                result["covered"] = []
                result["gaps"] = [{"start": target0, "end": target1}]
                result["needed"] = True
                result["path"] = str(day.get("path") or "")
                return result
            result["covered"] = [{"start": covered[0], "end": covered[1]}]
            result["gaps"] = _subtract_interval((target0, target1), covered)
            result["needed"] = len(result["gaps"]) > 0
            result["path"] = str(day.get("path") or "")
            return result
        # No matching day found in coverage
        result["basis"] = "coverage"
        result["needed"] = True
        result["gaps"] = [{"start": target0, "end": target1}]
        return result
    except Exception:
        # Fall through to fs-only
        pass

    # Fallback: filesystem existence for coarse signal
    try:
        exists = _fs_has_bar_size(symbol, date_str, bar_size)
        result["basis"] = "fs-only"
        result["needed"] = not exists
        result["gaps"] = [] if exists else [{"start": target0, "end": target1}]
        if exists:
            # We don't know exact coverage; provide a coarse marker
            result["covered"] = [{"start": target0, "end": target1}]
        return result
    except Exception:
        # Keep conservative default
        return result
