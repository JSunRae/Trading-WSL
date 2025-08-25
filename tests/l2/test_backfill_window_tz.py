from datetime import date, datetime, time
from zoneinfo import ZoneInfo


def build_window(trading_day: date):
    et = ZoneInfo("America/New_York")
    start = datetime.combine(trading_day, time(8, 0), et)
    end = datetime.combine(trading_day, time(11, 30), et)
    return start, end


def test_dst_and_standard_offsets():
    # Standard time (January)
    jan_day = date(2025, 1, 15)
    start_std, end_std = build_window(jan_day)
    # DST (July)
    jul_day = date(2025, 7, 15)
    start_dst, end_dst = build_window(jul_day)
    assert start_std.tzinfo is not None
    assert start_dst.tzinfo is not None
    # Offsets differ (standard -05:00 vs DST -04:00)
    assert start_std.utcoffset() != start_dst.utcoffset()
    assert end_std > start_std
    assert end_dst > start_dst
