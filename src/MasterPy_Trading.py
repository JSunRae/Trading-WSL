from __future__ import annotations

import asyncio
import os  # sent text, check files
import signal
import sys
import time
from atexit import register as atexit_register
from datetime import datetime, timedelta
from pathlib import (
    Path,
)  # Apple / and windows \
from time import perf_counter
from typing import Any

import ib_async
import pandas as pd
import pytz
from joblib import dump, load  # type: ignore[import-untyped]  # Missing stubs

# Import typed pandas helpers
from src.data.pandas_helpers import (
    fillna_typed,
)

try:
    # Try relative import first (when used as package)
    from . import MasterPy as MP
except ImportError:
    # Fall back to absolute import (when used as script)
    import MasterPy as MP

# Add config management for hardcoded path fix
try:
    from .core.config import get_config
except ImportError:
    from src.core.config import get_config

# (imports moved to top to satisfy linters)

# Global version and base path (config-aware, with safe fallbacks)
Version = "V1"
try:
    _config = get_config()
except Exception:
    _config = None

if _config is not None:
    try:
        # Use configured base path and ensure trailing slash for concatenation below
        LocG = str(_config.data_paths.base_path / "Machine Learning")
        if not LocG.endswith("/"):
            LocG += "/"
    except Exception:
        LocG = os.path.expanduser("~/Machine Learning/")
else:
    LocG = os.path.expanduser("~/Machine Learning/")


def _to_timestamp_or_none(value: Any):
    """Best-effort conversion to pandas.Timestamp, else None for empty/invalid.

    Accepts str, datetime, date, pandas Timestamp. Returns tz-naive Timestamp when possible.
    """
    if value in (None, ""):
        return None
    try:
        ts = pd.Timestamp(value)
        # Strip timezone to simplify downstream comparisons
        if getattr(ts, "tz", None) is not None:
            try:
                ts = ts.tz_localize(None)
            except Exception:
                # Fallback for any odd tz objects
                ts = pd.Timestamp(ts.to_pydatetime().replace(tzinfo=None))
        return ts
    except Exception:
        return None


def _date_key_str(value: Any) -> str:
    """Normalize a date-like value to YYYY-MM-DD for key/index usage."""
    s = safe_date_to_string(value)
    return s[:10] if s else ""


def safe_date_to_string(date_obj: Any) -> str:
    """Convert various date types to string format safely"""
    if isinstance(date_obj, str):
        return date_obj[:10] if len(date_obj) >= 10 else date_obj
    elif hasattr(date_obj, "strftime"):
        # Type-safe access using Protocol
        date_with_strftime: HasStrftime = date_obj  # type: ignore[assignment]
        return date_with_strftime.strftime("%Y-%m-%d")
    elif date_obj is None or date_obj == "":
        return ""
    else:
        return str(date_obj)[:10]


def safe_datetime_to_string(datetime_obj: Any) -> str:
    """Convert various datetime types to string format safely"""
    if isinstance(datetime_obj, str):
        return datetime_obj
    elif hasattr(datetime_obj, "strftime"):
        # Type-safe access using Protocol
        datetime_with_strftime: HasStrftime = datetime_obj  # type: ignore[assignment]
        return datetime_with_strftime.strftime("%Y-%m-%d %H:%M:%S")
    elif datetime_obj is None or datetime_obj == "":
        return ""
    else:
        return str(datetime_obj)


def safe_df_scalar_access(df: Any, row: Any, col: Any, default: Any = None) -> Any:
    """Safely access a scalar value from DataFrame"""
    try:
        if row in df.index and col in df.columns:
            value = df.at[row, col]
            return value if not pd.isnull(value) else default
        return default
    except (KeyError, IndexError, AttributeError):
        return default


def safe_df_scalar_check(df: Any, row: Any, col: Any, check_value: Any) -> bool:
    """Safely check a scalar value from DataFrame against check_value"""
    try:
        if row in df.index and col in df.columns:
            value = df.at[row, col]
            if pd.isnull(value):
                return False
            return value == check_value
        return False
    except (KeyError, IndexError, AttributeError):
        return False


###############################################################################
#       Profiling Lines and Time
# import line_profiler
# profile = line_profiler.LineProfiler()
# atexit_register(profile.print_stats)


