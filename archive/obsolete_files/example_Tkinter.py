###Tkinter example added

import asyncio
import tkinter as tk

from ib_async import IB, util

util.patchAsyncio()

from time import perf_counter

import pandas as pd


class TkApp:
    """
    Example of integrating with Tkinter.
    """

    def __init__(self, ib):
        self.ib = ib  # IB().connect(clientId=2)
        self.root = tk.Tk()
        self.root.protocol("WM_DELETE_WINDOW", self._onDeleteWindow)
        self.idx = 1.0

        # Default
        self.entry_stock = tk.Entry(self.root, width=50)
        self.entry_stock.insert(0, "Stock('TSLA', 'SMART', 'USD')")
        self.entry_stock.grid(row=0, column=1)
        self.button = tk.Button(
            self.root, text="Get details", command=self.onButtonClick
        )
        self.button.grid(row=0, column=0)

        # Second
        self.entry_task = tk.Entry(self.root, width=50)
        self.entry_task.insert(0, "Example Text")
        self.entry_task.grid(row=1, column=1)
        self.button2 = tk.Button(
            self.root, text="Run Function", command=self.onButtonClick2
        )
        self.button2.grid(row=1, column=0)

        self.text_bx = tk.Text(self.root)
        self.text_bx.grid(row=2, column=0, columnspan=2)
        self.loop = asyncio.get_event_loop()

    def onButtonClick(self):
        contract = eval(self.entry_stock.get())
        cds = self.ib.reqContractDetails(contract)
        self.text_bx.delete(1.0, tk.END)
        self.text_bx.insert(tk.END, str(cds))

    def onButtonClick2(self):
        text = self.entry_task.get()
        self.idx += 1
        # self.text_bx.delete(self.idx-1, tk.END)
        self.text_bx.insert(1.0, str(text))

    def run(self):
        self._onTimeout()
        self.loop.run_forever()

    def _onTimeout(self):
        self.root.update()
        self.loop.call_later(0.03, self._onTimeout)

    def _onDeleteWindow(self):
        self.loop.stop()


class MarketDepthCls:
    def __init__(self, contract, ib, frame_size=15, isSmartDepth=True):
        self.ib = ib  # ib_async.IB()
        self.frame_size = frame_size

        self.contract = contract
        self.ib.qualifyContracts(self.contract)
        self.ticker = self.ib.reqMktDepth(
            self.contract, isSmartDepth=isSmartDepth, numRows=frame_size
        )  # numRows
        self.ticker.updateEvent += self.onTickerUpdate

        self.df = pd.DataFrame(
            index=range(self.frame_size),
            columns="bidSize bidPrice askPrice askSize".split(),
        )

        self.last_display = perf_counter()

    def onTickerUpdate(self, ticker):
        bids = ticker.domBids
        for i in range(self.frame_size):
            self.df.iloc[i, 0] = bids[i].size if i < len(bids) else 0
            self.df.iloc[i, 1] = bids[i].price if i < len(bids) else 0

        asks = ticker.domAsks
        for i in range(self.frame_size):
            self.df.iloc[i, 2] = asks[i].price if i < len(asks) else 0
            self.df.iloc[i, 3] = asks[i].size if i < len(asks) else 0

        if perf_counter() > self.last_display + 1:
            self.last_display = perf_counter()
            print(self.df)

    def cancelMktDepth(self):
        self.ib.cancelMktDepth(self.contract)


# exchanges = ib.reqMktDepthExchanges()
def printSotck_Exchanges(exchanges):
    print("MktDepthExchanges:")
    for desc in exchanges:
        if desc.secType == "STK":
            print("DepthMktDataDescription.", desc)


if __name__ == "__main__":
    # ib, Req = MPT.InitiateTWS(LiveMode=False, clientId=2)
    ib = IB()

    # contract = Stock('AAPL', 'NASDAQ', 'USD')

    # DWAC_L2 = MarketDepthCls(contract, ib, isSmartDepth=False)

    app = TkApp(ib)
    app.run()

    asyncio.get_event_loop()
    """for i in range(1,120):
        ib.sleep(1)"""
