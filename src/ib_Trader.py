# ruff: noqa: N802,N803,N806,N817  # Legacy names preserved for compatibility
# IB_Trader
# A new API generic tick for realtime news is available via generic tick 292. Also requesting topic news is possible by providing the news source as the exchange. To see all available topics for a source enter "*" for the symbol.

# Time Issues
# Set time on login screen.
# Time is set to New York as I am only trading there....
# To test ML for other markets will need to apply the correct time from 'US/Eastern' to 'whatever'

# US SMASRT RESULTS IN THE BEST DATA

# from ib_async import *
from datetime import datetime
from pathlib import Path
from time import perf_counter
from typing import Any

import pandas as pd
import pytz  # TimeZone
from ib_async import Stock

try:
    # Try relative import first (when used as package)
    from . import MasterPy as MP
    from .utils.ib_connection_helper import get_ib_connection_sync
except ImportError:
    # Fall back to absolute import (when used as script)
    import MasterPy as MP
    from src.utils.ib_connection_helper import get_ib_connection_sync


class StockWatch:
    def __init__(self, ib: Any, StockCode: str) -> None:
        self.StockCode = StockCode
        self.contract = Stock(StockCode, "SMART", "USD")
        self.LiveStream = False
        self.ib = ib  # Store the IB connection

        # Initiate Hourly
        hourly_path = Path(MP.Download_loc_IB(self.StockCode, "1 hour"))
        if hourly_path.exists():
            self.df_hour = pd.read_excel(
                hourly_path,
                sheet_name=0,
                header=0,
                engine="openpyxl",
            )
        else:
            # Note: Stock_Downloads_Load needs proper Req object, using placeholder for now
            self.df_hour = None

        # Initiate Second
        now_str = self.NowStr()
        sec_path = Path(MP.Download_loc_IB(self.StockCode, "1 sec", now_str))
        if sec_path.exists():
            self.df_sec = pd.read_excel(
                sec_path,
                sheet_name=0,
                header=0,
                engine="openpyxl",
            )
        else:
            # Note: Stock_Downloads_Load needs proper Req object, using placeholder for now
            self.df_sec = None

        # Initiate Tick only on activation
        tick_path = Path(MP.Download_loc_IB(self.StockCode, "tick", now_str))
        if tick_path.exists():
            self.df_tick = pd.read_excel(
                tick_path,
                sheet_name=0,
                header=0,
                engine="openpyxl",
            )
        else:
            # Note: Stock_Downloads_Load should be MPT function and needs proper Req object
            self.df_tick = None

    def NowStr(self):
        return datetime.now(pytz.timezone("US/Eastern")).strftime("%Y-%m-%dT%H:%M:%S")

    def LevelII(self):
        if hasattr(self.ib, "reqMktDepthExchanges"):
            _exchanges = self.ib.reqMktDepthExchanges()
            self.ib.reqMktDepth(self.contract, numRows=5, isSmartDepth=False)
        else:
            MP.log_warning("StockWatch", "IB connection does not support Level II data")

    def Create_DataStream(self):
        self.LiveStream = True
        if hasattr(self.ib, "reqTickByTickData"):
            self.Ticker_BidAsk = self.ib.reqTickByTickData(
                self.contract, tickType="BidAsk", numberOfTicks=0, ignoreSize=False
            )
            self.Ticker_AllLast = self.ib.reqTickByTickData(
                self.contract, tickType="AllLast", numberOfTicks=0, ignoreSize=False
            )
        else:
            MP.log_warning(
                "StockWatch", "IB connection does not support tick-by-tick data"
            )

    def StockDownloader(self):
        print("x")

    def __del__(self):
        # cancel data stream
        if self.LiveStream and hasattr(self.ib, "cancelTickByTickData"):
            try:
                self.ib.cancelTickByTickData(self.contract, "BidAsk")
                self.ib.cancelTickByTickData(self.contract, "AllLast")
                self.ib.cancelMktDepth(self.contract)
            except Exception as e:
                MP.log_warning("StockWatch", f"Error canceling data streams: {e}")

        # save files (if dataframes exist)
        try:
            if hasattr(self, "df_hour") and self.df_hour is not None:
                self.df_hour.to_excel(
                    MP.Download_loc_IB(self.StockCode, "1 hour"),
                    sheet_name="Sheet1",
                    engine="openpyxl",
                    index=True,
                )
            if hasattr(self, "df_sec") and self.df_sec is not None:
                self.df_sec.to_excel(
                    MP.Download_loc_IB(self.StockCode, "1 sec", self.NowStr()),
                    sheet_name="Sheet1",
                    engine="openpyxl",
                    index=True,
                )
            if hasattr(self, "df_tick") and self.df_tick is not None:
                self.df_tick.to_excel(
                    MP.Download_loc_IB(self.StockCode, "tick", self.NowStr()),
                    sheet_name="Sheet1",
                    engine="openpyxl",
                    index=True,
                )
        except Exception as e:
            MP.log_warning("StockWatch", f"Error saving files: {e}")

        print(self.StockCode, "Ended")


