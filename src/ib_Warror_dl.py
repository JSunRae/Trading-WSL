# A new API generic tick for realtime news is available via generic tick 292. Also Requesting topic news is possible by providing the news source as the exchange. To see all available topics for a source enter "*" for the symbol.

# Time Issues
# Set time on login screen.
# Time is set to New York as I am only trading there....
# To test ML for other markets will need to apply the correct time from 'US/Eastern' to 'whatever'

# from ib_async import *
import datetime
import os
from sys import path

from ib_async import Stock

path.append("..")
try:
    # Try relative import first (when used as package)
    from . import MasterPy as MP
    from . import MasterPy_Trading as MPT
except ImportError:
    # Fall back to absolute import (when used as script)
    import MasterPy as MP
    import MasterPy_Trading as MPT
from time import perf_counter


class AvTimeCLS:
    def __init__(self):
        self.Start_Original = perf_counter()
        self.Count = 0

    def Interval_start(self):
        self.Interval_Start = perf_counter()

    def Interval_end(self, ReturnTimings=True):
        self.Interval_End = perf_counter()
        self.Count += 1

        if ReturnTimings and round(self.Interval_End - self.Interval_Start) > 0:
            m, s = divmod(round(self.Interval_End - self.Interval_Start), 60)
            return f"Took: {m:0.0f}:{s:02.0f}min. {self.Timings_Str()} {self.Timings_Str()}"

    def Timings_Str(self):
        m_AV, s_Av = divmod(
            round(self.Interval_End - self.Start_Original) / self.Count, 60
        )
        return f"Average of {m_AV:0.0f}:{s_Av:02.0f}min"


class ExitTrigger(Exception):
    pass


class WarriorListCLS:
    def __init__(
        self,
        Req,
        StartRow=0,
        OnlyStock=None,
        SkipStocks=["", "TSLA", "GME"],
        BarSizes=["30 mins", "1 secs", "1 min", "ticks"],
    ):
        self.WarriorList = MPT.WarriorList("Load")

        # Check if WarriorList was loaded successfully
        if self.WarriorList is None:
            MP.ErrorCapture(__name__, "Failed to load WarriorList", 180)
            raise ExitTrigger("Failed to load WarriorList")

        self.TimeClass = AvTimeCLS()
        self.rowN = StartRow - 1  # first grab increments
        self.StockCount = 0
        self.StockRowArr = []
        self.OnlyStock = OnlyStock
        self.InRun = False

        self.SkipStocks = SkipStocks

        self.BarSizeOrig = BarSizes
        self.BarSizes = self.BarSizeOrig

        self.Req = Req

    def Update_RowStocks(self):
        self.rowN += 1

        # Ensure WarriorList is available
        if self.WarriorList is None or self.rowN > len(self.WarriorList):
            raise ExitTrigger

        # try:
        stock_data = self.WarriorList.loc[self.rowN, "ROSS"]
        if isinstance(stock_data, str):
            self.StockRowArr = stock_data.split(";")
        else:
            # Handle case where stock_data is not a string
            self.StockRowArr = [str(stock_data)]

        self.DateRow = self.WarriorList.loc[self.rowN, "Date"]
        # except Exception:
        #    pass

    def Get_NextStock(self):
        self.GotStock = False

        while not self.GotStock:
            self.GotStock = self.Check_2Download()
            if Req.exitflag:
                raise ExitTrigger

        return self.CurrentStock

    def Check_2Download(self):
        if len(self.TradeDays) > 0:
            self.DateStp = self.TradeDays.pop(0)

        elif len(self.BarSizes) > 0:
            # Get new barsize, and refresh dates
            self.BarSize = self.BarSizeOrig.pop(0)
            self.TradeDays = self.Req.get_TradeDates(
                self.DateRow, self.BarSize, daysWanted=5
            )
            self.DateStp = self.TradeDays.pop(0)

        elif len(self.StockRowArr) > 0:
            # Finish last
            print(
                f"Updated {self.BarSize} for {self.contract.symbol}: {self.TimeClass.Interval_end(True)}"
            )
            # Get stocks, days, bar
            self.CurrentStock = self.StockRowArr.pop(0).strip()
            self.BarSizes = self.BarSizeOrig
            self.BarSize = self.BarSizeOrig.pop(0)
            self.TradeDays = self.Req.get_TradeDates(
                self.DateRow, self.BarSize, daysWanted=5
            )
            self.DateStp = self.TradeDays.pop(0)

        else:
            # go to next row
            self.Update_RowStocks()
            self.CurrentStock = self.StockRowArr.pop(0).strip()
            self.BarSizes = self.BarSizeOrig
            self.BarSize = self.BarSizeOrig.pop(0)
            self.TradeDays = self.Req.get_TradeDates(
                self.DateRow, self.BarSize, daysWanted=5
            )
            self.DateStp = self.TradeDays.pop(0)

        if self.CheckSkip():
            return False  # self.GotStock

        self.contract = Stock(self.CurrentStock, "SMART", "USD")

        if self.Req.Download_Exists(
            self.contract.symbol, self.BarSize, forDate=self.DateStp
        ):
            return False  # self.GotStockrn

        if not self.Req.avail2Download(
            self.contract.symbol, self.BarSize, forDate=self.DateStp
        ):
            return False  # self.GotStockrn

        self.TimeClass.Interval_start()
        self.InRun = False
        return True  # self.GotStock

    def CheckSkip(self):
        if self.CurrentStock in self.SkipStocks:
            return True
        if self.OnlyStock != None and self.OnlyStock != self.CurrentStock:
            return True

        return False


