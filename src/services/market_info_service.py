"""
Market Info Service

This service handles market calendar information and trading day logic,
extracted from the monolithic MasterPy_Trading.py file.
Provides market schedule, trading days, and market open status.
"""

from datetime import date, datetime, timedelta
from datetime import time as dtime
from typing import Any

try:
    import pandas_market_calendars as market_cal
except ImportError:
    market_cal = None
    print(
        "Note: pandas_market_calendars not available. Market calendar features disabled."
    )

try:
    from ..core.config import get_config
    from ..core.error_handler import get_error_handler

    error_handler = get_error_handler()
    config_manager = get_config()
except ImportError:
    from typing import Any as _Any

    error_handler: _Any | None = None
    config_manager: _Any | None = None


class MarketInfo:
    """Market information and calendar management"""

    def __init__(self, stock_market: str = "NYSE"):
        self.stock_market = stock_market
        self._initialize_calendar()

    def _initialize_calendar(self):
        """Initialize market calendar"""
        if market_cal is None:
            print(
                f"Warning: Market calendar functionality unavailable for {self.stock_market}"
            )
            self.calendar = None
            self.market_schedule = None
        else:
            try:
                self.calendar = market_cal.get_calendar(self.stock_market)
                self.market_schedule = self.calendar.schedule(
                    start_date="2012-07-01", end_date="2030-01-01"
                )
            except Exception as e:
                print(
                    f"Warning: Could not initialize {self.stock_market} calendar: {e}"
                )
                self.calendar = None
                self.market_schedule = None

    def is_market_open(self) -> bool:
        """Check if market is currently open"""
        if self.calendar is None:
            # Fallback: assume market is open during business hours (9 AM - 4 PM ET)
            now = datetime.now().time()
            return dtime(9, 0) <= now <= dtime(16, 0)

        try:
            return self.calendar.is_open_now(self.market_schedule)
        except Exception as e:
            print(f"Warning: Error checking market status: {e}")
            return False

    def get_last_trade_day(self, for_date: datetime | date) -> datetime:
        """Get the last trading day before or on the given date"""
        if self.market_schedule is None:
            # Fallback: return previous weekday
            if isinstance(for_date, date) and not isinstance(for_date, datetime):
                for_date = datetime.combine(for_date, datetime.min.time())

            last_trade_day = for_date
            while last_trade_day.weekday() >= 5:  # Skip weekends
                last_trade_day -= timedelta(days=1)
            return last_trade_day

        try:
            open_dates = self.market_schedule[: for_date.strftime("%Y-%m-%d")]
            if open_dates.empty:
                # No trading days found, use fallback
                if isinstance(for_date, date) and not isinstance(for_date, datetime):
                    for_date = datetime.combine(for_date, datetime.min.time())
                last_trade_day = for_date
                while last_trade_day.weekday() >= 5:
                    last_trade_day -= timedelta(days=1)
                return last_trade_day

            last_trade_datetime = open_dates.iloc[-1]["market_close"]
            return last_trade_datetime.tz_localize(None)
        except Exception as e:
            print(f"Warning: Error getting last trade day: {e}")
            # Fallback
            if isinstance(for_date, date) and not isinstance(for_date, datetime):
                for_date = datetime.combine(for_date, datetime.min.time())
            last_trade_day = for_date
            while last_trade_day.weekday() >= 5:
                last_trade_day -= timedelta(days=1)
            return last_trade_day

    def get_trade_dates(
        self, for_date: datetime | date, bar_config: Any = None, days_wanted: int = 3
    ) -> list[str]:
        """Get list of trading dates"""
        if self.market_schedule is None:
            # Fallback: generate simple date list
            if (
                bar_config
                and hasattr(bar_config, "bar_type")
                and bar_config.bar_type == 2
            ):  # 1 min bars
                dates = []
                current_date = for_date
                for _ in range(days_wanted):
                    # Simple weekday check (skip weekends)
                    while current_date.weekday() >= 5:  # Saturday = 5, Sunday = 6
                        current_date -= timedelta(days=1)
                    dates.append(current_date.strftime("%Y-%m-%d"))
                    current_date -= timedelta(days=1)
                return dates
            else:
                return [for_date.strftime("%Y-%m-%d")]

        try:
            if (
                bar_config
                and hasattr(bar_config, "bar_type")
                and bar_config.bar_type == 2
            ):  # 1 min bars
                open_dates = self.market_schedule[: for_date.strftime("%Y-%m-%d")]
                if len(open_dates) < days_wanted:
                    days_wanted = len(open_dates)

                trade_dates = open_dates[-days_wanted:]["market_close"]
                trade_dates = trade_dates.dt.tz_localize(None).tolist()
                return [td.strftime("%Y-%m-%d") for td in trade_dates]
            else:
                return [for_date.strftime("%Y-%m-%d")]

        except Exception as e:
            print(f"Warning: Error getting trade dates: {e}")
            return [for_date.strftime("%Y-%m-%d")]

    def is_trading_day(self, check_date: datetime | date) -> bool:
        """Check if given date is a trading day"""
        if self.market_schedule is None:
            # Fallback: check if it's a weekday
            return check_date.weekday() < 5

        try:
            date_str = check_date.strftime("%Y-%m-%d")
            # Convert index to string format for comparison
            schedule_dates = [
                d.strftime("%Y-%m-%d") for d in self.market_schedule.index
            ]
            return date_str in schedule_dates
        except Exception as e:
            print(f"Warning: Error checking trading day: {e}")
            return check_date.weekday() < 5

    def get_next_trading_day(self, from_date: datetime | date) -> datetime:
        """Get next trading day after given date"""
        if self.market_schedule is None:
            # Fallback: find next weekday
            if isinstance(from_date, date) and not isinstance(from_date, datetime):
                from_date = datetime.combine(from_date, datetime.min.time())
            next_day = from_date + timedelta(days=1)
            while next_day.weekday() >= 5:
                next_day += timedelta(days=1)
            return next_day

        try:
            future_dates = self.market_schedule[from_date.strftime("%Y-%m-%d") :]
            if len(future_dates) > 1:
                next_trade_datetime = future_dates.iloc[1]["market_open"]
                return next_trade_datetime.tz_localize(None)
            else:
                # Fallback
                if isinstance(from_date, date) and not isinstance(from_date, datetime):
                    from_date = datetime.combine(from_date, datetime.min.time())
                next_day = from_date + timedelta(days=1)
                while next_day.weekday() >= 5:
                    next_day += timedelta(days=1)
                return next_day
        except Exception as e:
            print(f"Warning: Error getting next trading day: {e}")
            if isinstance(from_date, date) and not isinstance(from_date, datetime):
                from_date = datetime.combine(from_date, datetime.min.time())
            next_day = from_date + timedelta(days=1)
            while next_day.weekday() >= 5:
                next_day += timedelta(days=1)
            return next_day

    def get_market_hours(self, for_date: datetime | date) -> tuple | None:
        """Get market open and close times for given date"""
        if self.market_schedule is None:
            # Fallback: standard NYSE hours (9:30 AM - 4:00 PM ET)
            market_open = datetime.combine(
                for_date, datetime.min.time().replace(hour=9, minute=30)
            )
            market_close = datetime.combine(
                for_date, datetime.min.time().replace(hour=16, minute=0)
            )
            return (market_open, market_close)

        try:
            date_str = for_date.strftime("%Y-%m-%d")
            # Check if date exists in schedule
            try:
                day_schedule = self.market_schedule.loc[date_str]
                market_open = day_schedule["market_open"].tz_localize(None)
                market_close = day_schedule["market_close"].tz_localize(None)
                return (market_open, market_close)
            except KeyError:
                return None
        except Exception as e:
            print(f"Warning: Error getting market hours: {e}")
            return None

    def get_market_summary(self) -> dict:
        """Get summary of market information"""
        return {
            "market": self.stock_market,
            "calendar_available": self.calendar is not None,
            "schedule_available": self.market_schedule is not None,
            "currently_open": self.is_market_open(),
            "schedule_range": {
                "start": "2012-07-01" if self.market_schedule is not None else None,
                "end": "2030-01-01" if self.market_schedule is not None else None,
            },
        }