###############################################################################
#       Classes
###############################################################################
class BarCLS:
    def __init__(self, BarStr_Full: str) -> None:  # noqa: N803
        self.BarStr_Full = BarStr_Full.lower()
        self.BarSize = BarStr_Full  # Store original for compatibility
        if " " in BarStr_Full:
            self.BarPeriod = int(BarStr_Full.split(" ")[0])
        else:
            self.BarPeriod = 1

        if "tick" in self.BarStr_Full:
            self.IntervalReq = 1000  # Integer, others are string. Always grab this much for ticks, for other bars calculate it
        else:
            self.IntervalReq = (
                self.get_intervalReq
            )  # No brackets as want to divert to the function itself

        if self.BarPeriod > 1:
            if "30" in self.BarStr_Full:
                self.BarName = "minutes"
                self.BarType = 3
                self.BarStr = "_30m"

                self.Interval_Max_Allowed = 2000  # 24hrs*2(p/hr)*28=1month
                self.MergeAskBidTrades = False
                self.BarsReq = 5000  # Average bars in 365 days, 5000 from 'TWS Stats 30min 365 days.xlsx'
                self.delta_letter = "h"
                self.Duration_Letter = " D"  # TWS request in x durations
                self.Interval_mFactor = 1 / (2 * 24)  # Hours to Days
                self.MultipleDays = True
                self.Columns_dl = [
                    "date",
                    "barCount",
                    "open",
                    "high",
                    "low",
                    "close",
                    "average",
                    "volume",
                ]
                self.cols_req = self.Columns_dl
                self.cols_Volumes = ["volume"]
                self.cols_Prices = [
                    "open",
                    "high",
                    "low",
                    "close",
                    "average",
                    "VWAP",
                    "9EMA1day",
                    "20EMA1day",
                    "200EMA1day",
                ]
                self.col_close = "close"
            else:
                MP.ErrorCapture(
                    __name__, "Not setup for periods other than 1 or 30 for minutes"
                )
        elif "tick" in self.BarStr_Full:
            self.BarType = 0
            self.BarName = "ticks"
            self.BarStr = "_Tick"

            self.Interval_Max_Allowed = (
                1000  # that Histortical Download can do per request
            )
            self.BarsReq = 1000
            self.MultipleDays = False
            self.Columns_dl = [
                "idx",
                "time",
                "tickAttribLast",
                "price",
                "size",
                "exchange",
                "specialConditions",
            ]
            self.specialConditions_Reference = (
                "https://www.interactivebrokers.com/en/index.php?f=7235"
            )
            self.cols_req = [
                "idx",
                "time",
                "tickAttribLast",
                "price",
                "size",
                "pastLimit",
                "unreported",
                "Intermarket Sweep Order (F)",
                "MarketOpen(T)",
            ]  #'Extended Hours Trade (T)', not T is when submited, so the market may be open when processed but not when submitted.
            self.cols_Del = [
                "idx",
                "tickAttribLast",
                "exchange",
                "specialConditions",
            ]  # droping data as colum, keeping as index.
            self.cols_Volumes = ["size"]
            self.cols_Prices = ["price"]

        elif "sec" in self.BarStr_Full:
            self.BarType = 1
            self.BarName = "seconds"
            self.BarStr = "_1s"

            self.Interval_Max_Allowed = (
                2000  # max interval is apparently 1800, but 2000 seems to be working.
            )
            self.MergeAskBidTrades = True
            self.BarsReq = 60 * 30  # 30min worth
            self.delta_letter = "s"
            self.Duration_Letter = " S"
            self.Interval_mFactor = 1  # Same delta to duration
            self.MultipleDays = False
            self.Columns_dl = [
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
            self.cols_Del = [
                "ASK_average",
                "ASK_barCount",
                "ASK_volume",
                "BID_average",
                "BID_barCount",
                "BID_volume",
            ]
            self.cols_Volumes = ["TRADES_volume"]
            self.cols_Prices = [
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
                "20EMA1min",
                "9EMA5min",
                "20EMA5min",
            ]
            self.col_close = "TRADES_close"

        elif "min" in self.BarStr_Full:
            self.BarType = 2
            self.BarName = "minutes"
            self.BarStr = "_1m"

            self.Interval_Max_Allowed = 2000  # 60*24hrs=1day
            self.MergeAskBidTrades = True
            self.BarsReq = 60 * 8  # 60(min/hr)*8hours=1 trading day
            self.delta_letter = "m"
            self.Duration_Letter = " S"  # TWS request in x durations
            self.Interval_mFactor = 60  # Seconds (duration) in 1min (delta)
            self.MultipleDays = False
            self.Columns_dl = [
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
            self.cols_Del = [
                "ASK_volume",
                "ASK_average",
                "ASK_barCount",
                "BID_volume",
                "BID_average",
                "BID_barCount",
            ]
            self.cols_Volumes = ["TRADES_volume"]
            self.cols_Prices = [
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
                "20EMA1min",
                "9EMA5min",
                "20EMA5min",
                "200EMA5min",
            ]
            self.col_close = "TRADES_close"

        elif "hour" in self.BarStr_Full:
            self.BarType = 4
            self.BarName = "hours"
            self.BarStr = "_1h"

            self.Interval_Max_Allowed = 2000
            self.MergeAskBidTrades = False
            self.BarsReq = 2500  # Average bars in 365 days
            self.delta_letter = "h"
            self.Duration_Letter = " D"  # TWS request in x durations
            self.Interval_mFactor = 1 / 24  # Hours to Days
            self.MultipleDays = True
            self.Columns_dl = [
                "date",
                "average",
                "barCount",
                "close",
                "high",
                "low",
                "open",
                "volume",
            ]
            self.cols_req = self.Columns_dl
            self.cols_Del: list[str] = []
            self.cols_Volumes = ["volume"]
            self.cols_Prices = [
                "average",
                "close",
                "high",
                "low",
                "open",
                "VWAP",
                "9EMA1day",
                "20EMA1day",
                "200EMA1day",
            ]
            self.col_close = "close"

        elif "day" in self.BarStr_Full:
            self.BarType = 5
            self.BarName = "days"
            self.BarStr = "_1d"

            self.Interval_Max_Allowed = 2000
            self.MergeAskBidTrades = False
            self.BarsReq = 10 * 365  # 10 years? Probably never need this.
            self.delta_letter = "D"
            self.Duration_Letter = " D"  # TWS request in x durations
            self.Interval_mFactor = 1  # Same delta to duration
            self.MultipleDays = True
            self.Columns_dl = [
                "date",
                "average",
                "barCount",
                "close",
                "high",
                "low",
                "open",
                "volume",
            ]
            self.cols_req = self.Columns_dl
            self.cols_Del: list[str] = []
            self.cols_Volumes = ["volume"]
            self.cols_Prices = [
                "average",
                "close",
                "high",
                "low",
                "open",
                "VWAP",
                "200EMA1day",
            ]
            self.col_close = "close"

        else:
            MP.ErrorCapture(__name__, f"Bar Size not correct: {self.BarStr_Full}", 60)

        # For Prep_Cleaning
        if self.BarType == 0:  # Ticks
            self.MACD_timeframe = ""  # No EMA
            return  # with nothing
        elif self.BarType == 1:  # 1 Second
            self.EMA_List = [
                (20, "1min", 60),
                (9, "5min", 5 * 60),
                (20, "5min", 5 * 60),
            ]  # Sec to min
            self.MACD_timeframe = 5 * 60  #'5T'
        elif self.BarType == 2:  # 1 Min
            self.EMA_List = [
                (20, "1min", 1),
                (9, "5min", 1),
                (20, "5min", 1),
                (200, "5min", 1),
            ]  # min to 1min
            self.MACD_timeframe = 5  #'5T'
        elif self.BarType == 3:  # 30 Min
            self.EMA_List = [
                (9, "1day", 2 * 24),
                (20, "1day", 2 * 24),
                (200, "1day", 2 * 24),
            ]  # 30min to days
            self.MACD_timeframe = 2  #'2h'
        elif self.BarType == 4:  # 1 Hr
            self.EMA_List = [
                (9, "1day", 24),
                (20, "1day", 24),
                (200, "1day", 24),
            ]  # Hours to days
            self.MACD_timeframe = 1  #'H'
        elif self.BarType == 5:  # 1 Day
            self.EMA_List = [(200, "1day", 1)]  # Days
            self.MACD_timeframe = 1  #'d'
        else:
            MP.ErrorCapture(__name__, f"Bar Size not correct: {self.BarStr}", 60)

        self.BarStr_Full = f"{self.BarPeriod} {self.BarName}"

    def get_intervalReq(
        self, StartTime: Any | str | datetime = "", EndTime: Any | str | datetime = ""
    ) -> str | int:  # noqa: N803
        if StartTime == "":
            # OLD IntervalReq = str(int(min([self.Interval_Max_Allowed, self.BarsReq])*self.Interval_mFactor))+self.Duration_Letter
            IntervalReq = (
                str(int(self.Interval_Max_Allowed * self.Interval_mFactor))
                + self.Duration_Letter
            )
        else:
            # Convert inputs strictly to pandas Timestamps; fallback to default if invalid
            start_ts = _to_timestamp_or_none(StartTime)
            end_ts = _to_timestamp_or_none(EndTime)
            if start_ts is None or end_ts is None:
                Interval_Needed = self.Interval_Max_Allowed
            else:
                time_diff = end_ts - start_ts
                if self.delta_letter == "D":
                    Interval_Needed = max(int(time_diff.days), 0)
                elif self.delta_letter == "H":
                    Interval_Needed = max(int(time_diff.total_seconds() / 3600), 0)
                elif self.delta_letter == "M":
                    Interval_Needed = max(int(time_diff.total_seconds() / 60), 0)
                elif self.delta_letter == "S":
                    Interval_Needed = max(int(time_diff.total_seconds()), 0)
                else:
                    Interval_Needed = max(int(time_diff.total_seconds()), 0)
            # IE to pull the max allowed, or just what needed to reach starttime
            IntervalReq = (
                str(
                    int(
                        min([self.Interval_Max_Allowed, Interval_Needed])
                        * self.Interval_mFactor
                    )
                )
                + self.Duration_Letter
            )

            if IntervalReq == "0 D" or IntervalReq == "1 S":
                return 0
            if IntervalReq == "60 S" and self.BarSize == "minutes":
                return 0

        return IntervalReq


class GracefulExiterCLS:
    def __init__(self) -> None:
        self.state = False
        signal.signal(signal.SIGINT, self.keyboardInterruptHandler)

    def exit(self) -> bool:
        return self.state

    def keyboardInterruptHandler(self, signum: int, frame: Any) -> None:
        print("Exit signal received...")
        self.state = True


class Market_InfoCLS:
    def __init__(self, StockMarket: str = "NYSE"):  # noqa: N803
        if market_cal is None:
            print(
                "Warning: Market calendar functionality unavailable without pandas_market_calendars"
            )
            self.calandar = None
            self.Market_schedule = None
        else:
            self.calandar = market_cal.get_calendar(StockMarket)
            self.Market_schedule = self.calandar.schedule(
                start_date="2012-07-01", end_date="2030-01-01"
            )
        # self.Mark_open_days = self.calandar.valid_days(start_date='2012-07-01', end_date='2030-01-01')

    def is_Market_Open(self) -> bool:
        if self.calandar is None:
            # Fallback: assume market is open during business hours (9 AM - 4 PM ET)
            from datetime import datetime, time

            now = datetime.now().time()
            return time(9, 0) <= now <= time(16, 0)
        return self.calandar.is_open_now(self.Market_schedule)

    def get_TradeDates(
        self, forDate: datetime, Bar: BarCLS | Any | None = None, daysWanted: int = 3
    ) -> list[str]:  # noqa: N803
        """Return recent trade dates.

        - If Bar is None, assume minute bars for multi-day sequences.
        - When market schedule is unavailable, fall back to weekday-based dates.
        - When schedule is available and minute bars, return timezone-naive datetimes from schedule.
        """
        is_minute = False
        if Bar is None:
            is_minute = True
        else:
            try:
                # Prefer integer bar type codes if available
                is_minute = getattr(Bar, "BarType", None) == 2 or (
                    isinstance(Bar, str) and "min" in Bar.lower()
                )
            except Exception:
                is_minute = False

        if self.Market_schedule is None:
            # Fallback: generate simple date list based on weekdays
            from datetime import timedelta

            if is_minute:
                dates: list[str] = []
                current_date = forDate
                for _ in range(daysWanted):
                    while current_date.weekday() >= 5:  # Skip weekends
                        current_date -= timedelta(days=1)
                    dates.append(current_date.strftime("%Y-%m-%d"))
                    current_date -= timedelta(days=1)
                return dates
            else:
                return [forDate.strftime("%Y-%m-%d")]

        if is_minute:
            OpenDates = self.Market_schedule[: forDate.strftime("%Y-%m-%d")]
            trade_dt = OpenDates[-daysWanted:]["market_close"].dt.tz_localize(None)
            TradeDates = [dt.strftime("%Y-%m-%d") for dt in trade_dt]
        else:
            TradeDates = [forDate.strftime("%Y-%m-%d")]

        return TradeDates

    def get_LastTradeDay(self, forDate: datetime):  # noqa: N803
        if self.Market_schedule is None:
            # Fallback: return previous weekday
            from datetime import timedelta

            last_trade_day = forDate
            while last_trade_day.weekday() >= 5:  # Skip weekends
                last_trade_day -= timedelta(days=1)
            return last_trade_day

        OpenDates = self.Market_schedule[: forDate.strftime("%Y-%m-%d")]
        LastTradeDateTime = OpenDates.iloc[-1]["market_close"]

        return LastTradeDateTime.tz_localize(None)


class requestCheckerCLS:
    def __init__(self, host: str, port: int, clientId: int, ib: Any):  # noqa: N803
        self.ib = ib  # ib_async.IB()
        # self.ib.errorEvent += self.onErrorJR #`+=`` operator can be used as a synonym for 'connect' method

        # GracefulExiterCLS
        self.exitflag = False
        signal.signal(signal.SIGINT, self.keyboardInterruptHandler)
        atexit_register(self.On_Exit)
        self.On_Exit_Run = perf_counter()

        self.NYSE = Market_InfoCLS("NYSE")

        self.ReqDict: dict[int, list[Any]] = {}
        self.ReqTime = perf_counter()
        self.ReqTimePrev = perf_counter()
        self.SleepTot = 0
        self.TotalSlept = 0

        self.symbolPrev = ""  # to check for identical requests
        self.endDateTimePrev = datetime.date(
            datetime.today() + timedelta(1)
        )  # tomorrow as it should not be ever used
        self.WhatToShowPrev = ""  # to check for identical requests

        # Initialize configuration for proper path management
        try:
            self.config = get_config()
        except Exception as e:
            print(f"Warning: Could not load config, using fallback paths: {e}")
            self.config = None

        # Use configuration-based paths instead of hardcoded ones
        if self.config:
            self.Loc_IBFailed = str(self.config.get_data_file_path("ib_failed_stocks"))
            self.Loc_IBDlable = str(
                self.config.get_data_file_path("ib_downloadable_stocks")
            )
            self.Loc_IBDled = str(
                self.config.get_data_file_path("ib_downloaded_stocks")
            )
        else:
            # Fallback to platform-appropriate paths
            if sys.platform == "win32":
                base_path = "G:\\Machine Learning\\"
            else:
                base_path = os.path.expanduser("~/Machine Learning/")
            self.Loc_IBFailed = base_path + "IB Failed Stocks.xlsx"
            self.Loc_IBDlable = base_path + "IB Downloadable Stocks.xlsx"
            self.Loc_IBDled = base_path + "IB Downloaded Stocks.xlsx"

        # Initialize DataFrames with error handling using config paths
        try:
            self.df_IBFailed = load_excel(
                self.Loc_IBFailed,
                sheet=0,
                index_col="Stock",
            )
        except (FileNotFoundError, PermissionError, ValueError) as e:
            print(f"Warning: Could not load IB Failed Stocks.xlsx: {e}")
            self.df_IBFailed = pd.DataFrame(index=pd.Index([], name="Stock"))

        try:
            self.df_IBDownloadable = load_excel(
                self.Loc_IBDlable,
                sheet=0,
                index_col="Stock",
            )
        except (FileNotFoundError, PermissionError, ValueError) as e:
            print(f"Warning: Could not load IB Downloadable Stocks.xlsx: {e}")
            self.df_IBDownloadable = pd.DataFrame(index=pd.Index([], name="Stock"))

        try:
            self.df_IBDownloaded = load_excel(
                self.Loc_IBDled,
                sheet=0,
                index_col="DateStock",
            )
        except (FileNotFoundError, PermissionError, ValueError) as e:
            print(f"Warning: Could not load IB Downloaded Stocks.xlsx: {e}")
            self.df_IBDownloaded = pd.DataFrame(index=pd.Index([], name="DateStock"))
        # self.df_IBDownloaded = self.df_IBDownloaded.set_index(['Date','Stock']) #MutliIndex

        # self.df_IBFailed = pd.read_feather("G:/Machine Learning/IB Failed Stocks.ftr")
        # self.df_IBDownloadable = pd.read_feather("G:/Machine Learning/IB Downloadable Stocks.ftr")
        # self.df_IBDownloaded = pd.read_feather("G:/Machine Learning/IB Downloaded Stocks.ftr")

        self.FailChanges = 0
        self.DownloadableChanges = 0
        self.DownloadedChanges = 0

        self.Downloading = False  # To only historical one at a time

        if os.path.exists("./Files/requestChecker.bin"):
            self.timeframeRequests: list[float]
            self.allRequests: list[float]
            self.timeframeRequests, self.allRequests = load(
                "./Files/requestChecker.bin"
            )
            self.maxTime = max(max(self.timeframeRequests), max(self.allRequests)) + (
                time.time() - os.path.getmtime("./Files/requestChecker.bin")
            )  # max of bost lists (most recent) - how old the file is
            self.allRequests = [
                x - self.maxTime for x in self.allRequests
            ]  # reset the perf_counter() which starts at zero
            self.timeframeRequests = [
                x - self.maxTime for x in self.timeframeRequests
            ]  # reset the perf_counter() which starts at zero
            del self.maxTime
        else:
            self.timeframeRequests: list[float] = []
            self.allRequests: list[float] = []

    def get_LastTradeDay(self, forDate: datetime):  # noqa: N803
        return self.NYSE.get_LastTradeDay(forDate)

    def get_TradeDates(
        self,
        forDate: datetime,
        Bar: BarCLS | Any | None = None,
        daysWanted: int | None = None,
    ) -> list[str]:  # noqa: N803
        # Backward-compatible shim: existing callers omit Bar; default to minute behavior
        return self.NYSE.get_TradeDates(forDate, Bar, daysWanted or 3)

    def appendFailed(
        self,
        symbol: SymbolT,
        NonExistant: bool = True,
        EarliestAvailBar: str = "",
        BarSize: str | None = None,
        forDate: str = "",
        comment: str = "",
    ) -> None:
        SaveMe = False

        if symbol == "":
            MP.ErrorCapture(
                __name__, "Symbol cannot be blank to AppendFailed List", 60, False
            )
            return

        # df_IBFailed is always initialized; no None-check needed

        # Normalize inputs to consistent forms
        _earliest_ts = _to_timestamp_or_none(EarliestAvailBar)
        EarliestAvailBar = safe_datetime_to_string(
            _earliest_ts or EarliestAvailBar
        )  # store string consistently

        forDate = safe_datetime_to_string(forDate)

        # Comment-only capture (no bar size provided)
        if (BarSize is None) and comment != "":
            for i in range(10):
                if (
                    "Comment" + str(i) not in self.df_IBFailed.columns
                ):  # create it and break
                    self.df_IBFailed.loc[symbol, "Date" + str(i)] = forDate
                    self.df_IBFailed.loc[symbol, "Comment" + str(i)] = comment
                    SaveMe = True
                    break
                elif pd.isnull(
                    self.df_IBFailed.loc[symbol, "Comment" + str(i)]
                ):  # no note
                    self.df_IBFailed.loc[symbol, "Date" + str(i)] = forDate
                    self.df_IBFailed.loc[symbol, "Comment" + str(i)] = comment
                    SaveMe = True
                    break
                elif (
                    self.df_IBFailed.loc[symbol, "Comment" + str(i)]
                    == forDate + "::" + comment
                ):  # already noted
                    break

            if pd.isnull(self.df_IBFailed.loc[symbol, "NonExistant"]):
                self.df_IBFailed.loc[symbol, "NonExistant"] = "Maybe"

        else:
            SaveMe = True
            if NonExistant:
                # self.df_IBFailed = self.df_IBFailed.append({'Stock':symbol, 'NonExistant': 'Yes'}, ignore_index=True)
                self.df_IBFailed.loc[symbol, "NonExistant"] = "Yes"

            else:
                # self.df_IBFailed = self.df_IBFailed.append({'Stock':symbol, 'NonExistant': 'No', 'DateStr': DateStr}, ignore_index=True)
                self.df_IBFailed.loc[symbol, "NonExistant"] = "No"
                if pd.isnull(self.df_IBFailed.loc[symbol, "EarliestAvailBar"]):
                    # EarliestAvailBar already normalized to string above
                    if EarliestAvailBar:
                        self.df_IBFailed.loc[symbol, "EarliestAvailBar"] = (
                            EarliestAvailBar
                        )

                # Require a concrete bar size to record failure details
                if BarSize is None:
                    MP.ErrorCapture(
                        __name__,
                        "BarSize must be provided when NonExistant is False",
                        60,
                        False,
                    )
                    return

                col = f"{BarSize}-LatestFailed"
                if col not in self.df_IBFailed.columns:
                    self.df_IBFailed.loc[symbol, col] = forDate
                else:
                    try:
                        latest_failed = self.df_IBFailed.at[symbol, col]
                        if pd.isnull(latest_failed):
                            self.df_IBFailed.loc[symbol, col] = forDate
                        elif latest_failed > forDate:
                            self.df_IBFailed.loc[symbol, col] = forDate
                    except (KeyError, IndexError):
                        self.df_IBFailed.loc[symbol, col] = forDate

        if SaveMe:
            self.FailChanges += 1

        if self.FailChanges >= 20:
            self.FailChanges = 0
            self.df_IBFailed = self.df_IBFailed.sort_values("Stock")
            self.df_IBFailed.to_excel(
                "G:/Machine Learning/IB Failed Stocks.xlsx",
                sheet_name="Sheet1",
                index=True,
                engine="openpyxl",
            )

    def is_failed(
        self, symbol: SymbolT, BarSize: str | BarSizeT, forDate: str = ""
    ) -> bool:
        # df_IBFailed is always initialized; no None-check needed

        if symbol not in self.df_IBFailed.index:  # Doesn't exist
            return False
        elif safe_df_scalar_check(self.df_IBFailed, symbol, "NonExistant", "Yes"):
            return True
        else:
            # Always construct the failure column name from a string
            bar_key = f"{str(BarSize)}-LatestFailed"
            latest_failed = safe_df_scalar_access(self.df_IBFailed, symbol, bar_key)
            lf_ts = _to_timestamp_or_none(latest_failed)
            # Accept str/datetime/Timestamp for forDate
            fd_ts = _to_timestamp_or_none(forDate)
            if lf_ts is None or fd_ts is None:
                return False
            return lf_ts >= fd_ts

    async def getEarliestAvailBar(self, contract: Any) -> Any:
        # DataFrames are always initialized; check indices or fallback to API
        if contract.symbol in self.df_IBFailed.index:
            EarliestAvailBar = self.df_IBFailed.loc[contract.symbol, "EarliestAvailBar"]
        elif contract.symbol in self.df_IBDownloadable.index:
            EarliestAvailBar = self.df_IBDownloadable.loc[
                contract.symbol, "EarliestAvailBar"
            ]
        else:
            self.SendRequest("", contract.symbol, "", "TRADES")
            EarliestAvailBar = await self.ib.reqHeadTimeStampAsync(
                contract, "TRADES", useRTH=False, formatDate=1
            )  # Outside hours, 1=non timezone aware
            self.ReqDict[self.ib.client._reqIdSeq] = [contract.symbol, "TRADES", ""]

        # Normalize to tz-naive Timestamp with fallback
        ts = _to_timestamp_or_none(EarliestAvailBar)
        if ts is None:
            ts = pd.Timestamp(year=2000, month=1, day=1)
        return ts

    def avail2Download(
        self, symbol: SymbolT, bar_size: BarSizeT, forDate: str = ""
    ) -> bool:
        # df_IBFailed is always initialized; no None-check needed

        if forDate == "":
            MP.ErrorCapture(__name__, "forDate in avail2Download is blank", 180, False)
            return True
        else:
            forDate_ts = _to_timestamp_or_none(forDate)
            if forDate_ts is None:
                # If we can't parse the input, allow download
                return True

        if symbol in self.df_IBFailed.index:
            if self.df_IBFailed.loc[symbol, "NonExistant"] == "Yes":
                return False
            elif True:
                # if len(self.df_IBFailed[(self.df_IBFailed['Stock']==symbol) & (self.df_IBFailed['DateStr']==symbol)]) == 1:
                earliest_avail = safe_df_scalar_access(
                    self.df_IBFailed, symbol, "EarliestAvailBar"
                )
                ea_ts = _to_timestamp_or_none(earliest_avail)
                if ea_ts is not None and ea_ts > forDate_ts:  # type: ignore[name-defined]
                    return False
                else:
                    if (
                        bar_size + "-LatestFailed" not in self.df_IBFailed.columns
                    ):  # No column fails recorded
                        return True
                    else:
                        latest_failed = safe_df_scalar_access(
                            self.df_IBFailed, symbol, bar_size + "-LatestFailed"
                        )
                        lf_ts = _to_timestamp_or_none(latest_failed)
                        if lf_ts is None:  # no fail recorded
                            return True
                        elif lf_ts < forDate_ts:  # type: ignore[name-defined]
                            # a date before an already known failed date
                            return False
                        else:
                            return True
            else:
                return True
        else:
            return True

    def Download_Exists(self, symbol: str, bar_size: str, forDate: str = "") -> bool:
        # df_IBDownloaded is always initialized; no None-check needed

        # MutliIndex
        # if not self.df_IBDownloaded.index.isin([(forDate, symbol)]).any(): #Doesn't exist
        #    return False
        # elif self.df_IBDownloaded.loc[(forDate, symbol), BarSize] == 'Yes':
        #    return True
        # elif self.df_IBDownloaded.loc[(forDate, symbol), BarSize] == 'TBA':
        #    return False
        # else:
        #    print("Unknown issue")

        date_str = _date_key_str(forDate)
        StockDate = date_str + "-" + symbol

        if StockDate not in self.df_IBDownloaded.index:  # Doesn't exist
            return False
        elif safe_df_scalar_check(self.df_IBDownloaded, StockDate, bar_size, "Yes"):
            return True
        elif safe_df_scalar_check(self.df_IBDownloaded, StockDate, bar_size, "TBA"):
            return False
        else:
            print("Unknown issue")
            return False

    def appendDownloaded(self, symbol: str, bar_size: str, forDate: Any) -> None:
        # df_IBDownloaded is always initialized; no None-check needed

        date_str = _date_key_str(forDate)
        StockDate = date_str + "-" + symbol

        # MutliIndex
        # if not self.df_IBDownloaded.index.isin([(forDate, symbol)]).any(): #Doesn't exist:
        #    self.df_IBDownloaded.loc[(forDate,symbol),BarSize] = 'Yes' #immutable, should save itself.
        #    self.df_IBDownloaded.loc[(forDate,symbol),:] = self.df_IBDownloaded.loc[(forDate,symbol),:].fillna('TBA') #not immutable
        # elif pd.isnull(self.df_IBDownloaded.loc[(forDate, symbol), BarSize]): #[0] N.a
        #    self.df_IBDownloaded.loc[(forDate, symbol), BarSize] = 'Yes'
        # elif self.df_IBDownloaded.loc[(forDate, symbol), BarSize] == 'TBA' : #[0] N.a
        #    self.df_IBDownloaded.loc[(forDate, symbol), BarSize] = 'Yes'

        if StockDate not in self.df_IBDownloaded.index:
            self.df_IBDownloaded.loc[StockDate, bar_size] = (
                "Yes"  # immutable, should save itself.
            )
            self.df_IBDownloaded.loc[StockDate, "Stock"] = (
                symbol  # immutable, should save itself.
            )
            self.df_IBDownloaded.loc[StockDate, "Date"] = (
                forDate  # immutable, should save itself.
            )
            # Force 2D selection so type is DataFrame for fillna_typed
            _row_df = self.df_IBDownloaded.loc[[StockDate], :]
            _row_df = fillna_typed(_row_df, "TBA")
            self.df_IBDownloaded.loc[[StockDate], :] = _row_df
        else:
            current_value = safe_df_scalar_access(
                self.df_IBDownloaded, StockDate, bar_size
            )
            if current_value is None:  # N.a
                self.df_IBDownloaded.loc[StockDate, bar_size] = "Yes"
            elif current_value == "TBA":  # [0] N.a
                self.df_IBDownloaded.loc[StockDate, bar_size] = "Yes"

    def appendDownloadable(
        self,
        symbol: str,
        bar_size: str,
        EarliestAvailBar: Any,
        StartDate: str | Any = "",
        EndDate: str | Any = "",
    ) -> None:
        SaveMe = False

        # Normalize inputs
        earliest_ts = _to_timestamp_or_none(EarliestAvailBar)
        EarliestAvailBar = safe_datetime_to_string(earliest_ts or EarliestAvailBar)

        start_ts = _to_timestamp_or_none(StartDate)
        end_ts = _to_timestamp_or_none(EndDate)

        if bar_size + "-StartDate" not in self.df_IBDownloadable.columns:
            self.df_IBDownloadable[bar_size + "-StartDate"] = ""
        if bar_size + "-EndDate" not in self.df_IBDownloadable.columns:
            self.df_IBDownloadable[bar_size + "-EndDate"] = ""

        if symbol not in self.df_IBDownloadable.index:
            self.df_IBDownloadable.loc[symbol, bar_size + "-StartDate"] = (
                start_ts if start_ts is not None else StartDate
            )
            self.df_IBDownloadable.loc[symbol, bar_size + "-EndDate"] = (
                end_ts if end_ts is not None else EndDate
            )  # only need to check once
            SaveMe = True
        else:
            start_date_val = safe_df_scalar_access(
                self.df_IBDownloadable, symbol, bar_size + "-StartDate"
            )
            sd_ts = _to_timestamp_or_none(start_date_val)
            if sd_ts is None and (start_ts is not None or StartDate != ""):
                self.df_IBDownloadable.loc[symbol, bar_size + "-StartDate"] = (
                    start_ts if start_ts is not None else StartDate
                )
                SaveMe = True
            elif start_ts is not None and sd_ts is not None and sd_ts > start_ts:
                self.df_IBDownloadable.loc[symbol, bar_size + "-StartDate"] = start_ts
                SaveMe = True

        end_date_val = safe_df_scalar_access(
            self.df_IBDownloadable, symbol, bar_size + "-EndDate"
        )
        ed_ts = _to_timestamp_or_none(end_date_val)
        if ed_ts is None and (end_ts is not None or EndDate != ""):
            self.df_IBDownloadable.loc[symbol, bar_size + "-EndDate"] = (
                end_ts if end_ts is not None else EndDate
            )
            SaveMe = True
        elif end_ts is not None and ed_ts is not None:
            if ed_ts < end_ts + timedelta(milliseconds=1):
                self.df_IBDownloadable.loc[symbol, bar_size + "-EndDate"] = end_ts
                SaveMe = True
        elif EndDate != "":
            # Fallback when types are not comparable
            self.df_IBDownloadable.loc[symbol, bar_size + "-EndDate"] = EndDate
            SaveMe = True

        earliest_avail_val = safe_df_scalar_access(
            self.df_IBDownloadable, symbol, "EarliestAvailBar"
        )
        if earliest_avail_val is None:
            self.df_IBDownloadable.loc[symbol, "EarliestAvailBar"] = EarliestAvailBar

        if SaveMe:
            self.DownloadableChanges += 1

        if self.DownloadableChanges >= 100:
            self.DownloadableChanges = 0
            self.df_IBDownloadable = self.df_IBDownloadable.sort_values("Stock")
            self.df_IBDownloadable.to_excel(
                "G:/Machine Learning/IB Downloadable Stocks.xlsx",
                sheet_name="Sheet1",
                index=True,
                engine="openpyxl",
            )

    def onErrorJR(
        self, reqId: int, errorId: int, errorStr: str, contract: Any
    ) -> None:  # , contract):
        # look at errorCode to see if warning or error
        if "pacing violation" in errorStr:
            print("Pacing Violation - Sleep Remaining: ", self.SleepRem())
            return
        if reqId == -1:
            MP.ErrorCapture(__name__, str(errorId) + ": " + errorStr, 1, True)
        elif reqId not in self.ReqDict.keys():
            print("Request ID NOT in dictionary:", reqId)
        elif errorId == 2103:
            untilTime = datetime.now() + timedelta(seconds=20)
            untilTime = untilTime.strftime("%I:%M:%S %p")
            print(f"Sleeping {errorStr}: until {untilTime}")
            self.ib.sleep(20)
        elif "returned no data" in errorStr:
            CxSymbol, CxTimeFrame, CxendDateTime = self.ReqDict[reqId]
            if CxSymbol == contract.symbol:
                self.appendFailed(
                    contract.symbol,
                    NonExistant=False,
                    BarSize=CxTimeFrame,
                    comment=errorStr,
                    forDate=CxendDateTime,
                )
        elif "No security definition has been found" in errorStr:
            CxSymbol, CxTimeFrame, CxendDateTime = self.ReqDict[reqId]
            if CxSymbol == contract.symbol:
                self.appendFailed(
                    contract.symbol,
                    NonExistant=True,
                    BarSize=CxTimeFrame,
                    comment=errorStr,
                    forDate=CxendDateTime,
                )
        elif "No historical market data" in errorStr:
            CxSymbol, CxTimeFrame, CxendDateTime = self.ReqDict[reqId]
            if CxSymbol == contract.symbol:
                self.appendFailed(
                    contract.symbol,
                    NonExistant=False,
                    BarSize=CxTimeFrame,
                    comment=errorStr,
                    forDate=CxendDateTime,
                )
        elif "connection is broken" in errorStr:
            print("Ignore:", errorStr)
        else:
            print(errorStr)

    def ReqRemaining(self) -> int:  # remaingin requests in next 10min
        self.allRequests = [
            x for x in self.allRequests if x >= (self.TimeOut)
        ]  # remove any older than 10min
        return 60 - len(self.allRequests)

    def SleepRem(self) -> float:
        return self.SleepTot - (perf_counter() - self.ReqTime)

    def Sleep_TotalTime(self, StrTxt: str = "", FinishedSleeping: bool = False) -> None:
        untilTime = datetime.now() + timedelta(seconds=self.SleepTot)
        untilTime = untilTime.strftime("%I:%M:%S %p")

        if FinishedSleeping and self.TotalSlept > 0:
            slept_m, slept_s = divmod(round(self.TotalSlept), 60)
            print(
                f"Slept until {untilTime} Total: {slept_m}:{slept_s:02}min                                   "
            )
            self.TotalSlept = 0
        elif not FinishedSleeping:
            self.TotalSlept = self.TotalSlept + self.SleepTot
            m, s = divmod(round(self.SleepTot), 60)
            slept_m, slept_s = divmod(round(self.TotalSlept), 60)

            if self.SleepTot > 1:  # longer than 1 second
                print(
                    f"Sleeping {StrTxt}: {m}:{s:02}min until {untilTime}: Total: {slept_m}:{slept_s:02}min",
                    end="\r",
                )

            try:
                # Prefer non-blocking sleep when possible; if event loop context, this may be awaited elsewhere
                self.ib.sleep(self.SleepTot)
            except Exception:
                pass

    async def aSendRequest(
        self, timeframe: str, symbol: str, endDateTime: str | Any, WhatToShow: str
    ) -> None:
        """Async-safe variant of SendRequest that avoids blocking sleeps."""
        self.ReqTime = perf_counter()
        if (
            self.symbolPrev == symbol
            and self.endDateTimePrev == endDateTime
            and self.WhatToShowPrev == WhatToShow
        ):
            self.SleepTot = max(0, 15 - (self.ReqTime - self.ReqTimePrev))
            if self.SleepTot > 0:
                untilTime = datetime.now() + timedelta(seconds=self.SleepTot)
                untilTime = untilTime.strftime("%I:%M:%S %p")
                m, s = divmod(round(self.SleepTot), 60)
                slept_m, slept_s = divmod(round(self.TotalSlept + self.SleepTot), 60)
                print(
                    f"Sleeping Identical Call: {m}:{s:02}min until {untilTime}: Total: {slept_m}:{slept_s:02}min",
                    end="\r",
                )
                await asyncio.sleep(self.SleepTot)
        else:
            self.ReqTimePrev = self.ReqTime
            self.symbolPrev = symbol
            self.endDateTimePrev = endDateTime
            self.WhatToShowPrev = WhatToShow

        # 60 requests in 10 minutes
        self.ReqTime = perf_counter()
        self.TimeOut = self.ReqTime - 10 * 60
        self.allRequests = [x for x in self.allRequests if x >= (self.TimeOut)]
        self.allRequests.append(self.ReqTime)
        if len(self.allRequests) > 60:
            self.SleepTot = max(0, 60 * 10 - (self.ReqTime - self.allRequests[0]))
            if self.SleepTot > 0:
                await asyncio.sleep(self.SleepTot)

        # 6 requests in 2 seconds for second bars
        if "sec" in timeframe.lower():
            self.ReqTime = perf_counter()
            self.TimeOut = self.ReqTime - 2
            self.timeframeRequests = [
                x for x in self.timeframeRequests if x >= (self.TimeOut)
            ]
            self.timeframeRequests.append(self.ReqTime)
            if len(self.timeframeRequests) > 6:
                self.SleepTot = max(0, 2 - (self.ReqTime - self.timeframeRequests[0]))
                if self.SleepTot > 0:
                    await asyncio.sleep(self.SleepTot)

    def SendRequest(
        self, timeframe: str, symbol: str, endDateTime: str | Any, WhatToShow: str
    ) -> None:  # noqa: N802, N803
        # CHECK IF IDENTICAL 15s between identical
        self.ReqTime = perf_counter()
        if (
            self.symbolPrev == symbol
            and self.endDateTimePrev == endDateTime
            and self.WhatToShowPrev == WhatToShow
        ):  # IDENTICAL
            self.SleepTot = max(
                0, 15 - (self.ReqTime - self.ReqTimePrev)
            )  # Up to 15 seconds between identical
            self.Sleep_TotalTime("Identical Call")

        else:  # not identical, then record the current request for the next call
            self.ReqTimePrev = self.ReqTime
            self.symbolPrev = symbol
            self.endDateTimePrev = endDateTime
            self.WhatToShowPrev = WhatToShow

        # 60 requests in 10 minutes
        self.ReqTime = perf_counter()
        self.TimeOut = self.ReqTime - 10 * 60
        self.allRequests = [
            x for x in self.allRequests if x >= (self.TimeOut)
        ]  # remove any older than 10min
        self.allRequests.append(self.ReqTime)
        if len(self.allRequests) > 60:  # 60 requests in 10min limit
            self.SleepTot = max(
                [0, 60 * 10 - (self.ReqTime - self.allRequests[0])]
            )  # 10min minus (diff between now and first)
            self.Sleep_TotalTime("MaxCalls 10min")

        # 6 requests in 2 seconds
        if "sec" in timeframe.lower():
            self.ReqTime = perf_counter()
            self.TimeOut = self.ReqTime - 2
            self.timeframeRequests = [
                x for x in self.timeframeRequests if x >= (self.TimeOut)
            ]  # remove any older than 2s
            self.timeframeRequests.append(self.ReqTime)
            if len(self.timeframeRequests) > 6:  # 6 requests in 2sec limit
                self.SleepTot = max(
                    [0, 2 - (self.ReqTime - self.timeframeRequests[0])]
                )  # 2seconds minus (diff between now and first)
                self.Sleep_TotalTime("6Requests in 2sec")

    def Save_requestChecks(self) -> None:
        for _ in range(0, 3):
            try:
                dump(
                    [self.timeframeRequests, self.allRequests],
                    "./Files/requestChecker.bin",
                    compress=True,
                )
            except:
                continue
            break

    def On_Exit(self) -> None:
        if self.On_Exit_Run > perf_counter() - 5:  # 5sec ago
            return

        if self.DownloadedChanges > 0:
            self.DownloadedChanges = 0
            self.df_IBDownloaded = sort_index_typed(self.df_IBDownloaded)
            # self.df_IBDownloaded.to_feather("G:/Machine Learning/IB Downloaded Stocks.ftr")
            save_excel(
                self.df_IBDownloaded,
                "G:/Machine Learning/IB Downloaded Stocks.xlsx",
                index=True,
            )

        if self.DownloadableChanges > 0:
            self.DownloadableChanges = 0
            self.df_IBDownloadable = sort_values_typed(self.df_IBDownloadable, "Stock")
            # self.df_IBDownloadable.to_feather("G:/Machine Learning/IB Downloadable Stocks.ftr")
            save_excel(
                self.df_IBDownloadable,
                "G:/Machine Learning/IB Downloadable Stocks.xlsx",
                index=True,
            )

        if self.FailChanges > 0:
            self.FailChanges = 0
            self.df_IBFailed = sort_values_typed(self.df_IBFailed, "Stock")
            # self.df_IBFailed.to_feather("G:/Machine Learning/IB Failed Stocks.ftr")
            save_excel(
                self.df_IBFailed,
                "G:/Machine Learning/IB Failed Stocks.xlsx",
                index=True,
            )

        self.Save_requestChecks()

        print("Finished Request Exit Checks")
        self.On_Exit_Run = perf_counter()

    def keyboardInterruptHandler(self, signum: int, frame: Any) -> None:
        print("")
        print("Exit flag triggered, will continue until current download finished...")
        self.Sleep_TotalTime()
        signal.signal(signal.SIGINT, signal.SIG_DFL)
        self.exitflag = True

    async def _download_historical_async(
        self, contract: Any, BarObj: BarCLS | Any, forDate: str = ""
    ) -> Any:  # noqa: N802, N803
        # Wait for availability
        while self.Downloading:
            waiting = max(self.SleepRem(), 0.1)
            print("Download Pause", waiting)
            await asyncio.sleep(waiting)

        if self.exitflag:
            self.Sleep_TotalTime(FinishedSleeping=False)
            return

        self.Downloading = True

        # Determine Start and End of download required
        if forDate == "":  # For now (live trading or testing)
            if BarObj.MultipleDays:
                StartTimeStr = (
                    datetime.strftime(datetime.today() - timedelta(400), "%Y-%m-%d")
                    + "T00:00"
                )
            else:
                StartTimeStr = datetime.strftime(datetime.now(), "%Y-%m-%d") + "T08:00"
            EndTimeStr = datetime.strftime(datetime.now(), "%Y-%m-%dT%H:%M")
        else:
            # Normalize input date once (accepts str/datetime/Timestamp)
            DateStr = _date_key_str(forDate)
            fd_ts = (
                _to_timestamp_or_none(DateStr)
                or _to_timestamp_or_none(forDate)
                or pd.Timestamp.today()
            )

            if BarObj.MultipleDays:
                StartTimeStr = (
                    datetime.strftime(fd_ts - timedelta(400), "%Y-%m-%d") + "T00:00"
                )
                EndTimeStr = DateStr + "T23:59"
            else:
                StartTimeStr = DateStr + (
                    "T09:00" if "tick" in BarObj.BarSize else "T08:00"
                )
                if "tick" in BarObj.BarSize:
                    EndTimeStr = DateStr + "T10:30"
                elif "sec" in BarObj.BarSize:
                    EndTimeStr = DateStr + "T12:00"
                elif "min" in BarObj.BarSize:
                    EndTimeStr = DateStr + "T16:00"
                else:
                    EndTimeStr = DateStr + "T23:59"

        EndTime: pd.Timestamp = pd.Timestamp(EndTimeStr).tz_localize("US/Eastern")
        StartTime = pd.Timestamp(StartTimeStr)

        if not self.NYSE.is_Market_Open():
            LastTradeDay = pd.Timestamp(
                self.NYSE.get_LastTradeDay(EndTime)
            ).tz_localize("US/Eastern")
            if LastTradeDay < EndTime:
                EndTime = LastTradeDay

        # Get the start time from previous save, or set it.
        _path_end: Path = IB_Download_Loc(contract.symbol, BarObj, EndTimeStr)
        if _path_end.exists():
            _path_start: Path = IB_Download_Loc(contract.symbol, BarObj, StartTimeStr)
            prev_df = pd.read_feather(str(_path_start))
            if BarObj.MultipleDays:
                prev_df = prev_df.set_index("date")
                StartTime = pd.Timestamp(prev_df.index.max())
            else:
                self.Downloading = False
                EarliestAvailBar = await self.getEarliestAvailBar(contract)
                if "time" in prev_df.columns:
                    _st = prev_df["time"].min()
                    _et = prev_df["time"].max()
                    StartTime = pd.Timestamp(_st)
                    EndTime = pd.Timestamp(_et)
                elif "date" in prev_df.columns:
                    _st = prev_df["date"].min()
                    _et = prev_df["date"].max()
                    StartTime = pd.Timestamp(_st)
                    EndTime = pd.Timestamp(_et)
                else:
                    MP.ErrorCapture_ReturnAns(
                        __name__, "Not sure what date/time columns to use", 180, False
                    )

                self.appendDownloaded(contract.symbol, BarObj.BarSize, forDate=forDate)
                self.appendDownloadable(
                    contract.symbol,
                    BarObj.BarSize,
                    EarliestAvailBar=safe_date_to_string(EarliestAvailBar),
                    StartDate=safe_date_to_string(StartTime),
                    EndDate=safe_date_to_string(EndTime),
                )
                return prev_df

            if StartTime >= (datetime.today().date() - pd.tseries.offsets.BDay(1)):
                self.Downloading = False
                return
        else:
            StartTime = pd.Timestamp(StartTimeStr)
            prev_df = "Doesnt exist"  # type: ignore[assignment]

        EarliestAvailBar = await self.getEarliestAvailBar(contract)
        StartTime = max(StartTime, EarliestAvailBar)

        # Loop until completely downloaded
        df = pd.DataFrame()
        self.Save_requestChecks()

        if StartTime.tz is None:
            StartTime = StartTime.tz_localize("US/Eastern")
        if EndTime.tz is None:
            EndTime = EndTime.tz_localize("US/Eastern")

        while EndTime > StartTime or StartTime == "":
            IntervalReq = BarObj.IntervalReq
            if IntervalReq == 0:
                self.Downloading = False
                break

            # Request Downloads
            Endtime_Input: datetime = EndTime.tz_localize(None).to_pydatetime()

            if "tick" in BarObj.BarSize:
                await self.aSendRequest(
                    BarObj.BarSize, contract.symbol, Endtime_Input, "TRADES"
                )
                bars = self.ib.reqHistoricalTicks(
                    contract,
                    startDateTime=None,
                    endDateTime=Endtime_Input,
                    numberOfTicks=IntervalReq,
                    whatToShow="TRADES",
                    useRth=False,
                )
                self.ReqDict[self.ib.client._reqIdSeq] = [
                    contract.symbol,
                    "tick",
                    EndTime,
                ]
                if not bars:
                    break
                bars_df = ib_util.df(bars)

            elif BarObj.MergeAskBidTrades:
                bars_df: pd.DataFrame = pd.DataFrame()
                for AskBidTrade in ["ASK", "BID", "TRADES"]:
                    await self.aSendRequest(
                        BarObj.BarSize, contract.symbol, Endtime_Input, AskBidTrade
                    )
                    bars = await self.ib.reqHistoricalDataAsync(
                        contract,
                        endDateTime=Endtime_Input,
                        durationStr=IntervalReq,
                        barSizeSetting=BarObj.BarSize,
                        whatToShow=AskBidTrade,
                        useRTH=False,
                    )
                    self.ReqDict[self.ib.client._reqIdSeq] = [
                        contract.symbol,
                        BarObj.BarSize,
                        EndTime,
                    ]
                    if not bars:
                        break
                    df_AB = ib_util.df(bars)
                    df_AB = df_AB.set_index("date").add_prefix(AskBidTrade + "_")
                    bars_df = pd.concat([bars_df, df_AB], axis=1, sort=True)
            else:
                await self.aSendRequest(
                    BarObj.BarSize, contract.symbol, Endtime_Input, "TRADES"
                )
                bars = await self.ib.reqHistoricalDataAsync(
                    contract,
                    endDateTime=Endtime_Input,
                    durationStr=IntervalReq,
                    barSizeSetting=BarObj.BarSize,
                    whatToShow="TRADES",
                    useRTH=False,
                )
                self.ReqDict[self.ib.client._reqIdSeq] = [
                    contract.symbol,
                    BarObj.BarSize,
                    EndTime,
                ]
                if not bars:
                    break
                bars_df = ib_util.df(bars)
                bars_df = bars_df.set_index("date")

            if len(bars_df) == 0:
                break

            # Volume sanity check
            for col in bars_df.columns:
                if "vol" in col:
                    df_filtered = bars_df[bars_df[col] > 0]
                    if df_filtered.shape[0] > 0:
                        df_mod = df_filtered[df_filtered[col] % 100 == 0]
                        if df_filtered.shape[0] == df_mod.shape[0]:
                            print(bars_df)
                            MP.ErrorCapture(
                                __name__,
                                "Looks like changed from Lots to Share Size in volume col:"
                                + col,
                                180,
                                False,
                            )

            # Combine from each loop
            df = pd.concat([df, bars_df])

            # Check if finished
            if "tick" in BarObj.BarSize:
                EndTime = df["time"].min().astimezone(tz=pytz.timezone("US/Eastern"))
            else:
                _minidx = pd.Timestamp(df.index.min())
                EndTime = _minidx.tz_localize("US/Eastern")

            if not EndTime == EndTime:  # nan
                self.Downloading = False
                self.appendFailed(
                    contract.symbol,
                    NonExistant=BarObj.MultipleDays,
                    EarliestAvailBar=safe_date_to_string(EarliestAvailBar),
                )
                return "Failed"

            if StartTime == "" and len(df) >= BarObj.BarsReq:
                break

        # Save and Return
        self.Save_requestChecks()
        self.Downloading = False
        self.Sleep_TotalTime(FinishedSleeping=True)

        # Merge files if two files
        if not isinstance(prev_df, str) and len(df) > 0:
            if prev_df.index.max() >= df.index.min():
                df = pd.concat([prev_df, df], verify_integrity=False, sort=True)
                df = df[~df.index.duplicated(keep="first")]
            else:
                df = pd.concat([prev_df, df], verify_integrity=True, sort=True)

            if df.isnull().values.any():
                SaveExcel_ForReview(
                    df,
                    StrName=contract.symbol + "_" + BarObj.BarSize + "_" + EndTimeStr,
                )
                MP.ErrorCapture_ReturnAns(__name__, "Found null values", 60, True)

        # if more downloaded
        if len(df) > 0:
            if "tick" in BarObj.BarSize:
                df = df.reset_index().sort_values(
                    ["time", "index"], ascending=[True, True]
                )
                df = (
                    df.reset_index()
                    .rename(columns={"index": "idx"})
                    .drop(columns=["level_0"])
                )
                df["tickAttribLast"] = df["tickAttribLast"].astype(str)
            else:
                df = df.sort_values("date").reset_index()

            _out_path: Path = IB_Download_Loc(
                contract.symbol, BarObj, safe_date_to_string(StartTime)
            )
            df.to_feather(str(_out_path))
            self.appendDownloadable(
                contract.symbol,
                BarObj.BarSize,
                EarliestAvailBar=safe_date_to_string(EarliestAvailBar),
                StartDate=safe_date_to_string(StartTime),
                EndDate=safe_date_to_string(EndTime),
            )
            self.appendDownloaded(
                contract.symbol, bar_size=BarObj.BarSize, forDate=forDate
            )
            return df

        elif not isinstance(prev_df, str):
            self.appendDownloaded(
                contract.symbol, bar_size=BarObj.BarSize, forDate=forDate
            )
        else:
            self.appendFailed(
                contract.symbol,
                NonExistant=BarObj.MultipleDays,
                EarliestAvailBar=safe_date_to_string(EarliestAvailBar),
                BarSize=BarObj.BarSize,
                forDate=safe_date_to_string(forDate),
            )
            return

    def Download_Historical(
        self, contract: Any, BarSize: str, forDate: str = ""
    ) -> Any:  # noqa: N802, N803
        """Backward-compatible synchronous wrapper.
        Accepts original BarSize string, constructs BarObj, and runs the async implementation.
        """
        BarObj = BarCLS(BarSize)
        coro = self._download_historical_async(contract, BarObj, forDate)
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Use compat util.run if available to run coroutine
                try:
                    if hasattr(ib_util, "run"):
                        return ib_util.run(coro)  # type: ignore[arg-type]
                except Exception:
                    pass
                # Fallback: schedule and warn; cannot block current loop
                print(
                    "Warning: event loop is running; cannot block synchronously; returning None"
                )
                return None
            else:
                return loop.run_until_complete(coro)
        except RuntimeError:
            return asyncio.run(coro)


###############################################################################
#       Subscription Functions
###############################################################################
class MarketDepthCls:
    def __init__(self, ib: IBProto, contract: Any):
        self.ib = ib  # ib_async.IB()
        self.timeLast = perf_counter()
        self.timeLastsaved = perf_counter()

        self.contract = contract
        self.StockCode = contract.symbol
        self.ib.qualifyContracts(self.contract)

        self.StoredRows = 20
        self.ticker = self.ib.reqMktDepth(
            self.contract, numRows=self.StoredRows, isSmartDepth=True
        )  # numRows
        # self.ticker.updateEvent += self.Current_L2_df
        self.ticker.updateEvent += self.updateMktDepthL2_COPY

        df_cols = [
            "BidsSize",
            "BidsPrice",
            "bMarket",
            "AsksSize",
            "AsksPrice",
            "aMarket",
        ]
        Tick_cols = [
            "Recieved",
            "lastTime",
            "position",
            "Operation",
            "price",
            "size",
            "marketMaker",
        ]
        self.df_L2 = pd.DataFrame(columns=df_cols, index=range(0, self.StoredRows))
        self.df = self.df_L2  # Alias for compatibility
        self.df_Ticks = pd.DataFrame(columns=Tick_cols)

        self.StartStr = datetime.now(pytz.timezone("US/Eastern"))
        atexit_register(self.cancelMktDepth)

    def updateMktDepthL2_COPY(self, reqId: int):
        # operation: 0 = insert, 1 = update, 2 = delete
        # side: 0 = ask, 1 = bid
        ticks = self.ticker.domTicks

        for tick in ticks:
            self.df_Ticks = pd.concat(
                [
                    self.df_Ticks,
                    pd.DataFrame(
                        [
                            {
                                "Recieved": tick.time,
                                "position": tick.position,
                                "Operation": tick.operation,
                                "price": tick.price,
                                "size": tick.size,
                                "marketMaker": tick.marketMaker,
                            }
                        ]
                    ),
                ],
                ignore_index=True,
            )
        if self.timeLast + 5 > perf_counter():
            return
        self.timeLast = perf_counter()
        print(self.StockCode)
        print(self.df_Ticks)

        if self.timeLastsaved + 5 > perf_counter():
            self.timeLastsaved = perf_counter()
            self.Save_DepthData()

    def Display_L2(self, reqId: int):
        # IB.updateMktDepthL2()
        # operation: 0 = insert, 1 = update, 2 = delete
        # side: 0 = ask, 1 = bid

        ###Note: "clearing" of tick data appears to mostly be done in Wrapper.tcpDataArrived()

        if self.timeLast + 5 > perf_counter():
            return

        self.timeLast = perf_counter()

        bids = self.ticker.domBids
        for i in range(self.StoredRows):
            self.df.iloc[i, 0] = bids[i].size if i < len(bids) else 0
            self.df.iloc[i, 1] = bids[i].price if i < len(bids) else 0
            self.df.iloc[i, 2] = bids[i].marketMaker if i < len(bids) else ""

        asks = self.ticker.domAsks
        for i in range(self.StoredRows):
            self.df.iloc[i, 3] = asks[i].price if i < len(asks) else 0
            self.df.iloc[i, 4] = asks[i].size if i < len(asks) else 0
            self.df.iloc[i, 5] = bids[i].marketMaker if i < len(bids) else ""

        print(self.StockCode)
        print(self.df)

    def Save_DepthData(self):
        loc = IB_L2_Loc(
            self.StockCode,
            self.StartStr,
            self.EndStr,
            Normalised=False,
            fileExt=".ftr",
            CreateCxFile=False,
        )
        self.df_Ticks.to_feather(loc)
        # SaveExcel_ForReview(self.df_Ticks, StrName="Market Depth Data")

    def cancelMktDepth(self):
        self.EndStr = datetime.now(pytz.timezone("US/Eastern"))

        self.Save_DepthData()
        self.cleanup()

        self.ib.cancelMktDepth(self.contract)
        SaveExcel_ForReview(self.df, StrName="MarketDepthCurrent")

        print("Canceled Market Depth")

    def cleanup(self):
        """Cleanup method for MarketDepthCls"""
        # Add any cleanup logic here if needed
        pass


class TickByTickCls:
    def __init__(self, ib: IBProto, contract: Any):
        self.ib = ib  # ib_async.IB()

        self.contract = contract
        self.ib.qualifyContracts(self.contract)
        self.ticker = self.ib.reqTickByTickData(
            contract, tickType="AllLast", numberOfTicks=0, ignoreSize=False
        )
        self.ticker.updateEvent += self.onTickerUpdate

        self.df = pd.DataFrame()

    def onTickerUpdate(self, ticker):
        print(self.df)

    def cancel(self):
        self.ib.cancelTickByTickData(self.contract)
        SaveExcel_ForReview(self.df, StrName="TickByTick")


###############################################################################
#       Core Functions
###############################################################################
async def InitiateTWS(
    LiveMode: bool = False, clientId: int = 1, use_gateway: bool = True
):
    # launches Interactive Brokers Gateway/TWS and returns the IB() class ib
    # launches the requestCheckerCLS class and returns it Req

    if use_gateway:
        # IB Gateway ports (preferred for automated trading)
        if LiveMode:
            Code = 4001  # Gateway Live
        else:
            Code = 4002  # Gateway Paper Trading
        print(f"Connecting to IB Gateway on port {Code}...")
    else:
        # TWS ports (requires TWS to be running)
        if LiveMode:
            Code = 7496  # TWS Live
        else:
            Code = 7497  # TWS Paper Trading
        print(f"Connecting to TWS on port {Code}...")

    # Use shared async client instead of direct IB() instantiation
    try:
        from src.infra.ib_client import get_ib
    except ImportError:
        from src.infra.ib_client import get_ib

    ib = await get_ib()

    # Note: Gateway doesn't need setConnectOptions like TWS
    if not use_gateway:
        # TWS pacing throttling; guard for clients without this attribute
        try:
            if hasattr(ib, "client") and hasattr(ib.client, "setConnectOptions"):
                ib.client.setConnectOptions("+PACEAPI")
        except Exception:
            pass

    try:
        await ib.connectAsync("127.0.0.1", Code, clientId)
        print(f"Connected to {'Gateway' if use_gateway else 'TWS'}")
    except Exception as e:
        print(e)
        if use_gateway:
            error_msg = (
                "Is IB Gateway running? Check Gateway configuration and API settings"
            )
        else:
            error_msg = "Is TWS open in Live or Demo? Is ReadOnly off. Enable sockets"

        MP.ErrorCapture(
            __name__,
            error_msg,
            60,
            continueOn=False,
        )

    # ib.disconnectedEvent += lambda: asyncio.create_task(ib.connectAsync())
    Req = requestCheckerCLS("127.0.0.1", Code, clientId, ib)

    return ib, Req


def Initiate_Auto_Reconnect():
    import logging

    from ib_async.client import Client
    from ibapi.wrapper import EWrapper

    logging.basicConfig(level=logging.DEBUG)
    _logger = logging.getLogger("test_reconnect")

    class MyWrapper(EWrapper):
        def __init__(self):
            self.client = Client(self)
            self.client.apiError += self.apierror  # Use += for Event subscription

        def connect(self):
            try:
                self.client.connect("127.0.0.1", 4002, 99)
            except ConnectionRefusedError:
                _logger.error("Unable to connect")
                pass

        def apierror(self, msg):
            try:
                ib_async.util.patchAsyncio()  # Use ib_async.util instead of self.util
            except AttributeError:
                # patchAsyncio might not be available in all versions
                pass
            _logger.warning(
                f"apierror: {msg}, waiting 5 second and trying to reconnect"
            )
            asyncio.get_event_loop().call_later(5, self.connect)

    if __name__ == "__main__":
        mywrapper = MyWrapper()
        mywrapper.connect()
        mywrapper.client.run()


def WarriorList(LoadSave, df=None):
    if LoadSave == "Load":
        return pd.read_excel(
            "./Warrior/WarriorTrading_Trades.xlsx",
            sheet_name=0,
            header=0,
            engine="openpyxl",
        )  # dont change index, as each row could have duplicaes (same stock dif day)
    elif LoadSave == "Save":
        if df is not None:
            df.to_excel(
                "G:/Machine Learning/WarriorTrading_Trades.xlsx",
                sheet_name=0,
                index=False,
                engine="openpyxl",
            )
        else:
            MP.ErrorCapture(__name__, "DataFrame is None, cannot save to Excel", 180)
    else:
        MP.ErrorCapture(__name__, "Must select load or save", 180)


def TrainList_LoadSave(LoadSave, TrainType="Test", df=None):
    if LoadSave == "Load":
        try:
            return pd.read_excel(
                "G:/Machine Learning/Train_List-" + TrainType + ".xlsx",
                sheet_name=0,
                header=0,
                engine="openpyxl",
            )  # dont change index, as each row could have duplicaes (same stock dif day)
        except (FileNotFoundError, PermissionError, ValueError) as e:
            print(f"Warning: Could not load Train_List-{TrainType}.xlsx: {e}")
            # Return empty DataFrame with expected columns
            return pd.DataFrame(columns=["Stock", "DateStr"])
    elif LoadSave == "Save":
        if df is not None:
            df.to_excel(
                "G:/Machine Learning/Train_List-" + TrainType + ".xlsx",
                sheet_name="Sheet1",
                index=False,
                engine="openpyxl",
            )
        else:
            MP.ErrorCapture(__name__, "DataFrame is None, cannot save to Excel", 180)
    else:
        MP.ErrorCapture(__name__, "Must select load or save", 180)


def Stock_Downloads_Load(Req, contract, BarSize, forDate):
    if forDate == "":
        df_uncleaned = Req.Download_Historical(
            contract=contract, BarSize="1 sec", forDate=""
        )
        df_uncleaned = Req.Download_Historical(
            contract=contract, BarSize="30 min", forDate=""
        )
        df_uncleaned = Req.Download_Historical(
            contract=contract, BarSize="tick", forDate=""
        )
    else:
        df_uncleaned = Req.Download_Historical(
            contract=contract, BarSize="tick", forDate=""
        )

    return df_uncleaned


###############################################################################
#       File Locations
###############################################################################


def IB_Download_Loc(Stock_Code, BarObj, DateStr="", fileExt=".ftr") -> Path:
    # Delegate to centralized path service for consistent path building
    try:
        from .services.path_service import IB_Download_Loc as _svc
    except ImportError:
        from src.services.path_service import IB_Download_Loc as _svc
    return _svc(Stock_Code, BarObj, DateStr, fileExt)


def IB_Df_Loc(
    StockCode, BarObj, DateStr, Normalised: bool, fileExt=".ftr", CreateCxFile=False
):
    """Delegate to centralized PathService for consistent path building."""
    try:
        from .services.path_service import IB_Df_Loc as _svc
    except ImportError:
        from src.services.path_service import IB_Df_Loc as _svc
    return _svc(StockCode, BarObj, DateStr, Normalised, fileExt, CreateCxFile)


def IB_L2_Loc(
    StockCode, StartStr, EndStr, Normalised: bool, fileExt=".ftr", CreateCxFile=False
):
    # Delegate to centralized service
    try:
        from .services.path_service import IB_L2_Loc as _svc
    except ImportError:
        from src.services.path_service import IB_L2_Loc as _svc
    return _svc(StockCode, StartStr, EndStr, Normalised, fileExt, CreateCxFile)


def IB_Train_Loc(
    StockCode, DateStr, TrainXorY=""
):  # TrainX is Features, TrainY is Labels
    try:
        from .services.path_service import IB_Train_Loc as _svc
    except ImportError:
        from src.services.path_service import IB_Train_Loc as _svc
    return _svc(StockCode, DateStr, TrainXorY)


def IB_Scalar(scalarType, scalarWhat, LoadScalar=True, BarObj=None, FeatureStr=None):
    """Delegate to PathService.get_scalar_location for unified scalar paths/loading."""
    service = get_path_service()
    return service.get_scalar_location(
        scalarType,
        scalarWhat,
        bar_config=BarObj,
        feature_str=FeatureStr,
        load_scalar=LoadScalar,
    )


def SaveExcel_ForReview(df, StrName=""):
    if StrName == "":
        StrName = "For Review"

    try:
        from .services.path_service import get_path_service as _get_ps
    except ImportError:
        from src.services.path_service import get_path_service as _get_ps
    service = _get_ps()
    path_obj = service.get_excel_review_location(StrName)
    path = str(path_obj)

    for col in df.columns:
        if "datetime64[ns," in df[col].dtype.name:
            if getattr(df[col].dtype, "_tz", None) is not None:
                df[col] = df[col].dt.tz_convert("America/New_York")
                df[col] = df[col].dt.tz_localize(None)

    df.to_excel(path, sheet_name="Sheet1", index=False, engine="openpyxl")


if __name__ == "__main__":
    MP.SendTxt(f"Completed {__name__}")