def Update_Test(Req, StartRow=0, OnlyStock=None, SkipStocks=None, BarSizes=None):
    WCls = WarriorListCLS(Req, StartRow, OnlyStock, SkipStocks, BarSizes)

    while True:
        try:
            WCls.Get_NextStock()
            print(
                f"{WCls.rowN} of {len(WCls.WarriorList) if WCls.WarriorList is not None else 0}: {WCls.DateRow}  Downloading {WCls.BarSize}: {WCls.CurrentStock}"
            )

            returned = Req.Download_Historical(
                WCls.contract, WCls.BarSize, forDate=WCls.DateStp.date()
            )  #'%Y-%m-%d' #pd.Timestamp(forDate)

            if isinstance(returned, str):
                MP.ErrorCapture_ReturnAns(
                    __name__,
                    "Continue for: "
                    + returned
                    + " : "
                    + WCls.CurrentStock
                    + " : "
                    + WCls.BarSize,
                    1,
                )

        except ExitTrigger:
            break


def Update_Warrior_Main(
    Req, StartRow, BarSizes=["30 mins", "1 secs", "1 min", "ticks"], OnlyStock=None
):
    WarriorList = MPT.WarriorList("Load")

    # Check if WarriorList was loaded successfully
    if WarriorList is None:
        MP.ErrorCapture(
            __name__, "Failed to load WarriorList in Update_Warrior_Main", 180
        )
        return

    TimeClass = AvTimeCLS()

    for rowN in range(StartRow, len(WarriorList)):  # ,0,-1):
        try:
            stock_data = WarriorList.loc[rowN, "ROSS"]
            if isinstance(stock_data, str):
                StockCodeArr = stock_data.split(";")
            else:
                # Handle case where stock_data is not a string
                StockCodeArr = [str(stock_data)]
        except Exception:
            continue

        for StockCode in StockCodeArr:
            StockCode = StockCode.strip()
            if StockCode == "":
                continue
            if StockCode == "TSLA":
                continue
            if StockCode == "GME":
                continue
            if OnlyStock != None and OnlyStock != StockCode:
                continue

            DateStp = WarriorList.loc[rowN, "Date"]
            # DateStr = datetime.strftime(DateStp, "%Y-%m-%d")
            contract = Stock(StockCode, "SMART", "USD")

            TimeClass.Interval_start()
            InRun = False
            for BarSize in BarSizes:
                # if  Req.avail2Download(contract.symbol, BarSize, forDate=DateStp):
                if BarSize == "1 min":
                    TradeDays = Req.get_TradeDates(DateStp, daysWanted=5)
                else:
                    TradeDays = [
                        DateStp
                    ]  # to download at least up to that day. [datetime.strptime('2021-10-01', "%Y-%m-%d")]#['2021-05-01']

                for TadeDayStp in TradeDays:
                    if Req.Download_Exists(
                        contract.symbol, BarSize, forDate=TadeDayStp
                    ):
                        continue

                    elif Req.avail2Download(
                        contract.symbol, BarSize, forDate=TadeDayStp
                    ):
                        InRun = True

                        print(
                            f"{rowN} of {len(WarriorList)}: {WarriorList.loc[rowN, 'Date']}  Downloading {BarSize}: {StockCode}"
                        )

                        # Convert TadeDayStp to proper date format
                        import datetime as dt

                        if isinstance(TadeDayStp, dt.datetime):
                            trade_date = TadeDayStp.date()
                        elif isinstance(TadeDayStp, dt.date):
                            trade_date = TadeDayStp
                        elif isinstance(TadeDayStp, str):
                            # Try to parse string date
                            try:
                                trade_date = dt.datetime.strptime(
                                    TadeDayStp, "%Y-%m-%d"
                                ).date()
                            except ValueError:
                                trade_date = TadeDayStp
                        else:
                            # For other types (pandas Timestamp, etc.), try to convert to string first
                            try:
                                trade_date = str(TadeDayStp)
                            except:
                                trade_date = TadeDayStp

                        returned = Req.Download_Historical(
                            contract, BarSize, forDate=trade_date
                        )  #'%Y-%m-%d' #pd.Timestamp(forDate)

                        if isinstance(returned, str):
                            MP.ErrorCapture_ReturnAns(
                                __name__,
                                "Continue for: "
                                + returned
                                + " : "
                                + StockCode
                                + " : "
                                + BarSize,
                                1,
                            )

                    if Req.exitflag:
                        break

                if InRun:
                    print(
                        f"Updated {BarSize} for {contract.symbol}: {TimeClass.Interval_end(True)}"
                    )

                if Req.exitflag:
                    break
            if Req.exitflag:
                break
        if Req.exitflag:
            break