class OrderManager:
    def __init__(self, StockCode: str, ModelLabels: Any, PriceNow: float) -> None:
        self.StockCode = StockCode
        self.PriceStart = PriceNow
        self.ModelLabel = ModelLabels
        self.ModelResult = ModelLabels

        if self.ModelLabel[:3] > 0.5:
            self.Entry = True
            self.Exit = False
            self.OrdeType = "LimitOrder"
        elif self.ModelLabel[4:] > 0.5:
            self.Entry = False
            self.Exit = True
        else:
            self.Hold = True
            self.Entry = False
            self.Exit = False

        self.CreateOrder()

    def CreateOrder(self):
        self.TimeStart = perf_counter()
        self.Filled = False
        self.change = False

        while not self.Filled:
            if self.Entry:
                self.Target = self.PriceStart * 1.1

            if self.Exit:
                if self.ModelLabel[4:] > 0.5:
                    print("MarketOrder")
                else:
                    print("LimitOrder")

            if perf_counter() - self.TimeStart >= 10:
                self.Exit = True

            # Use time.sleep instead of ib.sleep
            import time

            time.sleep(0.1)
            print("CheckOrderFillment")

    def CheckOrderFillment(self):
        print("RunTickerModel")

        if self.change:
            print("CancelPending")
            print("CreateOrder")


class DataPipeline:
    def __init__(self):
        print("DataPipeline initialized")


def WatchList(ib: Any, contract: Any) -> None:
    """Watch list function - needs proper IB connection."""
    if hasattr(ib, "reqMktData"):
        ib.reqMktData(
            contract,
            genericTickList=[
                "165",
                "221",
                "233",
                "236",
                "258",
                "293",
                "295",
                "375",
                "411",
            ],
            snapshot=False,
            regulatorySnapshot=False,
            mktDataOptions=None,
        )
    else:
        MP.log_warning("WatchList", "IB connection does not support reqMktData")


if __name__ == "__main__":
    # Initialize TWS connection - returns tuple (ib, req)
    ib, req = get_ib_connection_sync(live_mode=False)

    contract = Stock("AAPL", "SMART", "USD")

    # Example: Create a StockWatch instance
    # stock_watcher = StockWatch(ib, 'AAPL')

    # Uncommented original lines for reference:
    # Ticker_AllLast = ib.reqTickByTickData(contract, tickType='AllLast', numberOfTicks=0, ignoreSize=False)
    # Ticker_BidAsk = ib.reqTickByTickData(contract, tickType='BidAsk', numberOfTicks=0, ignoreSize=False)
    # MkDpth = MPT.MarketDepthCls(ib, contract)

    print("IB Trader initialized successfully")
    print("Use StockWatch(ib, 'SYMBOL') to start watching a stock")

    # Optional: Simple loop for testing
    # LoopNow = True
    # while LoopNow:
    #     try:
    #         # Add your trading logic here
    #         import time
    #         time.sleep(1)
    #     except (KeyboardInterrupt, SystemExit):
    #         LoopNow = False
    """
    class App:

        async def run(self):
            self.ib = IB()
            with await self.ib.connectAsync(port = 7497):
                contracts = [Stock(symbol, 'SMART', 'USD') for symbol in ['AAPL', 'TSLA']]
                for contract in contracts:
                    #self.ib.reqMktData(contract)
                    self.ib.reqTickByTickData(contract, tickType='AllLast', numberOfTicks=0, ignoreSize=False)
                    #self.ib.reqTickByTickData(self.contract, tickType='BidAsk', numberOfTicks=0, ignoreSize=False)

                async for tickers in self.ib.pendingTickersEvent:
                    for ticker in tickers:
                        print(ticker)

        def stop(self):
            self.ib.disconnect()

    app = App()
    try:
        asyncio.run(app.run())
    except (KeyboardInterrupt, SystemExit):
        app.stop()"""
