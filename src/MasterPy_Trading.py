from __future__ import annotations

"""
Minimal legacy compatibility module.

This file formerly contained a very large set of classes & utilities. It has
been reduced to only the legacy pieces still referenced by tests or external
code during the migration window:
  * BarCLS               (interval duration helper used in tests)
  * requestCheckerCLS    (thin stub retaining only Download_Historical)

All pacing logic, market info, tracking, and historical data workflows have
been migrated to dedicated service modules under src.services.*

Pending removal: requestCheckerCLS stub (scheduled once downstream code
fully migrates to services.request_manager_service & historical data service).
"""


import pandas as pd

try:  # Import original helper for error capture (legacy pattern)
    from . import MasterPy as MP  # type: ignore
except Exception:  # pragma: no cover - script context
    import MasterPy as MP  # type: ignore  # noqa: F401

try:  # Graceful exit (re-export for backward compatibility)
    from .utils.exit_handler import GracefulExiterCLS  # type: ignore  # noqa: F401
except Exception:  # pragma: no cover
    from src.utils.exit_handler import GracefulExiterCLS  # type: ignore  # noqa: F401

Version = "V1"


class BarCLS:
    """Slimmed legacy bar descriptor retained for interval request tests."""

    def __init__(self, BarStr_Full: str):  # noqa: N803 (legacy arg name)
        self.BarStr_Full = BarStr_Full.lower()
        self.BarSize = BarStr_Full
        if "tick" in self.BarStr_Full:
            self.BarType = 0
        elif self.BarStr_Full in {"1 sec", "1 second"}:
            self.BarType = 1
        elif "min" in self.BarStr_Full:
            if self.BarStr_Full.startswith("1 "):
                self.BarType = 2
            elif self.BarStr_Full.startswith("30 "):
                self.BarType = 3
            else:
                self.BarType = 2
        elif "hour" in self.BarStr_Full:
            self.BarType = 4
        elif "day" in self.BarStr_Full:
            self.BarType = 5
        else:
            self.BarType = 2

    def get_intervalReq(self, StartTime="", EndTime=""):  # noqa: N802 (legacy)
        """Return legacy-style IB duration string for interval between timestamps.

        Returns either:
          * "<seconds> S" for sub-day durations
          * "<days> D"    for day-or-longer
          * 0             for exactly 60 seconds (legacy quirk)
          * "0 S"         for invalid / negative intervals
        """
        try:
            # Accept str, datetime, pandas Timestamp. Coerce anything non-Timestamp.
            if not isinstance(StartTime, pd.Timestamp):
                StartTime = pd.to_datetime(StartTime, errors="coerce")
            if not isinstance(EndTime, pd.Timestamp):
                EndTime = pd.to_datetime(EndTime, errors="coerce")
            if StartTime is pd.NaT or EndTime is pd.NaT:
                return "0 S"
            delta = EndTime - StartTime
            if delta.total_seconds() < 0:
                return "0 S"
            seconds = int(delta.total_seconds())
            if seconds == 60:
                return 0
            if seconds < 86400:
                return f"{seconds} S"
            days = max(1, delta.days)
            return f"{days} D"
        except Exception:
            return "0 S"


class requestCheckerCLS:  # pragma: no cover - deprecated adapter
    """Deprecated stub retaining only Download_Historical adapter.

    All pacing, market info, and tracking logic have migrated to:
      * RequestManagerService
      * MarketInfoService
      * DownloadTracker
    """

    def __init__(self, ib=None, **_):  # accept legacy args silently
        self.ib = ib
        self.exitflag = False

    def On_Exit(self):  # noqa: N802 - legacy name retained
        return

    def keyboardInterruptHandler(self, *_):  # legacy signature
        self.exitflag = True
        return

    def Download_Historical(  # noqa: N802 (legacy name)
        self, contract=None, BarObj=None, BarSize=None, forDate: str = ""
    ):
        """Delegate to HistoricalDataService for backward compatibility."""
        try:
            from src.services.historical_data_service import (
                BarSize as BarSizeEnum,
            )
            from src.services.historical_data_service import (
                DataType,
                DownloadRequest,
                HistoricalDataService,
            )
        except Exception as e:  # pragma: no cover - defensive
            MP.ErrorCapture_ReturnAns(
                __name__, f"Historical service import failed: {e}", 60, False
            )
            return None

        bar_size_str: str | None = None
        if BarObj is not None and hasattr(BarObj, "BarSize"):
            bar_size_str = BarObj.BarSize
        if BarSize and not bar_size_str:
            bar_size_str = BarSize
        if bar_size_str is None:
            MP.ErrorCapture_ReturnAns(__name__, "Bar size not provided", 60, False)
            return None

        mapping = {
            "1 sec": BarSizeEnum.SEC_1,
            "5 secs": BarSizeEnum.SEC_5,
            "10 secs": BarSizeEnum.SEC_10,
            "30 secs": BarSizeEnum.SEC_30,
            "1 min": BarSizeEnum.MIN_1,
            "5 mins": BarSizeEnum.MIN_5,
            "15 mins": BarSizeEnum.MIN_15,
            "30 mins": BarSizeEnum.MIN_30,
            "1 hour": BarSizeEnum.HOUR_1,
            "1 day": BarSizeEnum.DAY_1,
        }
        bar_enum = mapping.get(bar_size_str, BarSizeEnum.MIN_1)

        symbol: str | None = None
        if contract is not None:
            symbol = getattr(contract, "symbol", None) or getattr(
                contract, "localSymbol", None
            )
        if not symbol:
            MP.ErrorCapture_ReturnAns(
                __name__, "Contract symbol not provided", 60, False
            )
            return None

        service = HistoricalDataService()
        connection = getattr(self, "ib", None)
        if connection is None:
            MP.ErrorCapture_ReturnAns(__name__, "No IB connection available", 60, False)
            return None

        request = DownloadRequest(
            symbol=symbol,
            bar_size=bar_enum,
            what_to_show=DataType.TRADES,
            end_date=forDate or None,
        )
        result = service.download_historical_data(connection, request)
        if getattr(result, "success", False):
            return result.data
        return None


###############################################################################
#       Subscription Functions
###############################################################################
if __name__ == "__main__":
    MP.SendTxt(f"Completed {__name__}")
