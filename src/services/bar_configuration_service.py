"""
Bar Configuration Service

This service handles all bar/timeframe configuration logic,
extracted from the monolithic MasterPy_Trading.py file.
Provides factory methods for creating bar configurations
with proper domain separation.
"""

from typing import Any

import pandas as pd

try:
    from ..core.config import get_config
    from ..core.error_handler import get_error_handler

    error_handler = get_error_handler()
    config_manager = get_config()
except ImportError:
    # Fallback imports for transition period
    try:
        from src.core.config import get_config
        from src.core.error_handler import get_error_handler

        error_handler = get_error_handler()
        config_manager = get_config()
    except ImportError:
        # Ultimate fallback during decomposition
        error_handler = None
        config_manager = None


def handle_error(module: str, message: str, duration: int = 60) -> None:
    """Fallback error handling for transition period"""
    if error_handler:
        try:
            from ..core.error_handler import TradingSystemError

            error = TradingSystemError(message)
            error_handler.handle_error(error, {"module": module, "duration": duration})
        except Exception:
            print(f"ERROR [{module}]: {message}")
    else:
        print(f"ERROR [{module}]: {message}")


class BarConfiguration:
    """Domain model for bar configuration settings"""

    def __init__(self, bar_str_full: str):
        self.bar_str_full = bar_str_full.lower()
        self.bar_size = bar_str_full  # Store original for compatibility
        self._initialize_configuration()

    def _initialize_configuration(self):
        """Initialize all bar configuration parameters"""
        if " " in self.bar_str_full:
            self.bar_period = int(self.bar_str_full.split(" ")[0])
        else:
            self.bar_period = 1

        # Configure based on bar type
        if "tick" in self.bar_str_full:
            self._configure_tick_bars()
        elif "sec" in self.bar_str_full:
            self._configure_second_bars()
        elif "min" in self.bar_str_full:
            self._configure_minute_bars()
        elif "hour" in self.bar_str_full:
            self._configure_hour_bars()
        elif "day" in self.bar_str_full:
            self._configure_day_bars()
        else:
            handle_error(__name__, f"Bar Size not correct: {self.bar_str_full}")

    def _configure_tick_bars(self):
        """Configure tick bar parameters"""
        self.bar_type = 0
        self.bar_name = "ticks"
        self.bar_str = "_Tick"
        self.interval_max_allowed = 1000
        self.bars_req = 1000
        self.multiple_days = False
        self.merge_ask_bid_trades = False

        self.columns_dl = [
            "idx",
            "time",
            "tickAttribLast",
            "price",
            "size",
            "exchange",
            "specialConditions",
        ]
        self.special_conditions_reference = (
            "https://www.interactivebrokers.com/en/index.php?f=7235"
        )
        self.cols_req = [
            "idx",
            "time",
            "tickAttribLast",
            "price",
            "size",
            "exchange",
            "specialConditions",
        ]
        self.cols_del = ["idx", "tickAttribLast", "exchange", "specialConditions"]
        self.cols_volumes = ["size"]
        self.cols_prices = ["price"]
        self.macd_timeframe = ""  # No EMA for ticks

    def _configure_second_bars(self):
        """Configure second bar parameters"""
        self.bar_type = 1
        self.bar_name = "seconds"
        self.bar_str = "_1s"
        self.interval_max_allowed = 2000
        self.merge_ask_bid_trades = True
        self.bars_req = 60 * 30  # 30min worth

        self.delta_letter = "s"
        self.duration_letter = " S"
        self.interval_mfactor = 1
        self.multiple_days = False

        self._setup_ask_bid_trades_columns()
        self.macd_timeframe = 5 * 60  # '5T'
        self.ema_list = [
            (20, "1min", 60),
            (9, "5min", 5 * 60),
            (20, "5min", 5 * 60),
        ]

    def _configure_minute_bars(self):
        """Configure minute bar parameters"""
        if self.bar_period == 1:
            self._configure_1min_bars()
        elif self.bar_period == 30:
            self._configure_30min_bars()
        else:
            handle_error(
                __name__, "Not setup for periods other than 1 or 30 for minutes"
            )

    def _configure_1min_bars(self):
        """Configure 1-minute bar parameters"""
        self.bar_type = 2
        self.bar_name = "minutes"
        self.bar_str = "_1m"
        self.interval_max_allowed = 2000
        self.merge_ask_bid_trades = True
        self.bars_req = 60 * 8  # 1 trading day

        self.delta_letter = "m"
        self.duration_letter = " S"
        self.interval_mfactor = 60
        self.multiple_days = False

        self._setup_ask_bid_trades_columns()
        self.macd_timeframe = 5  # '5T'
        self.ema_list = [
            (20, "1min", 1),
            (9, "5min", 1),
            (20, "5min", 1),
            (200, "5min", 1),
        ]

    def _configure_30min_bars(self):
        """Configure 30-minute bar parameters"""
        self.bar_type = 3
        self.bar_name = "minutes"
        self.bar_str = "_30m"
        self.interval_max_allowed = 2000
        self.merge_ask_bid_trades = False
        self.bars_req = 5000

        self.delta_letter = "h"
        self.duration_letter = " D"
        self.interval_mfactor = 1 / (2 * 24)
        self.multiple_days = True

        self._setup_ohlc_columns()
        self.macd_timeframe = 2  # '2h'
        self.ema_list = [
            (9, "1day", 2 * 24),
            (20, "1day", 2 * 24),
            (200, "1day", 2 * 24),
        ]

    def _configure_hour_bars(self):
        """Configure hour bar parameters"""
        self.bar_type = 4
        self.bar_name = "hours"
        self.bar_str = "_1h"
        self.interval_max_allowed = 2000
        self.merge_ask_bid_trades = False
        self.bars_req = 2500

        self.delta_letter = "h"
        self.duration_letter = " D"
        self.interval_mfactor = 1 / 24
        self.multiple_days = True

        self._setup_ohlc_columns()
        self.macd_timeframe = 1  # 'H'
        self.ema_list = [
            (9, "1day", 24),
            (20, "1day", 24),
            (200, "1day", 24),
        ]

    def _configure_day_bars(self):
        """Configure day bar parameters"""
        self.bar_type = 5
        self.bar_name = "days"
        self.bar_str = "_1d"
        self.interval_max_allowed = 2000
        self.merge_ask_bid_trades = False
        self.bars_req = 10 * 365  # 10 years

        self.delta_letter = "D"
        self.duration_letter = " D"
        self.interval_mfactor = 1
        self.multiple_days = True

        self._setup_ohlc_columns()
        self.macd_timeframe = 1  # 'd'
        self.ema_list = [(200, "1day", 1)]

    def _setup_ask_bid_trades_columns(self):
        """Setup columns for ask/bid/trades data"""
        self.columns_dl = [
            "date",
            "ASK_open",
            "ASK_high",
            "ASK_low",
            "ASK_close",
            "ASK_volume",
            "ASK_average",
            "ASK_barCount",
            "BID_open",
            "BID_high",
            "BID_low",
            "BID_close",
            "BID_volume",
            "BID_average",
            "BID_barCount",
            "TRADES_open",
            "TRADES_high",
            "TRADES_low",
            "TRADES_close",
            "TRADES_volume",
            "TRADES_average",
            "TRADES_barCount",
        ]

        self.cols_req = [
            "date",
            "ASK_open",
            "ASK_high",
            "ASK_low",
            "ASK_close",
            "BID_open",
            "BID_high",
            "BID_low",
            "BID_close",
            "TRADES_open",
            "TRADES_high",
            "TRADES_low",
            "TRADES_close",
            "TRADES_volume",
            "TRADES_average",
            "TRADES_barCount",
        ]

        self.cols_del = [
            "ASK_volume",
            "ASK_average",
            "ASK_barCount",
            "BID_volume",
            "BID_average",
            "BID_barCount",
        ]

        self.cols_volumes = ["TRADES_volume"]
        self.cols_prices = [
            "ASK_open",
            "ASK_high",
            "ASK_low",
            "ASK_close",
            "BID_open",
            "BID_high",
            "BID_low",
            "BID_close",
            "TRADES_open",
            "TRADES_high",
            "TRADES_low",
            "TRADES_close",
            "TRADES_average",
            "VWAP",
        ]

        if hasattr(self, "ema_list"):
            for ema_period, ema_timeframe, _ in self.ema_list:
                self.cols_prices.append(f"{ema_period}EMA{ema_timeframe}")

        self.col_close = "TRADES_close"

    def _setup_ohlc_columns(self):
        """Setup columns for OHLC data"""
        self.columns_dl = [
            "date",
            "barCount",
            "open",
            "high",
            "low",
            "close",
            "average",
            "volume",
        ]
        self.cols_req = self.columns_dl
        self.cols_del = []
        self.cols_volumes = ["volume"]
        self.cols_prices = ["open", "high", "low", "close", "average", "VWAP"]

        if hasattr(self, "ema_list"):
            for ema_period, ema_timeframe, _ in self.ema_list:
                self.cols_prices.append(f"{ema_period}EMA{ema_timeframe}")

        self.col_close = "close"

    def get_interval_req(self, start_time: str = "", end_time: str = "") -> str | int:  # noqa: C901
        """Calculate required interval for data request"""
        # Default interval when no start specified
        if start_time == "":
            return (
                str(int(self.interval_max_allowed * self.interval_mfactor))
                + self.duration_letter
            )

        try:
            # Normalize inputs to Timestamp
            start_ts = pd.to_datetime(start_time)
            end_ts = pd.to_datetime(end_time)

            total_seconds = max(0, int((end_ts - start_ts).total_seconds()))

            unit_seconds = {
                "D": 86400,
                "H": 3600,
                "M": 60,
                "S": 1,
            }.get(self.delta_letter, 1)

            interval_needed = total_seconds // unit_seconds
            clamped = min(self.interval_max_allowed, int(interval_needed))
            interval_req = (
                f"{int(clamped * self.interval_mfactor)}{self.duration_letter}"
            )

            # Edge-case normalization consistent with legacy behavior
            if interval_req in {"0 D", "1 S"}:
                return 0
            if interval_req == "60 S" and self.bar_name == "minutes":
                return 0

            return interval_req

        except (ValueError, TypeError) as e:
            print(f"Warning: Error converting times in get_interval_req: {e}")
            # Use default interval if conversion fails
            return (
                str(int(self.interval_max_allowed * self.interval_mfactor))
                + self.duration_letter
            )