def Update_Warrior_30Min(Req, StartRow, BarSizes=["30 mins"], OnlyStock=None):
    WarriorList = MPT.WarriorList("Load")

    # Check if WarriorList was loaded successfully
    if WarriorList is None:
        MP.ErrorCapture(
            __name__, "Failed to load WarriorList in Update_Warrior_30Min", 180
        )
        return

    TimeClass = AvTimeCLS()

    for rowN in range(StartRow, len(WarriorList)):  # ,0,-1):
        try:
            stock_data = WarriorList.loc[rowN, "ROSS"]
            if isinstance(stock_data, str):
                StockCodeArr = stock_data.split(";")
            else:
                # Handle case where stock_data is not a string
                StockCodeArr = [str(stock_data)]
        except Exception:
            continue

        for StockCode in StockCodeArr:
            StockCode = StockCode.strip()
            if StockCode == "":
                continue
            if StockCode == "TSLA":
                continue
            if StockCode == "GME":
                continue
            if OnlyStock != None and OnlyStock != StockCode:
                continue

            TadeDayStp = datetime.date.today() - datetime.timedelta(days=1)
            # DateStr = datetime.strftime(DateStp, "%Y-%m-%d")

            contract = Stock(StockCode, "SMART", "USD")
            TimeClass.Interval_start()
            InRun = False

            for BarSize in BarSizes:
                if Req.Download_Exists(contract.symbol, BarSize, forDate=TadeDayStp):
                    continue
                elif Req.is_failed(contract.symbol, BarSize, forDate=TadeDayStp):
                    continue
                elif Req.avail2Download(contract.symbol, BarSize, forDate=TadeDayStp):
                    print(
                        f"{rowN} of {len(WarriorList)}: {WarriorList.loc[rowN, 'Date']}  Downloading {BarSize}: {StockCode}"
                    )
                    InRun = True
                    returned = Req.Download_Historical(
                        contract, BarSize, forDate=TadeDayStp
                    )  #'%Y-%m-%d' #pd.Timestamp(forDate)
                    print(f"Updated {BarSize} for {contract.symbol}")

                    if isinstance(returned, str):
                        MP.ErrorCapture_ReturnAns(
                            __name__,
                            "Continue for: "
                            + returned
                            + " : "
                            + StockCode
                            + " : "
                            + BarSize,
                            1,
                        )

                if Req.exitflag:
                    break
            if InRun:
                print(
                    f"Updated {BarSize} for {contract.symbol}: {TimeClass.Interval_end(True)}"
                )

            if Req.exitflag:
                break

        if Req.exitflag:
            break


