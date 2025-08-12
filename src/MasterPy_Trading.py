import os  # sent text, check files
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import (
    Path,
)  # Apple / and windows \
from time import perf_counter
from typing import Any

import pandas as pd
import pytz
from joblib import dump, load  # type: ignore[import-untyped]  # Missing stubs

# Import typed pandas helpers
from src.data.pandas_helpers import (  # type: ignore[import-not-found]  # Local module
    DataFrame,
    fillna_typed,
    load_excel,
    save_excel,
    sort_index_typed,
    sort_values_typed,
)
from src.types.project_types import HasStrftime  # type: ignore[import-not-found]  # Local module

try:
    import pandas_market_calendars as market_cal  # type: ignore[import-untyped]  # Missing stubs
except ImportError:
    # Optional dependency for market calendar functionality
    market_cal = None
    print("Note: pandas_market_calendars not available. Market calendar features disabled.")

try:
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from src.types.project_types import (  # type: ignore[import-not-found]  # Local module
        BarSize,
        DataFrame,
        HasSymbol,
        Series,
        Symbol,
    )
except ImportError:
    # Fallback types if project_types is not available
    from typing import Any
    Symbol = str  # type: ignore[misc]  # Fallback type
    BarSize = str  # type: ignore[misc]  # Fallback type
    HasSymbol = Any  # type: ignore[misc]  # Fallback type
    DataFrame = Any  # type: ignore
    Series = Any  # type: ignore

sys.path.append("..")
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

import asyncio
import signal
from atexit import register as atexit_register

import ib_async

Version = "V1"
if sys.platform == "win32":
    LocLocal = "C:\\Users\\Jason\\OneDrive\\Documents\\Python Files\\"
    LocG = "G:\\Machine Learning\\"
    LocG_Backup = "F:\\T7 Backup\\Machine Learning\\"
    LocDownloads = "D:\\Downloads\\"
    StockListLoc = "G:\\Machine Learning\\IB_StockList.ftr"
else:
    # Set default paths for non-Windows systems
    LocLocal = os.path.expanduser("~/Documents/Python Files/")
    LocG = os.path.expanduser("~/Machine Learning/")
    LocG_Backup = os.path.expanduser("~/T7 Backup/Machine Learning/")
    LocDownloads = os.path.expanduser("~/Downloads/")
    StockListLoc = os.path.expanduser("~/Machine Learning/IB_StockList.ftr")

###############################################################################
#       Helper Functions for Type Safety
###############################################################################

def safe_date_to_string(date_obj: Any) -> str:
    """Convert various date types to string format safely"""
    if isinstance(date_obj, str):
        return date_obj[:10] if len(date_obj) >= 10 else date_obj
    elif hasattr(date_obj, 'strftime'):
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
    elif hasattr(datetime_obj, 'strftime'):
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
    def __init__(self, BarStr_Full):

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

    def get_intervalReq(self, StartTime="", EndTime=""):
        if StartTime == "":
            # OLD IntervalReq = str(int(min([self.Interval_Max_Allowed, self.BarsReq])*self.Interval_mFactor))+self.Duration_Letter
            IntervalReq = (
                str(int(self.Interval_Max_Allowed * self.Interval_mFactor))
                + self.Duration_Letter
            )
        else:
            # Convert string times to pandas Timestamps for calculation
            try:
                if isinstance(StartTime, str):
                    StartTime = pd.Timestamp(StartTime)
                if isinstance(EndTime, str):
                    EndTime = pd.Timestamp(EndTime)

                # Calculate the difference using pandas timedelta
                time_diff = EndTime - StartTime
                if self.delta_letter == 'D':
                    Interval_Needed = int(time_diff.days)
                elif self.delta_letter == 'H':
                    Interval_Needed = int(time_diff.total_seconds() / 3600)
                elif self.delta_letter == 'M':
                    Interval_Needed = int(time_diff.total_seconds() / 60)
                elif self.delta_letter == 'S':
                    Interval_Needed = int(time_diff.total_seconds())
                else:
                    Interval_Needed = int(time_diff.total_seconds())
            except (ValueError, TypeError) as e:
                print(f"Warning: Error converting times in get_intervalReq: {e}")
                # Use default interval if conversion fails
                Interval_Needed = self.Interval_Max_Allowed
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
    def __init__(self):
        self.state = False
        signal.signal(signal.SIGINT, self.keyboardInterruptHandler)

    def exit(self):
        return self.state

    def keyboardInterruptHandler(self, signum, frame):
        print("Exit signal received...")
        self.state = True


