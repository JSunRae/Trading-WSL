from __future__ import annotations

from datetime import date, datetime

import pytz

ET = pytz.timezone("America/New_York")


def et_session_window_utc(
    trading_day: date, start_et: str, end_et: str
) -> tuple[datetime, datetime]:
    """Convert ET local session window to UTC, honoring DST for that date.

    start_et/end_et in HH:MM format.
    """
    s_h, s_m = map(int, start_et.split(":", 1))
    e_h, e_m = map(int, end_et.split(":", 1))
    local_start = ET.localize(
        datetime(trading_day.year, trading_day.month, trading_day.day, s_h, s_m)
    )
    local_end = ET.localize(
        datetime(trading_day.year, trading_day.month, trading_day.day, e_h, e_m)
    )
    return local_start.astimezone(pytz.utc), local_end.astimezone(pytz.utc)