def Update_Downloaded(
    Req, StartRow, BarSizes=["30 mins", "1 secs", "1 min", "ticks"], OnlyStock=None
):
    WarriorList = MPT.WarriorList("Load")

    # Check if WarriorList was loaded successfully
    if WarriorList is None:
        MP.ErrorCapture(
            __name__, "Failed to load WarriorList in Update_Downloaded", 180
        )
        return

    for rowN in range(StartRow, len(WarriorList)):  # ,0,-1):
        try:
            stock_data = WarriorList.loc[rowN, "ROSS"]
            if isinstance(stock_data, str):
                StockCodeArr = stock_data.split(";")
            else:
                # Handle case where stock_data is not a string
                StockCodeArr = [str(stock_data)]
        except Exception:
            continue

        for StockCode in StockCodeArr:
            StockCode = StockCode.strip()
            if StockCode == "":
                continue
            if OnlyStock != None and OnlyStock != StockCode:
                continue

            contract = Stock(StockCode, "SMART", "USD")
            DateStp = WarriorList.loc[rowN, "Date"]

            for BarSize in BarSizes:
                if BarSize == "1 min":
                    TradeDays = Req.get_TradeDates(DateStp, daysWanted=5)
                else:
                    TradeDays = [
                        DateStp
                    ]  # to download at least up to that day. [datetime.strptime('2021-10-01', "%Y-%m-%d")]#['2021-05-01']

                for TadeDayStp in TradeDays:
                    # Convert TadeDayStp to string format for file operations
                    try:
                        import datetime as dt

                        if isinstance(TadeDayStp, (dt.datetime, dt.date)):
                            trade_date_str = TadeDayStp.strftime("%Y-%m-%d")
                        else:
                            trade_date_str = (
                                str(TadeDayStp)[:10]
                                if len(str(TadeDayStp)) >= 10
                                else str(TadeDayStp)
                            )
                    except:
                        trade_date_str = (
                            str(TadeDayStp)[:10]
                            if len(str(TadeDayStp)) >= 10
                            else str(TadeDayStp)
                        )

                    if Req.Download_Exists(
                        contract.symbol, BarSize, forDate=TadeDayStp
                    ):
                        continue
                    if os.path.exists(
                        MPT.IB_Download_Loc(contract.symbol, BarSize, trade_date_str)
                    ):
                        Req.appendDownloaded(
                            contract.symbol, BarSize, forDate=TadeDayStp
                        )


def Create_Warrior_TrainList(StartRow):
    WarriorList = MPT.WarriorList("Load")

    # Check if WarriorList was loaded successfully
    if WarriorList is None:
        MP.ErrorCapture(
            __name__, "Failed to load WarriorList in Create_Warrior_TrainList", 180
        )
        return

    TrainList = MPT.TrainList_LoadSave("Load", TrainType="Warrior")

    # Check if TrainList was loaded successfully
    if TrainList is None:
        MP.ErrorCapture(
            __name__, "Failed to load TrainList in Create_Warrior_TrainList", 180
        )
        return

    i = -1
    for rowN in range(StartRow, len(WarriorList)):  # ,0,-1):
        try:
            stock_data = WarriorList.loc[rowN, "ROSS"]
            if isinstance(stock_data, str):
                StockCodeArr = stock_data.split(";")
            else:
                # Handle case where stock_data is not a string
                StockCodeArr = [str(stock_data)]
        except Exception:
            continue

        for StockCode in StockCodeArr:
            StockCode = StockCode.strip()
            if StockCode == "":
                continue

            DateStr = WarriorList.loc[rowN, "Date"]

            # Convert DateStr to string safely using try-catch
            try:
                import datetime as dt

                if isinstance(DateStr, (dt.datetime, dt.date)):
                    DateStr = DateStr.strftime("%Y-%m-%d")
                else:
                    # Handle pandas Timestamp and other datetime-like objects
                    DateStr = (
                        str(DateStr)[:10] if len(str(DateStr)) >= 10 else str(DateStr)
                    )
            except:
                DateStr = str(DateStr)[:10] if len(str(DateStr)) >= 10 else str(DateStr)

            contract = Stock(StockCode, "SMART", "USD")

            if os.path.exists(
                MPT.IB_Download_Loc(contract.symbol, "1 secs", DateStr)
            ) and os.path.exists(
                MPT.IB_Download_Loc(contract.symbol, "1 min", DateStr)
            ):
                i += 1
                TrainList.loc[i, "Stock"] = StockCode
                TrainList.loc[i, "DateStr"] = DateStr

    MPT.TrainList_LoadSave("Save", TrainType="Warrior", df=TrainList)


if __name__ == "__main__":
    ib, Req = MPT.InitiateTWS(LiveMode=False)
    # Update_Downloaded(Req, StartRow=0)

    Update_Test(Req, StartRow=0, OnlyStock=None, SkipStocks=None, BarSizes=None)
    # Update_Warrior_Main(Req, StartRow=0)
    # Update_Warrior_30Min(Req, StartRow=135)

    # Create_Warrior_TrainList(StartRow=0)

    MP.SendTxt(f"Completed {__name__}")
