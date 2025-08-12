"""
Market Calendar Service - P0 Critical Architecture Migration
Handles market hours, trading days, and calendar operations.
Extracted from monolithic Market_InfoCLS (200+ lines).
"""

import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import pytz

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    import pandas_market_calendars as mcal

    HAS_MARKET_CAL = True
except ImportError:
    mcal = None
    HAS_MARKET_CAL = False
    print("Note: pandas_market_calendars not available. Using fallback implementation.")

try:
    from src.core.config import get_config
    from src.core.error_handler import get_error_handler
except ImportError as e:
    print(f"Warning: Could not import core modules: {e}")

    def get_error_handler():
        class FallbackErrorHandler:
            def log_info(self, msg):
                print(f"INFO: {msg}")

            def log_warning(self, msg):
                print(f"WARNING: {msg}")

            def log_error(self, msg):
                print(f"ERROR: {msg}")

            def handle_error(self, e, context=None):
                print(f"ERROR: {e}")

        return FallbackErrorHandler()

    def get_config():
        return None


class MarketCalendarService:
    """
    Enterprise-grade market calendar and trading hours management.

    Responsibilities:
    - Market open/close detection
    - Trading day calculations
    - Holiday handling
    - Multi-market support
    - Timezone management
    """

    def __init__(self, market: str = "NYSE", config=None):
        """Initialize market calendar service."""
        self.error_handler = get_error_handler()
        self.config = config or get_config()
        self.market = market.upper()

        # Timezone settings
        self.market_timezone = self._get_market_timezone(self.market)
        self.utc_timezone = pytz.UTC

        # Market calendars (if available)
        self.calendar = None
        if HAS_MARKET_CAL:
            try:
                if mcal:
                    self.calendar = mcal.get_calendar(
                        self._get_market_cal_name(self.market)
                    )
                    self.error_handler.logger.info(
                        f"Initialized market calendar for {self.market}"
                    )
            except Exception as e:
                self.error_handler.logger.warning(
                    f"Could not initialize market calendar: {e}"
                )

        # Fallback market hours (Eastern Time)
        self.default_market_hours = {
            "market_open": "09:30",  # 9:30 AM ET
            "market_close": "16:00",  # 4:00 PM ET
            "pre_market_open": "04:00",  # 4:00 AM ET
            "after_hours_close": "20:00",  # 8:00 PM ET
        }

        # Known holidays (fallback when pandas_market_calendars not available)
        self.static_holidays_2024 = [
            date(2024, 1, 1),  # New Year's Day
            date(2024, 1, 15),  # Martin Luther King Jr. Day
            date(2024, 2, 19),  # Presidents' Day
            date(2024, 3, 29),  # Good Friday
            date(2024, 5, 27),  # Memorial Day
            date(2024, 6, 19),  # Juneteenth
            date(2024, 7, 4),  # Independence Day
            date(2024, 9, 2),  # Labor Day
            date(2024, 11, 28),  # Thanksgiving
            date(2024, 12, 25),  # Christmas
        ]

    def _get_market_timezone(self, market: str) -> pytz.BaseTzInfo:
        """Get the timezone for a market."""
        timezone_map = {
            "NYSE": pytz.timezone("America/New_York"),
            "NASDAQ": pytz.timezone("America/New_York"),
            "LSE": pytz.timezone("Europe/London"),
            "TSX": pytz.timezone("America/Toronto"),
            "ASX": pytz.timezone("Australia/Sydney"),
            "HKEX": pytz.timezone("Asia/Hong_Kong"),
            "JSE": pytz.timezone("Asia/Tokyo"),
        }
        return timezone_map.get(market, pytz.timezone("America/New_York"))

    def _get_market_cal_name(self, market: str) -> str:
        """Get the pandas_market_calendars name for a market."""
        cal_map = {
            "NYSE": "NYSE",
            "NASDAQ": "NASDAQ",
            "LSE": "LSE",
            "TSX": "TSX",
            "ASX": "ASX",
            "HKEX": "HKEX",
            "JPX": "JPX",
        }
        return cal_map.get(market, "NYSE")

    def is_market_open(self, check_time: datetime | None = None) -> bool:
        """
        Check if the market is currently open.

        Args:
            check_time: Time to check (defaults to current time)

        Returns:
            True if market is open, False otherwise
        """
        try:
            if check_time is None:
                check_time = datetime.now(self.market_timezone)
            elif check_time.tzinfo is None:
                check_time = self.market_timezone.localize(check_time)
            else:
                check_time = check_time.astimezone(self.market_timezone)

            # Check if it's a trading day
            if not self.is_trading_day(check_time.date()):
                return False

            # Use pandas_market_calendars if available
            if self.calendar:
                try:
                    schedule = self.calendar.schedule(
                        start_date=check_time.date(), end_date=check_time.date()
                    )

                    if not schedule.empty:
                        market_open = schedule.iloc[0]["market_open"].tz_convert(
                            self.market_timezone
                        )
                        market_close = schedule.iloc[0]["market_close"].tz_convert(
                            self.market_timezone
                        )

                        return market_open <= check_time <= market_close
                    else:
                        return False

                except Exception as e:
                    self.error_handler.logger.warning(
                        f"Market calendar check failed: {e}"
                    )
                    # Fall through to fallback logic

            # Fallback logic using default hours
            market_time = check_time.time()

            open_time = datetime.strptime(
                self.default_market_hours["market_open"], "%H:%M"
            ).time()
            close_time = datetime.strptime(
                self.default_market_hours["market_close"], "%H:%M"
            ).time()

            return open_time <= market_time <= close_time

        except Exception as e:
            self.error_handler.handle_error(e, {"check_time": str(check_time)})
            return False

    def is_trading_day(self, check_date: date | None = None) -> bool:
        """
        Check if a date is a trading day.

        Args:
            check_date: Date to check (defaults to today)

        Returns:
            True if it's a trading day, False otherwise
        """
        try:
            if check_date is None:
                check_date = date.today()

            # Check if it's a weekend
            if check_date.weekday() >= 5:  # Saturday = 5, Sunday = 6
                return False

            # Use pandas_market_calendars if available
            if self.calendar:
                try:
                    valid_days = self.calendar.valid_days(
                        start_date=check_date, end_date=check_date
                    )
                    return len(valid_days) > 0

                except Exception as e:
                    self.error_handler.logger.warning(f"Trading day check failed: {e}")
                    # Fall through to fallback logic

            # Fallback: check against static holidays
            return check_date not in self.static_holidays_2024

        except Exception as e:
            self.error_handler.handle_error(e, {"check_date": str(check_date)})
            return False

    def get_last_trading_day(self, from_date: date | None = None) -> date:
        """
        Get the last trading day before or on the given date.

        Args:
            from_date: Date to search from (defaults to today)

        Returns:
            Last trading day
        """
        try:
            if from_date is None:
                from_date = date.today()

            # Use pandas_market_calendars if available
            if self.calendar:
                try:
                    # Get valid days for the past month
                    start_date = from_date - timedelta(days=30)
                    valid_days = self.calendar.valid_days(
                        start_date=start_date, end_date=from_date
                    )

                    if len(valid_days) > 0:
                        return valid_days[-1].date()

                except Exception as e:
                    self.error_handler.logger.warning(
                        f"Last trading day lookup failed: {e}"
                    )
                    # Fall through to fallback logic

            # Fallback: search backwards day by day
            current_date = from_date
            for _ in range(10):  # Look back up to 10 days
                if self.is_trading_day(current_date):
                    return current_date
                current_date -= timedelta(days=1)

            # If we can't find a trading day, return the original date
            self.error_handler.logger.warning(
                f"Could not find last trading day from {from_date}"
            )
            return from_date

        except Exception as e:
            self.error_handler.handle_error(e, {"from_date": str(from_date)})
            return from_date

    def get_next_trading_day(self, from_date: date | None = None) -> date:
        """
        Get the next trading day after the given date.

        Args:
            from_date: Date to search from (defaults to today)

        Returns:
            Next trading day
        """
        try:
            if from_date is None:
                from_date = date.today()

            # Use pandas_market_calendars if available
            if self.calendar:
                try:
                    # Get valid days for the next month
                    end_date = from_date + timedelta(days=30)
                    valid_days = self.calendar.valid_days(
                        start_date=from_date + timedelta(days=1), end_date=end_date
                    )

                    if len(valid_days) > 0:
                        return valid_days[0].date()

                except Exception as e:
                    self.error_handler.logger.warning(
                        f"Next trading day lookup failed: {e}"
                    )
                    # Fall through to fallback logic

            # Fallback: search forwards day by day
            current_date = from_date + timedelta(days=1)
            for _ in range(10):  # Look ahead up to 10 days
                if self.is_trading_day(current_date):
                    return current_date
                current_date += timedelta(days=1)

            # If we can't find a trading day, return a week from now
            self.error_handler.logger.warning(
                f"Could not find next trading day from {from_date}"
            )
            return from_date + timedelta(days=7)

        except Exception as e:
            self.error_handler.handle_error(e, {"from_date": str(from_date)})
            return from_date + timedelta(days=1)

    def get_trading_days(self, start_date: date, end_date: date) -> list[date]:
        """
        Get all trading days between two dates.

        Args:
            start_date: Start date (inclusive)
            end_date: End date (inclusive)

        Returns:
            List of trading days
        """
        try:
            # Use pandas_market_calendars if available
            if self.calendar:
                try:
                    valid_days = self.calendar.valid_days(
                        start_date=start_date, end_date=end_date
                    )
                    return [day.date() for day in valid_days]

                except Exception as e:
                    self.error_handler.logger.warning(
                        f"Trading days lookup failed: {e}"
                    )
                    # Fall through to fallback logic

            # Fallback: check each day individually
            trading_days = []
            current_date = start_date

            while current_date <= end_date:
                if self.is_trading_day(current_date):
                    trading_days.append(current_date)
                current_date += timedelta(days=1)

            return trading_days

        except Exception as e:
            self.error_handler.handle_error(
                e, {"start_date": str(start_date), "end_date": str(end_date)}
            )
            return []

    def get_market_hours(self, for_date: date | None = None) -> dict[str, Any]:
        """
        Get market hours for a specific date.

        Args:
            for_date: Date to get hours for (defaults to today)

        Returns:
            Dictionary with market hours information
        """
        try:
            if for_date is None:
                for_date = date.today()

            result = {
                "date": for_date,
                "is_trading_day": self.is_trading_day(for_date),
                "market": self.market,
                "timezone": str(self.market_timezone),
            }

            if not result["is_trading_day"]:
                result["reason"] = "Not a trading day"
                return result

            # Use pandas_market_calendars if available
            if self.calendar:
                try:
                    schedule = self.calendar.schedule(
                        start_date=for_date, end_date=for_date
                    )

                    if not schedule.empty:
                        market_open = schedule.iloc[0]["market_open"].tz_convert(
                            self.market_timezone
                        )
                        market_close = schedule.iloc[0]["market_close"].tz_convert(
                            self.market_timezone
                        )

                        result.update(
                            {
                                "market_open": market_open.time(),
                                "market_close": market_close.time(),
                                "hours_source": "pandas_market_calendars",
                            }
                        )
                        return result

                except Exception as e:
                    self.error_handler.logger.warning(
                        f"Market hours lookup failed: {e}"
                    )

            # Fallback to default hours
            result.update(
                {
                    "market_open": datetime.strptime(
                        self.default_market_hours["market_open"], "%H:%M"
                    ).time(),
                    "market_close": datetime.strptime(
                        self.default_market_hours["market_close"], "%H:%M"
                    ).time(),
                    "pre_market_open": datetime.strptime(
                        self.default_market_hours["pre_market_open"], "%H:%M"
                    ).time(),
                    "after_hours_close": datetime.strptime(
                        self.default_market_hours["after_hours_close"], "%H:%M"
                    ).time(),
                    "hours_source": "fallback_default",
                }
            )

            return result

        except Exception as e:
            self.error_handler.handle_error(e, {"for_date": str(for_date)})
            return {"error": str(e)}

    def get_statistics(self) -> dict[str, Any]:
        """Get market calendar service statistics."""
        return {
            "market": self.market,
            "timezone": str(self.market_timezone),
            "has_market_calendars": HAS_MARKET_CAL,
            "calendar_available": self.calendar is not None,
            "current_market_open": self.is_market_open(),
            "today_is_trading_day": self.is_trading_day(),
            "last_trading_day": str(self.get_last_trading_day()),
            "next_trading_day": str(self.get_next_trading_day()),
        }