class Market_InfoCLS:
    def __init__(self, StockMarket="NYSE"):
        if market_cal is None:
            print("Warning: Market calendar functionality unavailable without pandas_market_calendars")
            self.calandar = None
            self.Market_schedule = None
        else:
            self.calandar = market_cal.get_calendar(StockMarket)
            self.Market_schedule = self.calandar.schedule(
                start_date="2012-07-01", end_date="2030-01-01"
            )
        # self.Mark_open_days = self.calandar.valid_days(start_date='2012-07-01', end_date='2030-01-01')

    def is_Market_Open(self):
        if self.calandar is None:
            # Fallback: assume market is open during business hours (9 AM - 4 PM ET)
            from datetime import datetime, time
            now = datetime.now().time()
            return time(9, 0) <= now <= time(16, 0)
        return self.calandar.is_open_now(self.Market_schedule)

    def get_TradeDates(
        self, forDate, Bar, daysWanted=3
    ):  # Need type of bas, as only 1min is over several days
        if self.Market_schedule is None:
            # Fallback: generate simple date list
            from datetime import timedelta
            if Bar.BarType == "1 min":
                dates: list[str] = []
                current_date = forDate
                for _ in range(daysWanted):
                    # Simple weekday check (skip weekends)
                    while current_date.weekday() >= 5:  # Saturday = 5, Sunday = 6
                        current_date -= timedelta(days=1)
                    dates.append(current_date.strftime("%Y-%m-%d"))
                    current_date -= timedelta(days=1)
                return dates
            else:
                return [forDate.strftime("%Y-%m-%d")]

        if Bar.BarType == "1 min":
            OpenDates = self.Market_schedule[: forDate.strftime("%Y-%m-%d")]
            TradeDates = OpenDates[-daysWanted:]["market_close"]
            TradeDates = TradeDates.dt.tz_localize(None).tolist()
        else:
            TradeDates = [forDate.strftime("%Y-%m-%d")]

        return TradeDates

    def get_LastTradeDay(self, forDate):
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
    def __init__(self, host, port, clientId, ib):

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
            self.Loc_IBDlable = str(self.config.get_data_file_path("ib_downloadable_stocks"))
            self.Loc_IBDled = str(self.config.get_data_file_path("ib_downloaded_stocks"))
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

    def get_LastTradeDay(self, forDate):
        return self.NYSE.get_LastTradeDay(forDate)

    def get_TradeDates(self, forDate, daysWanted=None):
        return self.NYSE.get_TradeDates(forDate, daysWanted)

    def appendFailed(
        self,
        symbol: Symbol,
        NonExistant: bool = True,
        EarliestAvailBar: str = "",
        BarSize: BarSize = "",  # type: ignore
        forDate: str = "",
        comment: str = "",
    ) -> None:
        SaveMe = False

        if symbol == "":
            MP.ErrorCapture(
                __name__, "Symbol cannot be blank to AppendFailed List", 60, False
            )
            return

        # Check if DataFrame is None (safety check)
        if self.df_IBFailed is None:
            print("Warning: df_IBFailed is None, cannot append failed record")
            return

        # Convert EarliestAvailBar to string if it's a Timestamp
        if hasattr(EarliestAvailBar, 'strftime') and not isinstance(EarliestAvailBar, str):
            EarliestAvailBar = EarliestAvailBar.strftime("%Y-%m-%d %H:%M:%S")
        elif str(type(EarliestAvailBar)).find('Timestamp') >= 0:
            # Handle pandas Timestamp objects specifically
            EarliestAvailBar = str(EarliestAvailBar)
        elif EarliestAvailBar and not isinstance(EarliestAvailBar, str):
            EarliestAvailBar = str(EarliestAvailBar)

        # Convert forDate to string if needed
        if hasattr(forDate, 'strftime') and not isinstance(forDate, str):
            forDate = forDate.strftime("%Y-%m-%d %H:%M:%S")
        elif str(type(forDate)).find('Timestamp') >= 0:
            # Handle pandas Timestamp objects specifically
            forDate = str(forDate)
        elif forDate and not isinstance(forDate, str):
            forDate = str(forDate)

        if (
            BarSize == "" and comment != ""
        ):  # this was an error capture. Only add comment
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
                    if isinstance(EarliestAvailBar, datetime):
                        self.df_IBFailed.loc[
                            symbol, "EarliestAvailBar"
                        ] = EarliestAvailBar
                    elif isinstance(EarliestAvailBar, str):
                        if len(EarliestAvailBar) > 0:
                            self.df_IBFailed.loc[
                                symbol, "EarliestAvailBar"
                            ] = EarliestAvailBar

                if BarSize + "-LatestFailed" not in self.df_IBFailed.columns:
                    self.df_IBFailed.loc[symbol, BarSize + "-LatestFailed"] = forDate
                else:
                    try:
                        latest_failed = self.df_IBFailed.at[symbol, BarSize + "-LatestFailed"]
                        if pd.isnull(latest_failed):
                            self.df_IBFailed.loc[symbol, BarSize + "-LatestFailed"] = forDate
                        elif latest_failed > forDate:
                            self.df_IBFailed.loc[symbol, BarSize + "-LatestFailed"] = forDate
                    except (KeyError, IndexError):
                        self.df_IBFailed.loc[symbol, BarSize + "-LatestFailed"] = forDate

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

    def is_failed(self, symbol: Symbol, BarSize: BarSize, forDate: str = "") -> bool:  # type: ignore
        # Check if DataFrame is None (safety check)
        if self.df_IBFailed is None:
            print("Warning: df_IBFailed is None, cannot check if failed")
            return False

        if symbol not in self.df_IBFailed.index:  # Doesn't exist
            return False
        elif safe_df_scalar_check(self.df_IBFailed, symbol, "NonExistant", "Yes"):
            return True
        else:
            latest_failed = safe_df_scalar_access(self.df_IBFailed, symbol, BarSize + "-LatestFailed")
            if latest_failed is None:
                return False
            elif latest_failed >= forDate:
                return True
            else:
                return False

    async def getEarliestAvailBar(self, contract: Any) -> Any:
        # Check if DataFrames are None (safety check)
        if self.df_IBFailed is None or self.df_IBDownloadable is None:
            print("Warning: DataFrames not initialized, using fallback for EarliestAvailBar")
            # Fallback to API call
            self.SendRequest("", contract.symbol, "", "TRADES")
            # Use the ib instance that was passed in __init__
            EarliestAvailBar = await self.ib.reqHeadTimeStampAsync(
                contract, "TRADES", useRTH=False, formatDate=1
            )  # Outside hours, 1=non timezone aware
            self.ReqDict[self.ib.client._reqIdSeq] = [contract.symbol, "TRADES", ""]
        elif contract.symbol in self.df_IBFailed.index:
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

        try:
            # Simple conversion - let pandas handle the conversion
            EarliestAvailBar = pd.Timestamp(str(EarliestAvailBar))
        except:
            EarliestAvailBar = pd.Timestamp(year=2000, month=1, day=1)

        return EarliestAvailBar

    def avail2Download(self, symbol: Symbol, bar_size: BarSize, forDate: str = "") -> bool:
        # Check if DataFrame is None (safety check)
        if self.df_IBFailed is None:
            print("Warning: df_IBFailed is None, cannot check availability for download")
            return True  # Assume available if we can't check

        if isinstance(forDate, str) and forDate != "":
            try:
                forDate = datetime.strptime(forDate, "%Y-%m-%d %H:%M:%S")
            except:
                forDate = datetime.strptime(forDate, "%Y-%m-%d %H:%M:%S.%f")
        elif forDate == "":
            MP.ErrorCapture(__name__, "forDate in avail2Download is blank", 180, False)

        if symbol in self.df_IBFailed.index:
            if self.df_IBFailed.loc[symbol, "NonExistant"] == "Yes":
                return False
            elif forDate != "":
                # if len(self.df_IBFailed[(self.df_IBFailed['Stock']==symbol) & (self.df_IBFailed['DateStr']==symbol)]) == 1:
                earliest_avail = safe_df_scalar_access(self.df_IBFailed, symbol, "EarliestAvailBar")
                if earliest_avail and earliest_avail > forDate:
                    return False
                else:
                    if (
                        bar_size + "-LatestFailed" not in self.df_IBFailed.columns
                    ):  # No column fails recorded
                        return True
                    else:
                        latest_failed = safe_df_scalar_access(self.df_IBFailed, symbol, bar_size + "-LatestFailed")
                        if latest_failed is None:  # no fail recorded
                            return True
                        elif latest_failed < forDate:  # a date before an already known failed date
                            return False
                        else:
                            return True
            else:
                return True
        else:
            return True

    def Download_Exists(self, symbol: str, bar_size: str, forDate: str = "") -> bool:
        # Check if DataFrame is None (safety check)
        if self.df_IBDownloaded is None:
            print("Warning: df_IBDownloaded is None, cannot check if download exists")
            return False

        # MutliIndex
        # if not self.df_IBDownloaded.index.isin([(forDate, symbol)]).any(): #Doesn't exist
        #    return False
        # elif self.df_IBDownloaded.loc[(forDate, symbol), BarSize] == 'Yes':
        #    return True
        # elif self.df_IBDownloaded.loc[(forDate, symbol), BarSize] == 'TBA':
        #    return False
        # else:
        #    print("Unknown issue")

        if isinstance(forDate, str):
            date_str = forDate[:10]  # Take first 10 characters (YYYY-MM-DD)
        elif isinstance(forDate, (date, datetime)):
            date_str = forDate.strftime("%Y-%m-%d")
        else:
            date_str = str(forDate)[:10]

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
        # Check if DataFrame is None (safety check)
        if self.df_IBDownloaded is None:
            print("Warning: df_IBDownloaded is None, cannot append downloaded record")
            return

        if isinstance(forDate, str):
            date_str = forDate[:10]  # Take first 10 characters (YYYY-MM-DD)
        elif isinstance(forDate, (date, datetime)):
            date_str = forDate.strftime("%Y-%m-%d")
        else:
            date_str = str(forDate)[:10]

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
            self.df_IBDownloaded.loc[
                StockDate, bar_size
            ] = "Yes"  # immutable, should save itself.
            self.df_IBDownloaded.loc[
                StockDate, "Stock"
            ] = symbol  # immutable, should save itself.
            self.df_IBDownloaded.loc[
                StockDate, "Date"
            ] = forDate  # immutable, should save itself.
            self.df_IBDownloaded.loc[StockDate, :] = fillna_typed(
                self.df_IBDownloaded.loc[StockDate, :], "TBA"
            ).iloc[0]  # Get the Series back
        else:
            current_value = safe_df_scalar_access(self.df_IBDownloaded, StockDate, bar_size)
            if current_value is None:  # N.a
                self.df_IBDownloaded.loc[StockDate, bar_size] = "Yes"
            elif current_value == "TBA":  # [0] N.a
                self.df_IBDownloaded.loc[StockDate, bar_size] = "Yes"

        self.DownloadedChanges += 1
        return

    def appendDownloadable(
        self, symbol: str, bar_size: str, EarliestAvailBar: Any, StartDate: str | Any = "", EndDate: str | Any = ""
    ) -> None:
        SaveMe = False

        # Convert EarliestAvailBar to string if it's a Timestamp
        if hasattr(EarliestAvailBar, 'strftime') and not isinstance(EarliestAvailBar, str):
            EarliestAvailBar = EarliestAvailBar.strftime("%Y-%m-%d %H:%M:%S")
        elif str(type(EarliestAvailBar)).find('Timestamp') >= 0:
            EarliestAvailBar = str(EarliestAvailBar)
        elif EarliestAvailBar and not isinstance(EarliestAvailBar, str):
            EarliestAvailBar = str(EarliestAvailBar)

        # Convert StartDate to proper format
        if str(type(StartDate)).find('Timestamp') >= 0:
            # Convert Timestamp to string first, then back to datetime if needed for processing
            StartDate_str = str(StartDate)
            if StartDate_str != "":
                try:
                    StartDate = datetime.strptime(StartDate_str[:19], "%Y-%m-%d %H:%M:%S")
                except:
                    StartDate = pd.Timestamp(StartDate_str)
        elif isinstance(StartDate, str) and StartDate != "":
            try:
                StartDate = datetime.strptime(StartDate, "%Y-%m-%d %H:%M:%S")
            except:
                StartDate = datetime.strptime(StartDate, "%Y-%m-%d %H:%M:%S.%f")
        elif StartDate != "":
            # Convert to pandas Timestamp if needed for tz_localize
            StartDate = pd.Timestamp(StartDate)

        # Only tz_localize if it's a pandas Timestamp - more explicit type checking
        if StartDate != "":
            # Check if it's actually a pandas Timestamp before calling tz_localize
            if hasattr(StartDate, 'tz_localize') and hasattr(StartDate, 'tz'):
                try:
                    StartDate = StartDate.tz_localize(None)  # type: ignore
                except (AttributeError, TypeError):
                    # Fallback for datetime objects
                    if isinstance(StartDate, datetime) and StartDate.tzinfo is not None:
                        StartDate = StartDate.replace(tzinfo=None)
            elif isinstance(StartDate, datetime) and StartDate.tzinfo is not None:
                StartDate = StartDate.replace(tzinfo=None)

        # Convert EndDate to proper format
        if str(type(EndDate)).find('Timestamp') >= 0:
            # Convert Timestamp to string first, then back to datetime if needed for processing
            EndDate_str = str(EndDate)
            if EndDate_str != "":
                try:
                    EndDate = datetime.strptime(EndDate_str[:19], "%Y-%m-%d %H:%M:%S")
                except:
                    EndDate = pd.Timestamp(EndDate_str)

        if isinstance(EndDate, str) and EndDate != "":
            try:
                EndDate = datetime.strptime(EndDate, "%Y-%m-%d %H:%M:%S")
            except:
                EndDate = datetime.strptime(EndDate, "%Y-%m-%d %H:%M:%S.%f")
        elif EndDate != "":
            # Convert to pandas Timestamp if needed for tz_localize
            EndDate = pd.Timestamp(EndDate)

        # Only tz_localize if it's a pandas Timestamp
        if EndDate != "":
            # Check if it's actually a pandas Timestamp before calling tz_localize
            if hasattr(EndDate, 'tz_localize') and hasattr(EndDate, 'tz'):
                try:
                    EndDate = EndDate.tz_localize(None)  # type: ignore
                except (AttributeError, TypeError):
                    # Fallback for datetime objects
                    if isinstance(EndDate, datetime) and EndDate.tzinfo is not None:
                        EndDate = EndDate.replace(tzinfo=None)
            elif isinstance(EndDate, datetime) and EndDate.tzinfo is not None:
                EndDate = EndDate.replace(tzinfo=None)

        if bar_size + "-StartDate" not in self.df_IBDownloadable.columns:
            self.df_IBDownloadable[bar_size + "-StartDate"] = ""
        if bar_size + "-EndDate" not in self.df_IBDownloadable.columns:
            self.df_IBDownloadable[bar_size + "-EndDate"] = ""

        if symbol not in self.df_IBDownloadable.index:
            self.df_IBDownloadable.loc[symbol, bar_size + "-StartDate"] = StartDate
            self.df_IBDownloadable.loc[
                symbol, bar_size + "-EndDate"
            ] = EndDate  # only need to check once
            SaveMe = True
        else:
            start_date_val = safe_df_scalar_access(self.df_IBDownloadable, symbol, bar_size + "-StartDate")
            if start_date_val is None:
                self.df_IBDownloadable.loc[symbol, bar_size + "-StartDate"] = StartDate
                SaveMe = True
            elif start_date_val == "":
                self.df_IBDownloadable.loc[symbol, bar_size + "-StartDate"] = StartDate
                SaveMe = True
            elif start_date_val > StartDate:
                self.df_IBDownloadable.loc[symbol, bar_size + "-StartDate"] = StartDate
                SaveMe = True

        end_date_val = safe_df_scalar_access(self.df_IBDownloadable, symbol, bar_size + "-EndDate")
        if end_date_val is None:
            self.df_IBDownloadable.loc[symbol, bar_size + "-EndDate"] = EndDate
            SaveMe = True
        elif end_date_val == "":
            self.df_IBDownloadable.loc[symbol, bar_size + "-EndDate"] = EndDate
            SaveMe = True
        elif EndDate != "" and hasattr(EndDate, '__add__'):
            # Only do comparison if EndDate supports addition (not empty string)
            try:
                if end_date_val < EndDate + timedelta(milliseconds=1):
                    self.df_IBDownloadable.loc[symbol, bar_size + "-EndDate"] = EndDate
                    SaveMe = True
            except (TypeError, AttributeError):
                # If comparison fails, just update
                self.df_IBDownloadable.loc[symbol, bar_size + "-EndDate"] = EndDate
                SaveMe = True

        earliest_avail_val = safe_df_scalar_access(self.df_IBDownloadable, symbol, "EarliestAvailBar")
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

    def onErrorJR(self, reqId: int, errorId: int, errorStr: str, contract: Any) -> None:  # , contract):
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
                self.ib.sleep(self.SleepTot)
            except:
                pass  # in care event loop already running

    def SendRequest(self, timeframe, symbol, endDateTime, WhatToShow):

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

    def Save_requestChecks(self):
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

    def On_Exit(self):
        if self.On_Exit_Run > perf_counter() - 5:  # 5sec ago
            return

        if self.DownloadedChanges > 0:
            self.DownloadedChanges = 0
            self.df_IBDownloaded = sort_index_typed(self.df_IBDownloaded)
            # self.df_IBDownloaded.to_feather("G:/Machine Learning/IB Downloaded Stocks.ftr")
            save_excel(
                self.df_IBDownloaded,
                "G:/Machine Learning/IB Downloaded Stocks.xlsx",
                index=True
            )

        if self.DownloadableChanges > 0:
            self.DownloadableChanges = 0
            self.df_IBDownloadable = sort_values_typed(self.df_IBDownloadable, "Stock")
            # self.df_IBDownloadable.to_feather("G:/Machine Learning/IB Downloadable Stocks.ftr")
            save_excel(
                self.df_IBDownloadable,
                "G:/Machine Learning/IB Downloadable Stocks.xlsx",
                index=True
            )

        if self.FailChanges > 0:
            self.FailChanges = 0
            self.df_IBFailed = sort_values_typed(self.df_IBFailed, "Stock")
            # self.df_IBFailed.to_feather("G:/Machine Learning/IB Failed Stocks.ftr")
            save_excel(
                self.df_IBFailed,
                "G:/Machine Learning/IB Failed Stocks.xlsx",
                index=True
            )

        self.Save_requestChecks()

        print("Finished Request Exit Checks")
        self.On_Exit_Run = perf_counter()

    def keyboardInterruptHandler(self, signum, frame):
        print("")
        print("Exit flag triggered, will continue until current download finished...")
        self.Sleep_TotalTime()
        signal.signal(signal.SIGINT, signal.SIG_DFL)
        self.exitflag = True

    async def Download_Historical(self, contract, BarObj, forDate=""):

        # Wait for availability
        while self.Downloading:  # Already downloading
            Waiting2Download = max(self.SleepRem(), 0.1)
            print("Download Pause", Waiting2Download)
            self.ib.sleep(Waiting2Download)

        if self.exitflag:
            self.Sleep_TotalTime(FinishedSleeping=False)
            return

        self.Downloading = True

        #########################################################################################################################################
        # Set limits, and features of the bar type
        #########################################################################################################################################
        """if 'tick' in BarSize:
            Interval_Max_Allowed = 1000
            BarsReq = 1000
            MultipleDays = False
        elif 'sec' in BarSize:
            Interval_Max_Allowed = 2000#max interval is apparently 1800, but 2000 seems to be working.
            MergeAskBidTrades = True
            BarsReq = 60*30 #30min worth
            delta_letter = 's'
            Duration_Letter = ' S'
            Interval_mFactor = 1 #Same delta to duration
            MultipleDays = False
        elif 'min' in BarSize:
            if '30' in BarSize:
                Interval_Max_Allowed = 2000#24*2*28 #1month
                MergeAskBidTrades = False
                BarsReq = 5000 #Average bars in 365 days, 5000 from 'TWS Stats 30min 365 days.xlsx'
                delta_letter = 'h'
                Duration_Letter = ' D' #TWS request in x durations
                Interval_mFactor = 1/(2*24) #Hours to Days
                MultipleDays = True
            else:
                Interval_Max_Allowed = 2000#60*24 #1day
                MergeAskBidTrades = True
                BarsReq = 60*8 #8hours 1 trading day
                delta_letter = 'm'
                Duration_Letter = ' S' #TWS request in x durations
                Interval_mFactor = 60 #Minutes to Seconds
                MultipleDays = False
        elif 'hour' in BarSize:
            Interval_Max_Allowed = 2000
            MergeAskBidTrades = False
            BarsReq = 2500 #Average bars in 365 days
            delta_letter = 'h'
            Duration_Letter = ' D' #TWS request in x durations
            Interval_mFactor = 1/24 #Hours to Days
            MultipleDays = True
        elif 'day' in BarSize:
            Interval_Max_Allowed = 2000
            MergeAskBidTrades = False
            BarsReq = 10*365 #10 years? Probably never need this.
            delta_letter = 'D'
            Duration_Letter = ' D' #TWS request in x durations
            Interval_mFactor = 1 #Same delta to duration
            MultipleDays = True
        else:
            MP.ErrorCapture(__name__,'Bar Size not correct: '+BarSize, 60)"""

        #########################################################################################################################################
        # Determine Start and End of download required
        #########################################################################################################################################
        if forDate == "":  # For now (live trading or testing)
            if BarObj.MultipleDays:  # to download then
                StartTimeStr = (
                    datetime.strftime(datetime.today() - timedelta(400), "%Y-%m-%d")
                    + "T00:00"
                )  # at least 400 days ago to get enough bars
            else:
                StartTimeStr = datetime.strftime(datetime.now(), "%Y-%m-%d") + "T08:00"
            EndTimeStr = datetime.strftime(datetime.now(), "%Y-%m-%dT%H:%M")  # Now
        else:  # Historical Data
            if isinstance(forDate, str):
                DateStr = forDate
                forDate = datetime.strptime(forDate, "%Y-%m-%d")
            else:
                DateStr = datetime.strftime(forDate, "%Y-%m-%d")  # Yesterday

            if BarObj.MultipleDays:  # to download then
                StartTimeStr = (
                    datetime.strftime(forDate - timedelta(400), "%Y-%m-%d") + "T00:00"
                )  # at least 400 days for forDate to get enough bars
                EndTimeStr = DateStr + "T23:59"
            else:
                if "tick" in BarObj.BarSize:
                    StartTimeStr = DateStr + "T09:00"
                else:
                    StartTimeStr = DateStr + "T08:00"

                if "tick" in BarObj.BarSize:
                    EndTimeStr = DateStr + "T10:30"
                elif "sec" in BarObj.BarSize:
                    EndTimeStr = DateStr + "T12:00"
                elif "min" in BarObj.BarSize:
                    EndTimeStr = DateStr + "T16:00"

        EndTime = pd.Timestamp(EndTimeStr).tz_localize(
            tz="US/Eastern"
        )  # Localise from wherever

        if not self.NYSE.is_Market_Open():
            LastTradeDay = self.NYSE.get_LastTradeDay(EndTime).tz_localize(
                tz="US/Eastern"
            )
            if LastTradeDay < EndTime:
                EndTime = LastTradeDay

        #########################################################################################################################################
        # Get the start time from previous save, or set it.
        #########################################################################################################################################
        if os.path.exists(
            IB_Download_Loc(contract.symbol, BarObj.BarSize, EndTimeStr)
        ):  # Start time is the last in previous save
            prev_df = pd.read_feather(
                IB_Download_Loc(contract.symbol, BarObj.BarSize, StartTimeStr)
            )
            if BarObj.MultipleDays:
                prev_df = prev_df.set_index(
                    "date"
                )  # drop the integer index, and set to date like the bars_df
                StartTime = (
                    prev_df.index.max()
                )  # Start time to download is from the last of the previous saved. df['date'].max()
                StartTime = pd.Timestamp(StartTime)
            else:
                # Not programed to continue on where left off if not over multiple days
                self.Downloading = False
                EarliestAvailBar = self.getEarliestAvailBar(contract)
                if "time" in prev_df.columns:
                    StartTime = prev_df["time"].min()
                    EndTime = prev_df["time"].max()
                elif "date" in prev_df.columns:
                    StartTime = prev_df["date"].min()
                    EndTime = prev_df["date"].max()
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

            if StartTime >= (
                datetime.today().date() - pd.tseries.offsets.BDay(1)
            ):  # already downloaded
                # datetime.strftime(date.today()- timedelta(1),'%Y-%m-%d'):
                self.Downloading = False
                return

        else:  # Start time is the default
            StartTime = pd.Timestamp(
                StartTimeStr
            )  # , tz=TimeZoneStr) .tz_localize(tz='US/Eastern') #Localise from wherever
            prev_df = "Doesnt exist"

        EarliestAvailBar = self.getEarliestAvailBar(contract)
        StartTime = max(
            StartTime, EarliestAvailBar
        )  # only go as back as needed or exists (max)

        #########################################################################################################################################
        # Loop until completely downloaded
        #########################################################################################################################################

        # The final dataframe everything will merge into.
        df = pd.DataFrame()
        # Save Time Arrays
        self.Save_requestChecks

        if StartTime.tz == None:
            StartTime = StartTime.tz_localize(tz="US/Eastern")  # Localise
        if EndTime.tz == None:
            EndTime = EndTime.tz_localize(tz="US/Eastern")  # Localise

        while EndTime > StartTime or StartTime == "":

            IntervalReq = BarObj.IntervalReq
            if IntervalReq == 0:
                self.Downloading = False
                break  # return #Finished Downloading
            """if 'tick' in BarSize:
                IntervalReq = 1000
            elif StartTime == '':
                IntervalReq = str(int(min([Interval_Max_Allowed, BarsReq])*Interval_mFactor))+Duration_Letter
            else:
                Interval_Needed = int((EndTime - StartTime)/timedelta64(1, delta_letter))
                IntervalReq = str(int(min([Interval_Max_Allowed, Interval_Needed])*Interval_mFactor))+Duration_Letter
                #IntervalReqOld = str(int(min([Interval_Max_Allowed, Interval_Needed])/2/24))+Duration_Letter

                if IntervalReq == '0 D' or IntervalReq == '1 S':
                    self.Downloading = False
                    break #return #Finished Downloading
                if IntervalReq == '60 S' and BarSize == '1 min':
                    self.Downloading = False
                    break #return #Finished Downloading"""

            ######################################################################################################################################
            # Request Downloads
            ######################################################################################################################################
            Endtime_Input = EndTime.tz_localize(None)

            if "tick" in BarObj.BarSize:
                self.SendRequest(
                    BarObj.BarSize, contract.symbol, Endtime_Input, "TRADES"
                )  # pd.to_datetime(EndTime)
                bars = self.ib.reqHistoricalTicks(
                    contract,
                    startDateTime=None,
                    endDateTime=Endtime_Input,
                    numberOfTicks=IntervalReq,  # no startDateTime as its one OR the other. #pd.to_datetime(EndTime)
                    whatToShow="TRADES",
                    useRth=False,
                )  # inc outside hours, False then show all data
                self.ReqDict[self.ib.client._reqIdSeq] = [
                    contract.symbol,
                    "tick",
                    EndTime,
                ]

                if not bars:
                    break  # While loop

                bars_df = ib_async.util.df(bars)  # .set_index('time')

            elif BarObj.MergeAskBidTrades:
                bars_df = pd.DataFrame()
                for AskBidTrade in ["ASK", "BID", "TRADES"]:
                    self.SendRequest(
                        BarObj.BarSize, contract.symbol, Endtime_Input, AskBidTrade
                    )  # pd.to_datetime(EndTime)
                    bars = await self.ib.reqHistoricalDataAsync(
                        contract,
                        endDateTime=Endtime_Input,
                        durationStr=IntervalReq,  # pd.to_datetime(EndTime)
                        barSizeSetting=BarObj.BarSize,
                        whatToShow=AskBidTrade,
                        useRTH=False,
                    )  # inc outside hours False then show all data
                    self.ReqDict[self.ib.client._reqIdSeq] = [
                        contract.symbol,
                        BarObj.BarSize,
                        EndTime,
                    ]

                    if not bars:
                        break  # While loop. Finished downloading.

                    # Merge ASK, BID, and TRADES
                    df_AB = ib_async.util.df(bars)
                    if df_AB is None:
                        break  # While loop - no data returned
                    df_AB = df_AB.set_index("date")
                    df_AB = df_AB.add_prefix(AskBidTrade + "_")
                    bars_df = pd.concat(
                        [bars_df, df_AB], axis=1, sort=True
                    )  # pd.concat([bars_df,df], join='inner',verify_integrity=True,sort=True) # merge
            else:
                self.SendRequest(
                    BarObj.BarSize, contract.symbol, Endtime_Input, "TRADES"
                )
                bars = await self.ib.reqHistoricalDataAsync(
                    contract,
                    endDateTime=Endtime_Input,
                    durationStr=IntervalReq,  # pd.to_datetime(EndTime)
                    barSizeSetting=BarObj.BarSize,
                    whatToShow="TRADES",
                    useRTH=False,
                )  # inc outside hours
                self.ReqDict[self.ib.client._reqIdSeq] = [
                    contract.symbol,
                    BarObj.BarSize,
                    EndTime,
                ]
                if not bars:
                    break  # While loop
                bars_df = ib_async.util.df(bars)
                if bars_df is None:
                    break  # While loop - no data returned
                bars_df = bars_df.set_index("date")

            if bars_df is None or len(bars_df) == 0:
                break  # While loop. Finished.

            # Check if volumes changed from lots of 100 to shares
            for col in bars_df.columns:
                if "vol" in col:
                    df_filtered = bars_df[bars_df[col] > 0]
                    if df_filtered.shape[0] > 0:
                        df_filtered_mod = df_filtered[df_filtered[col] % 100 == 0]
                        if (
                            df_filtered.shape[0] == df_filtered_mod.shape[0]
                        ):  # =bars_df.shape[0]:
                            print(bars_df)
                            MP.ErrorCapture(
                                __name__,
                                "Looks like changed from Lots to Share Size in volume col:"
                                + col,
                                180,
                                False,
                            )

            # Combine from each loop
            df = pd.concat([df, bars_df])  # , verify_integrity=True,sort=True)

            # Check if finished
            if "tick" in BarObj.BarSize:
                EndTime = df["time"].min()
                EndTime = EndTime.astimezone(tz=pytz.timezone("US/Eastern"))
            else:
                EndTime = df.index.min()
                EndTime = EndTime.tz_localize("US/Eastern")

            if not EndTime == EndTime:  # nan
                self.Downloading = False
                self.appendFailed(
                    contract.symbol,
                    NonExistant=BarObj.MultipleDays,
                    EarliestAvailBar=safe_date_to_string(EarliestAvailBar),
                )  # if multiple days failed, then non-existant also true
                return "Failed"  # End requesting
            if (
                StartTime == "" and len(df) >= BarObj.BarsReq
            ):  # no start/end specified but have enough bars for ML
                break  # while loop

        #########################################################################################################################################
        # Save and Return
        #########################################################################################################################################
        self.Save_requestChecks()  # Save Time Arrays
        self.Downloading = False  # Ending no matter what
        self.Sleep_TotalTime(FinishedSleeping=True)

        # Merge files if two files
        if not isinstance(prev_df, str) and len(df) > 0:  # previous file to merge with.
            if prev_df.index.max() >= df.index.min():  # there is an overlap in grabbing
                df = pd.concat(
                    [prev_df, df], verify_integrity=False, sort=True
                )  # There is overlap, we already know this hence verify =false
                df = df[~df.index.duplicated(keep="first")]
            else:
                df = pd.concat([prev_df, df], verify_integrity=True, sort=True)

            # Check for errors
            if df.isnull().values.any():  # if null values save a check file
                SaveExcel_ForReview(
                    df,
                    StrName=contract.symbol + "_" + BarObj.BarSize + "_" + EndTimeStr,
                )
                MP.ErrorCapture_ReturnAns(__name__, "Found null values", 60, True)

        # if more downloaded
        if (
            len(df) > 0
        ):  # then something was downloaded. Otherwise the prev_df is untouched.

            # Sort and clean the dataframe a little from merges
            if "tick" in BarObj.BarSize:
                # there are multiple lines for each second. Need to keep the order.
                df = df.reset_index()
                df = df.sort_values(["time", "index"], ascending=[True, True])
                df = df.reset_index()
                df = df.rename(columns={"index": "idx"})
                df = df.drop(columns=["level_0"])
                df["tickAttribLast"] = df["tickAttribLast"].astype(str)
            else:
                df = df.sort_values("date")
                df = df.reset_index()

            # df.to_excel(IB_Download_Loc(contract.symbol, BarObj.BarSize, StartTime,'.xlsx'), sheet_name='Sheet1',engine='openpyxl') #, index=True)
            # df.to_csv(IB_Download_Loc(contract.symbol, BarObj.BarSize, StartTime,'.csv')) #index is date, so save with index....

            df.to_feather(IB_Download_Loc(contract.symbol, BarObj.BarSize, safe_date_to_string(StartTime)))
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

        elif not isinstance(prev_df, str):  # prev exists but nothing new downloaded
            # self.appendDownloadable(contract.symbol, BarSize, EarliestAvailBar=EarliestAvailBar, StartDate=prev_df.index.min(), EndDate=prev_df.index.max())
            self.appendDownloaded(
                contract.symbol, bar_size=BarObj.BarSize, forDate=forDate
            )
        else:  # no previous and no download
            self.appendFailed(
                contract.symbol,
                NonExistant=BarObj.MultipleDays,
                EarliestAvailBar=safe_date_to_string(EarliestAvailBar),
                BarSize=BarObj.BarSize,
                forDate=safe_date_to_string(forDate),
            )  # if multiple days failed, then non-existant also true
            return


