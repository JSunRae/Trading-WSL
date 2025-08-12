"""Type stubs for pandas_market_calendars"""
from datetime import datetime, time
from typing import Any

from pandas import DataFrame, DatetimeIndex

def get_calendar(
    name: str,
    open_time: time | None = None,
    close_time: time | None = None
) -> MarketCalendar: ...

class MarketCalendar:
    def schedule(
        self,
        start_date: datetime | str,
        end_date: datetime | str,
        tz: str = "UTC",
        start: str = "market_open",
        end: str = "market_close",
        force_special_times: bool = True,
        market_times: Any | None = None,
        interruptions: bool = False
    ) -> DataFrame: ...

    def valid_days(
        self,
        start_date: datetime | str,
        end_date: datetime | str,
        tz: str = "UTC"
    ) -> DatetimeIndex: ...

    def is_open_now(
        self,
        schedule: DataFrame | None = None,
        include_close: bool = False,
        only_rth: bool = False
    ) -> bool: ...

class ExchangeCalendar(MarketCalendar): ...