class BarConfigurationService:
    """Service for managing bar configurations"""

    def __init__(self):
        self.config = get_config()
        self._bar_cache: dict[str, BarConfiguration] = {}

    def create_bar_configuration(self, bar_str_full: str) -> BarConfiguration:
        """Create or retrieve cached bar configuration"""
        cache_key = bar_str_full.lower()

        if cache_key not in self._bar_cache:
            self._bar_cache[cache_key] = BarConfiguration(bar_str_full)

        return self._bar_cache[cache_key]

    def get_supported_bar_types(self) -> list[str]:
        """Get list of supported bar types"""
        return ["tick", "1 sec", "1 min", "30 min", "1 hour", "1 day"]

    def validate_bar_type(self, bar_str_full: str) -> bool:
        """Validate if bar type is supported"""
        bar_str_lower = bar_str_full.lower()

        supported_patterns = ["tick", "sec", "min", "hour", "day"]

        return any(pattern in bar_str_lower for pattern in supported_patterns)

    def get_bar_configuration_summary(self, bar_str_full: str) -> dict[str, Any]:
        """Get summary of bar configuration parameters"""
        bar_config = self.create_bar_configuration(bar_str_full)

        return {
            "bar_type": bar_config.bar_type,
            "bar_name": bar_config.bar_name,
            "bar_str": bar_config.bar_str,
            "interval_max_allowed": bar_config.interval_max_allowed,
            "multiple_days": bar_config.multiple_days,
            "merge_ask_bid_trades": bar_config.merge_ask_bid_trades,
            "columns_count": len(bar_config.columns_dl),
            "ema_configurations": getattr(bar_config, "ema_list", []),
        }


# Factory function for backward compatibility
def create_bar_cls(bar_str_full: str) -> BarConfiguration:
    """Factory function to create BarCLS equivalent (backward compatibility)"""
    service = BarConfigurationService()
    return service.create_bar_configuration(bar_str_full)


# Singleton service instance
_bar_service = None


def get_bar_service() -> BarConfigurationService:
    """Get singleton bar configuration service"""
    global _bar_service
    if _bar_service is None:
        _bar_service = BarConfigurationService()
    return _bar_service
