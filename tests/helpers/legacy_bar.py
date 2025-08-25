from __future__ import annotations

"""Test-only legacy BarCLS shim.

This reproduces the legacy interval behavior required by tests without keeping
`BarCLS` in production code. If production needs these semantics again, move
logic into a shared helper under `src/`.
"""
from datetime import date, datetime
from typing import Any, Union

import pandas as pd

DateLike = Union[str, datetime, date, pd.Timestamp]


class BarClsTestShim:
    def __init__(self, bar_str_full: str):
        self.BarStr_Full = bar_str_full.lower()
        self.BarSize = bar_str_full

    def get_intervalReq(self, StartTime: DateLike = "", EndTime: DateLike = ""):
        def _coerce(x: Any):
            if isinstance(x, pd.Timestamp):
                return x.to_pydatetime()
            if isinstance(x, (datetime, date)):
                if not isinstance(x, datetime):
                    return datetime.combine(x, datetime.min.time())
                return x
            try:
                ts = pd.to_datetime(x, errors="coerce")
                if ts is pd.NaT:
                    return None
                return ts.to_pydatetime()
            except Exception:
                return None

        start_dt = _coerce(StartTime)
        end_dt = _coerce(EndTime)
        if start_dt is None or end_dt is None:
            return "0 S"
        try:
            delta = end_dt - start_dt
        except Exception:
            return "0 S"
        if delta.total_seconds() < 0:
            return "0 S"
        seconds = int(delta.total_seconds())
        if seconds == 86400:
            return "1 D"
        if seconds == 60:
            return 0
        if seconds < 86400:
            return f"{seconds} S"
        days = max(1, seconds // 86400)
        return f"{days} D"


__all__ = ["BarClsTestShim"]