###############################################################################
#       Subscription Functions
###############################################################################
class MarketDepthCls:
    def __init__(self, ib, contract):
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
            self.df_Ticks = pd.concat([
                self.df_Ticks,
                pd.DataFrame([{
                    "Recieved": tick.time,
                    "position": tick.position,
                    "Operation": tick.operation,
                    "price": tick.price,
                    "size": tick.size,
                    "marketMaker": tick.marketMaker,
                }])
            ], ignore_index=True)
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
    def __init__(self, ib, contract):
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
async def InitiateTWS(LiveMode=False, clientId=1, use_gateway=True):
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
        ib.client.setConnectOptions("+PACEAPI")  # TWS Pacing Throttling

    try:
        await ib.connectAsync("127.0.0.1", Code, clientId)
        print(f"Connected to {'Gateway' if use_gateway else 'TWS'}")
    except Exception as e:
        print(e)
        if use_gateway:
            error_msg = "Is IB Gateway running? Check Gateway configuration and API settings"
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


def IB_Download_Loc(Stock_Code, BarObj, DateStr="", fileExt=".ftr"):

    if "." not in fileExt:
        fileExt = "." + fileExt

    # Convert DateStr if it's a Timestamp
    if str(type(DateStr)).find('Timestamp') >= 0:
        DateStr = str(DateStr)
    elif hasattr(DateStr, 'strftime') and not isinstance(DateStr, str):
        DateStr = DateStr.strftime("%Y-%m-%d %H:%M:%S")

    if BarObj.BarType == 0:  # Tick
        BarStr = "_Tick"
    elif BarObj.BarType == 1:  # 1 Second
        BarStr = "_1s"
    elif BarObj.BarType == 2:  # 1 Min
        BarStr = "_1M"
    elif BarObj.BarType == 3:  # 30 Min
        BarStr = "_30M"
    elif BarObj.BarType == 4:  # 1 Hour
        BarStr = "_1Hour"  # no underscore as no date string
    elif BarObj.BarType == 5:  # 1 Day
        BarStr = "_1D"  # no underscore as no date string
    else:
        MP.ErrorCapture(__name__, "Timeframe must be day/hour/minute/second/tick")

    if BarObj.BarType <= 2:  # then need a start date and end date string in file name
        if DateStr == "":
            MP.ErrorCapture(__name__, "need start and end string")

        if isinstance(DateStr, (date, datetime)):
            DateStr = "_" + DateStr.strftime("%Y-%m-%d")
        else:
            DateStr = (
                "_" + str(DateStr)[:10]
            )  # Start to 10th letter incase of format YYYY-MM-DDTHH:MM:SS

    else:  # then dont need a date string, as it is forever*
        DateStr = ""

    if "." not in fileExt:
        fileExt = "." + fileExt

    LocPathNew = Path(
        LocG + "IBDownloads\\" + Stock_Code + "_USUSD" + BarStr + DateStr + fileExt
    )  # DD.MM.YYYY

    return LocPathNew