class MarketInfoService:
    """Service for managing market information"""

    def __init__(self):
        self.config = config_manager
        self._market_cache: dict[str, MarketInfo] = {}

    def get_market_info(self, stock_market: str = "NYSE") -> MarketInfo:
        """Get or create market info instance"""
        if stock_market not in self._market_cache:
            self._market_cache[stock_market] = MarketInfo(stock_market)
        return self._market_cache[stock_market]

    def get_supported_markets(self) -> list[str]:
        """Get list of supported markets"""
        if market_cal is None:
            return ["NYSE"]  # Fallback

        try:
            return market_cal.get_calendar_names()
        except Exception as e:
            print(f"Warning: Could not get market list: {e}")
            return ["NYSE", "NASDAQ", "LSE", "TSX", "ASX"]

    def is_any_market_open(self, markets: list[str] | None = None) -> bool:
        """Check if any of the specified markets are open"""
        if markets is None:
            markets = ["NYSE", "NASDAQ"]

        for market in markets:
            market_info = self.get_market_info(market)
            if market_info.is_market_open():
                return True
        return False

    def get_global_trading_status(self) -> dict[str, dict[str, Any]]:
        """Get trading status for major markets"""
        major_markets = ["NYSE", "NASDAQ", "LSE", "TSX", "ASX"]
        status: dict[str, dict[str, Any]] = {}

        for market in major_markets:
            try:
                market_info = self.get_market_info(market)
                status[market] = {
                    "is_open": market_info.is_market_open(),
                    "calendar_available": market_info.calendar is not None,
                }
            except Exception as e:
                status[market] = {"is_open": False, "error": str(e)}

        return status


# Factory functions for backward compatibility
def create_market_info_cls(stock_market: str = "NYSE") -> MarketInfo:
    """Factory function to create Market_InfoCLS equivalent (backward compatibility)"""
    service = MarketInfoService()
    return service.get_market_info(stock_market)


# Singleton service instance
_market_service = None


def get_market_service() -> MarketInfoService:
    """Get singleton market info service"""
    global _market_service
    if _market_service is None:
        _market_service = MarketInfoService()
    return _market_service