# Singleton instances for different markets
_market_calendar_instances = {}


def get_market_calendar_service(
    market: str = "NYSE", config=None
) -> MarketCalendarService:
    """Get or create a market calendar service instance for a specific market."""
    global _market_calendar_instances

    market = market.upper()
    if market not in _market_calendar_instances:
        _market_calendar_instances[market] = MarketCalendarService(market, config)

    return _market_calendar_instances[market]


def reset_market_calendar_services():
    """Reset all market calendar service instances (useful for testing)."""
    global _market_calendar_instances
    _market_calendar_instances.clear()


if __name__ == "__main__":
    # Test the market calendar service
    print("📅 Testing Market Calendar Service")

    nyse_cal = MarketCalendarService("NYSE")

    # Test current market status
    print(f"Market open now: {nyse_cal.is_market_open()}")
    print(f"Today is trading day: {nyse_cal.is_trading_day()}")

    # Test trading day calculations
    print(f"Last trading day: {nyse_cal.get_last_trading_day()}")
    print(f"Next trading day: {nyse_cal.get_next_trading_day()}")

    # Test market hours
    hours = nyse_cal.get_market_hours()
    print(f"Market hours: {hours}")

    # Test statistics
    stats = nyse_cal.get_statistics()
    print(f"Statistics: {stats}")

    print("✅ Market Calendar Service test completed")