def IB_Df_Loc(
    StockCode, BarObj, DateStr, Normalised: bool, fileExt=".ftr", CreateCxFile=False
):
    if CreateCxFile:
        Loc = LocG + "/CxData - "
        if fileExt != ".xlsx":
            MP.ErrorCapture(
                __name__, "This should be a xlsx file if its a Chech file", 60, True
            )
    else:
        Loc = LocG + "Stocks/" + StockCode + "/Dataframes/"
    MP.LocExist(Loc)

    if BarObj.BarType <= 2:
        if DateStr == "":
            MP.ErrorCapture(__name__, "ticks need start and end string")

        if isinstance(DateStr, date):
            DateStr = "_" + DateStr.strftime("%Y-%m-%d")
        else:
            DateStr = (
                "_" + DateStr[:10]
            )  # Start to 10th letter incase of format YYYY-MM-DDTHH:MM:SS

    else:  # then dont need a date string, as it is forever*
        DateStr = ""

    if Normalised:
        Norm_df = "_NORM"
    elif not Normalised:
        Norm_df = "_df"

    if "." not in fileExt:
        fileExt = "." + fileExt

    FileName = StockCode + BarObj.BarStr + Norm_df + "_" + Version + DateStr + fileExt

    return Path(Loc + FileName)


def IB_L2_Loc(
    StockCode, StartStr, EndStr, Normalised: bool, fileExt=".ftr", CreateCxFile=False
):
    if CreateCxFile:
        Loc = LocG + "/CxData - "
        if fileExt != ".xlsx":
            MP.ErrorCapture(
                __name__, "This should be a xlsx file if its a Chech file", 60, True
            )
    else:
        Loc = LocG + "Stocks/" + StockCode + "/Dataframes/"
    MP.LocExist(Loc)

    if isinstance(StartStr, date):
        StartStr = "_" + StartStr.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(EndStr, date):
        EndStr = "_" + EndStr.strftime("%H:%M:%S")

    if Normalised:
        Norm_df = "_NORM"
    elif not Normalised:
        Norm_df = "_df"

    if "." not in fileExt:
        fileExt = "." + fileExt

    FileName = (
        StockCode
        + "_L2_"
        + Norm_df
        + "_"
        + Version
        + StartStr
        + " to "
        + EndStr
        + fileExt
    )

    return Path(Loc + FileName)


def IB_Train_Loc(
    StockCode, DateStr, TrainXorY=""
):  # TrainX is Features, TrainY is Labels
    if "y" in TrainXorY.lower() or "label" in TrainXorY.lower():
        TrainXorY = "TrainY"
    elif "x" in TrainXorY.lower() or "feature" in TrainXorY.lower():
        TrainXorY = "TrainX"
    else:
        MP.ErrorCapture(__name__, "Could not determine if it is a Feature or Label")

    Loc = LocG + "Stocks/" + StockCode + "/Dataframes/"
    MP.LocExist(Loc)

    FileName = (
        StockCode
        + "_1s_"
        + TrainXorY
        + "_"
        + Version
        + "_"
        + DateStr.strftime("%Y%m%d")
        + ".ftr"
    )

    return Path(Loc + FileName)


def IB_Scalar(scalarType, scalarWhat, LoadScalar=True, BarObj=None, FeatureStr=None):

    Loc = LocG + "/Scalars/"
    MP.LocExist(Loc)

    if "st" in scalarType.lower():
        scalarType = "Std"
    elif "min" in scalarType.lower():
        scalarType = "MinMax"
    else:
        MP.ErrorCapture(__name__, "Scalar type needs to be Standard or Min Max.")

    if FeatureStr != None:
        scalarFor = "Fr"
        if "float" in scalarWhat[0].lower():
            scalarWhat = "float_"
        elif "outstanding" in scalarWhat[0].lower():
            scalarWhat = "outstanding-shares_"
        elif "short" in scalarWhat[0].lower():
            scalarWhat = "shares-short_"
        elif "volume" in scalarWhat[0].lower():
            scalarWhat = "av-volume"
        else:
            MP.ErrorCapture(__name__, "Scalar type needs to be for Prices or Volumes")
    elif BarObj != None:
        scalarFor = BarObj.BarStr
        if scalarWhat[0].lower() == "p":
            scalarWhat = "prices"
        elif scalarWhat[0].lower() == "v":
            scalarWhat = "volumes"
        else:
            MP.ErrorCapture(__name__, "Scalar type needs to be for Prices or Volumes")
    else:
        MP.ErrorCapture(__name__, "Scalar needs a BarObf or a FeatureStr")

    FileName = f"scaler_{scalarType}{scalarFor}_{scalarWhat}.bin"

    if LoadScalar:
        return load(Path(Loc + FileName))  # Scalar
    else:
        return Path(Loc + FileName)  # Path


def SaveExcel_ForReview(df, StrName=""):
    if StrName == "":
        StrName = "For Review"

    path = f"G:/Machine Learning/Temp-{StrName}.xlsx"
    count = 1
    while os.path.exists(path):
        count += 1
        path = f"G:/Machine Learning/Temp-{StrName}-{count}.xlsx"

    for col in df.columns:
        if (
            "datetime64[ns," in df[col].dtype.name
        ):  # if there is no comma then it is localised already
            if df[col].dtype._tz is not None:
                df[col] = df[col].dt.tz_convert("America/New_York")
                df[col] = df[col].dt.tz_localize(None)

    df.to_excel(path, sheet_name="Sheet1", index=False, engine="openpyxl")


if __name__ == "__main__":

    MP.SendTxt(f"Completed {__name__}")
