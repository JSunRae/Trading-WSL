"""
https://medium.com/swlh/structure-and-communicating-with-interactive-brokers-api-python-78ed9dcaccd7
To start testing the program on your local machine, open the command terminal and navigate to the home folder where ibProgram1.py is saved (Figure 3.1). Open the Trader Work Station and keep that running in the background as we execute the program.
Note: You will receive errors of a broken pipe if the Trader Work Station is not actively running and ready to communicate.
The error codes were received were of type 2104 and 2106 which represent success.

type    Live    Demo
TWS     7496    7497
Gateway 400 4002
"""

"""
Send messages to TWS -> Use Client Class
Receive messages from TWS -> Use Wrapper Class
"""

############################################### IBAPI ###############################################
import math
import multiprocessing
import queue
import time
from threading import Lock, Thread  # Multithreading

import pandas as pd
from ibapi.client import (  # request info
    EClient,
    ListOfContractDescription,
    ListOfHistoricalTick,
    ListOfHistoricalTickBidAsk,
    ListOfHistoricalTickLast,
    logging,
)
from ibapi.contract import Contract
from ibapi.order import Order
from ibapi.wrapper import (  # recieve info
    EWrapper,
    OrderId,
    OrderState,
    RealTimeBar,
    TickAttrib,
    TickerId,
    TickType,
)

import MasterPy as MP

# Below are the global variables
availableFunds = 0
buyingPower = 0
positionsDict = {}
stockPrice = 100000000
stockPriceBool = False


def contractCreate(StockCode, StkMarket):
    # Fills out the contract object
    contract1 = Contract()  # Creates a contract object from the import
    contract1.symbol = (
        StockCode  # StockCode[:StockCode.find('.')]   # Sets the ticker symbol
    )
    contract1.secType = "STK"  # STK Defines the security type as stock
    contract1.currency = "USD"  # StockCode[-3:]  # Currency is US dollars
    contract1.exchange = "SMART"  # In the API side, NASDAQ is always defined as ISLAND in the exchange field
    contract1.primaryExchange = StkMarket  #'ASX' #MP.ExchangeCode(StockCode)[0] #"NYSE"
    return contract1  # Returns the contract object


def orderCreate(quantityEntered=10):
    # Fills out the order object
    order1 = Order()  # Creates an order object from the import
    if quantityEntered > 0:
        order1.action = "BUY"  # Sets the order action to buy
        order1.totalQuantity = int(
            quantityEntered
        )  # Uses the quantity passed in orderExecution
    else:
        order1.action = "SELL"
        order1.totalQuantity = abs(
            int(quantityEntered)
        )  # Uses the quantity passed in orderExecution

    order1.orderType = "MKT"
    # MIT - Market If Touched: triggers if touched
    # MOC - Market On Close: to action as close to close as possible
    # MOO - Market on Open
    # MTL - Market to Limit: market order at best market value, if only partially filled, the rest is submitted as a Limit
    # PEG MKT - Pegged to market
    # PEG STK - Pegged to Stock
    # .sweepToFill = True : Sweep to Fillwhen a trader values speed of execution over price.
    # order1.transmit = True

    order1.totalQuantity = 10  # Setting a static quantity of 10
    order1.discretionaryAmt = (
        0.1 * order1.totalQuantity
    )  # hides and only shows this qty
    return order1  # Returns the order object


def orderExecution(StockCode=""):
    # Places the order with the returned contract and order objects

    contractObject = contractCreate(StockCode)

    orderObject = orderCreate()
    app.price_update(contractObject, app.nextOrderId())
    nextID = app.nextOrderId()

    # Waits for the price_update request to finish
    global stockPriceBool
    timeout = time.time() + 5  # 5seconds
    while stockPriceBool != True:
        time.sleep(0.1)
        if time.time() > timeout:
            MP.ErrorCapture(__name__, "Timeout trying to get StockPrice", 5)
            break

    # Calculates the quantity of the shares we want to trade
    # and Update the quantity of the order to be a portion of the portfolio
    quantityOfTrade = quantityCalc()
    orderObject.totalQuantity = quantityOfTrade

    # Place order
    app.placeOrder(nextID, contractObject, orderObject)
    print(
        "Order placed: "
        + contractObject.symbol
        + " for "
        + str(orderObject.totalQuantity)
        + " Shares: $"
        + str(round(stockPrice * orderObject.totalQuantity))
    )

    stockPriceBool = (
        False  # Reset the flag now that the price has been used in the order
    )


def orderExecutionNormalize(
    symbolEntered, quantityEntered
):  # This order is called to normalize our positions
    # Remakes the contract and order object
    contractObject = contractCreate(symbolEntered)
    orderObject = orderCreate(quantityEntered)
    nextID = app.nextOrderId()

    # Place order
    app.placeOrder(nextID, contractObject, orderObject)
    print("Positions were normalized")


def quantityCalc():
    # View teh buying power and price of stock
    print("Buying power: " + str(buyingPower))
    print("Stock Price: " + str(stockPrice))

    # Divide the buying power by price of the share
    possibleShares = float(buyingPower) / stockPrice

    # Weight the value to be 1 percent of our buying power (this is an easy value to use for testing)
    sharesToBuy = math.floor(possibleShares * 0.10)
    sharesToBuy = 10
    return sharesToBuy  # return the shares to buy so we can use it in orderExecution


def normalizeOrder():  # This function is designed to either sell a holding or cover a short
    print("Waiting to sell the order...")
    # Get the positions from the server
    app.position_update()
    time.sleep(5)

    # Iterates over everything in the positions list and reverses the quantity (covers position)
    for key, value in positionsDict.items():
        parsedSymbol = key
        parsedQuantity = value["positions"]
        parsedCost = value["avgCost"]
        print(str(parsedSymbol) + " " + str(parsedQuantity) + " " + str(parsedCost))

        # This reverses the quantity in the positions list to set the final quantity to 0
        orderExecutionNormalize(parsedSymbol, -1 * parsedQuantity)

    print(positionsDict)

    print("All positions have been sold")


# Below is the TestWrapper/EWrapper class
"""Here we will override the methods found inside api files"""


class TestWrapper(EWrapper):
    ## error handling code
    def init_error(self):
        error_queue = queue.Queue()
        self.my_errors_queue = error_queue

    def is_error(self):
        error_exist = not self.my_errors_queue.empty()
        return error_exist

    def get_error(self, timeout=6):
        if self.is_error():
            try:
                return self.my_errors_queue.get(timeout=timeout)
            except queue.Empty:
                return None
        return None

    def error(self, id, errorCode, errorString):
        ## Overrides the native method
        errormessage = "IB returns an error with %d errorcode %d that says %s" % (
            id,
            errorCode,
            errorString,
        )
        print(errormessage)
        self.my_errors_queue.put(errormessage)

    def init_time(self):
        time_queue = queue.Queue()
        self.my_time_queue = time_queue
        return time_queue

    def currentTime(self, server_time):
        ## Overriden method
        self.my_time_queue.put(server_time)

    def nextValidId(self, orderId: int):
        super().nextValidId(orderId)

        logging.debug("setting nextValidOrderId: %d", orderId)
        self.nextValidOrderId = orderId

    def nextOrderId(self):
        oid = self.nextValidOrderId
        self.nextValidOrderId += 1
        ThisDict[oid] = ""
        return oid

    def accountSummary(
        self, reqId: int, account: str, tag: str, value: str, currency: str
    ):
        super().accountSummary(reqId, account, tag, value, currency)
        print(
            f"Acct Summary        :: ReqId:{reqId} Acct:{account} {tag} ${float(value):,} {currency}"
        )
        if tag == "AvailableFunds":
            global availableFunds
            availableFunds = value
        if tag == "BuyingPower":
            global buyingPower
            buyingPower = value

    def accountSummaryEnd(self, reqId: int):
        super().accountSummaryEnd(reqId)
        print("AccountSummaryEnd. Req Id: ", reqId)

    def position(
        self, account: str, contract: Contract, position: float, avgCost: float
    ):
        super().position(account, contract, position, avgCost)
        positionsDict[contract.symbol] = {"positions": position, "avgCost": avgCost}
        print(
            f"Position            :: {account} Symbol: {contract.symbol} : {contract.secType} Position: ${position:,} AvgCost: ${avgCost:,} {contract.currency}"
        )

    # Market Price handling methods
    def tickPrice(
        self, reqId: TickerId, tickType: TickType, price: float, attrib: TickAttrib
    ):
        super().tickPrice(reqId, tickType, price, attrib)
        print(
            "Tick Price. Ticker Id:",
            reqId,
            "tickType:",
            tickType,
            "Price:",
            price,
            "CanAutoExecute:",
            attrib.canAutoExecute,
            "PastLimit:",
            attrib.pastLimit,
            end=" ",
        )

        global stockPrice  # Declares that we want stockPrice to be treated as a global variable
        global stockPriceBool  # A boolean flag that signals if the price has been updated

        # Use tickType 4 (Last Price) if you are running during the market day
        if tickType == 4:
            print("\nParsed Tick Price, Type4: " + str(price))
            stockPrice = price
            stockPriceBool = True

        # Uses tickType 9 (Close Price) if after market hours
        elif tickType == 9:
            print("\nParsed Tick Price, Type9: " + str(price))
            stockPrice = price
            stockPriceBool = True

    def tickSize(self, reqId: TickerId, tickType: TickType, size: int):
        super().tickSize(reqId, tickType, size)
        print(
            "Tick Size"
        )  # . Ticker Id:", reqId, "tickType:", tickType, "Size:", size)

    def tickString(self, reqId: TickerId, tickType: TickType, value: str):
        super().tickString(reqId, tickType, value)
        print("Tick string. Ticker Id:", reqId, "Typxe:", tickType, "Value:", value)

    def tickGeneric(self, reqId: TickerId, tickType: TickType, value: float):
        super().tickGeneric(reqId, tickType, value)
        print("Tick Generic. Ticker Id:", reqId, "tickType:", tickType, "Value:", value)

    def fundamentalData(self, reqID, data: str):
        super().fundamentalData(reqID, data)
        print("FundamentalData. ReqId:", reqID, "Data:", data)

    def openOrder(
        self, orderId: OrderId, contract: Contract, order: Order, orderState: OrderState
    ):
        super().openOrder(orderId, contract, order, orderState)
        oOrder_dict = {
            "PermId": order.permId,
            "OrderId": orderId,
            "Symbol": contract.symbol,
            "Exchange": contract.exchange,
            "Action": order.action,
            "OrderType": order.orderType,
            "TotalQty": order.totalQuantity,
            "CashQty": order.cashQty,
            "LmtPrice": order.lmtPrice,
            "AuxPrice": order.auxPrice,
            "Status": orderState.status,
        }
        openOrder_df = pd.DataFrame([oOrder_dict], columns=oOrder_dict.keys())
        # main_df = pd.concat([main_df, acct_df], axis=0).reset_index()

        order.contract = contract
        # self.permId2ord[order.permId] = order

    def orderStatus(
        self,
        orderId: OrderId,
        status: str,
        filled: float,
        remaining: float,
        avgFillPrice: float,
        permId: int,
        parentId: int,
        lastFillPrice: float,
        clientId: int,
        whyHeld: str,
        mktCapPrice: float,
    ):
        super().orderStatus(
            orderId,
            status,
            filled,
            remaining,
            avgFillPrice,
            permId,
            parentId,
            lastFillPrice,
            clientId,
            whyHeld,
            mktCapPrice,
        )
        stringAff = ""
        if filled > 0:
            stringAff = "Filled:", filled, "AvgFillPrice:", avgFillPrice
        print(
            "OrderStatus: Id:",
            orderId,
            "Status:",
            status,
            stringAff,
            "Remaining:",
            remaining,
            "PermId:",
            permId,
        )

    def realtimeBar(
        self,
        reqId: TickerId,
        time: int,
        open_: float,
        high: float,
        low: float,
        close: float,
        volume: int,
        wap: float,
        count: int,
    ):
        super().realtimeBar(reqId, time, open_, high, low, close, volume, wap, count)
        print(
            "RealTimeBar. TickerId:",
            reqId,
            RealTimeBar(time, -1, open_, high, low, close, volume, wap, count),
        )

    def historicalTicks(self, reqId: int, ticks: ListOfHistoricalTick, done: bool):
        for tick in ticks:
            print("HistoricalTick. ReqId:", reqId, tick)

    def historicalData(self, reqId: int, bar):
        labels = ["Date", "Open", "High", "Low", "Close", "Volume", "Average", "Count"]

        # Assuming bar is a single row of data, convert it to a DataFrame with one row
        bar_df = pd.DataFrame([bar], columns=labels)

        if isinstance(ThisDict[reqId], str):
            self.ThisDict[reqId] = bar_df
        else:
            self.ThisDict[reqId] = pd.concat([ThisDict[reqId], bar_df])

        print("HistoricalData. ReqId:", reqId, "BarData.", bar)

    def historicalDataEnd(self, reqId: int, start: str, end: str):
        print(ThisDict(reqId))
        print("HistoricalDataEnd. ReqId:", reqId, "from", start, "to", end)

    def historicalTicksBidAsk(
        self, reqId: int, ticks: ListOfHistoricalTickBidAsk, done: bool
    ):
        for tick in ticks:
            print("HistoricalTickBidAsk. ReqId:", reqId, tick)

    def historicalTicksLast(
        self, reqId: int, ticks: ListOfHistoricalTickLast, done: bool
    ):
        for tick in ticks:
            print("HistoricalTickLast. ReqId:", reqId, tick)

    def symbolSamples(
        self, reqId: int, contractDescriptions: ListOfContractDescription
    ):
        super().symbolSamples(reqId, contractDescriptions)
        print("Symbol Samples. Request Id: ", reqId)
        for contractDescription in contractDescriptions:
            derivSecTypes = ""
            for derivSecType in contractDescription.derivativeSecTypes:
                derivSecTypes += derivSecType
                derivSecTypes += " "
            print(
                "Contract: conId:%s, symbol:%s, secType:%s primExchange:%s, "
                "currency:%s, derivativeSecTypes:%s"
                % (
                    contractDescription.contract.conId,
                    contractDescription.contract.symbol,
                    contractDescription.contract.secType,
                    contractDescription.contract.primaryExchange,
                    contractDescription.contract.currency,
                    derivSecTypes,
                )
            )


# Below is the TestClient/EClient Class
"""Here we will call our own methods, not overriding the api methods"""


class TestClient(EClient):
    def __init__(self, wrapper):
        ## Set up with a wrapper inside
        EClient.__init__(self, wrapper)

    def server_clock(self):
        print("Asking server for Unix time")

        # Creates a queue to store the time
        time_storage = self.wrapper.init_time()

        # Sets up a request for unix time from the Eclient
        self.reqCurrentTime()

        # Specifies a max wait time if there is no connection
        max_wait_time = 10

        try:
            requested_time = time_storage.get(timeout=max_wait_time)
        except queue.Empty:
            print("The queue was empty or max time reached")
            requested_time = None

        while self.wrapper.is_error():
            print("Error:")
            print(self.wrapper.get_error(timeout=5))  # JR added in wrapper

        return requested_time

    def account_update(self):
        self.reqAccountSummary(
            9001, "All", "TotalCashValue, BuyingPower, AvailableFunds"
        )

    def position_update(self):
        self.reqPositions()

    def price_update(self, Contract, tickerid):
        self.reqMktData(tickerid, Contract, "", False, False, [])
        return tickerid

    def getFundamentalData(self, reqID, Contract, data: str):
        self.reqFundamentalData(reqID, Contract, data, [])

    def Outside_call(self, var):
        TickerId = app.nextOrderId()
        TempContract = contractCreate(var)
        app.getFundamentalData(TickerId, TempContract, str)


# Below is TestApp Class
class TestApp(TestWrapper, TestClient):
    # Intializes our main classes
    def __init__(self, ipaddress, portid, clientid):
        TestWrapper.__init__(self)
        TestClient.__init__(self, wrapper=self)

        # Connects to the server with the ipaddress, portid, and clientId specified in the program execution area
        self.connect(ipaddress, portid, clientid)

        # Initializes the threading
        thread = Thread(target=self.run)
        thread.start()

        self._thread = thread

        # Starts listening for errors
        self.init_error()


# Below is the program execution
if __name__ == "__main__":
    lock = Lock()
    manager = multiprocessing.Manager()
    ThisDict = manager.dict()

    # LAUNCH TWS
    app = TestApp("127.0.0.1", 7497, 0)
    requested_time = app.server_clock()
    print(
        "This is the current time from the server: " + str(requested_time)
    )  # datetime.fromtimestamp(requested_time).strftime('%Y-%m-%d %H:%M:%S'))

    GetAcctUpdate = False
    if GetAcctUpdate:
        print("Call Account Update")
        app.account_update()  # Call this whenever you need to start accounting data
        print("Call Position Update")
        app.position_update()  # Call for current position
        print("Positions Dictionary")
        print(positionsDict)

    # Get Held Stocks
    for key, value in positionsDict.items():
        parsedSymbol = key
        parsedQuantity = value["positions"]
        parsedCost = value["avgCost"]
        print(str(parsedSymbol) + " " + str(parsedQuantity) + " " + str(parsedCost))

    GetFundamentals = False
    if GetFundamentals:
        # ReportsFinSummary	    Financial summary
        # ReportsOwnership	    Company's ownership (Can be large in size)
        # ReportSnapshot	        Company's financial overview
        # ReportsFinStatements	Financial Statements
        # RESC	                Analyst Estimates
        # CalendarReport	        Company's calendar

        # print(app.fundamentalData('AAPL.US/USD', 'ReportSnapshot'))
        # print(app.fundamentalData('AAPL.US/USD', 'RESC'))
        # print(app.reqMatchingSymbols(211,'IB'))

        # TickerId = app.nextOrderId()
        contractX = Contract()
        contractX.symbol = "AAPL"
        contractX.secType = "STK"
        contractX.currency = "USD"
        contractX.primaryExchange = "ISLAND"
        # app.getFundamentalData(TickerId, contractX, 'ReportSnapshot')

    contractX = Contract()
    contractX.symbol = "AAPL"
    contractX.secType = "STK"
    contractX.currency = "USD"
    contractX.exchange = "SMART"
    contractX.primaryExchange = "ISLAND"

    tickerId = app.nextOrderId()  # nextID
    endDateTime = "20130701 23:59:59 GMT"  # only specify if keepUpToDate = True
    durationStr = (
        "600 S"  # NUmber then letter: S(seconds) D(days) W(weeks) M(months) Y(years)
    )
    barSizeSetting = "1 min"  # 1 secs, 5 secs, 15 secs, 30 secs, 1 min, 2 mins, 3 mins, 5 mins, 15 mins, 30 mins, 1 hour, 1 day
    whatToShow = "TRADES"
    useRTH = 0  # to get out side of trading hours
    formatDate = 1  # to obtain the bars' time as yyyyMMdd HH:mm:ss, set to 2 to obtain it like system time format in seconds
    keepUpToDate = False  # To stop at enddate, if true, endDateTime cannot be specified
    chartOptions = []  #'List< TagValue > 	chartOptions '
    print("tickerId", tickerId)
    bars = app.reqHistoricalData(
        tickerId,
        contractX,
        endDateTime,
        durationStr,
        barSizeSetting,
        whatToShow,
        useRTH,
        formatDate,
        keepUpToDate,
        chartOptions,
    )
    print(bars)
    # Request Historical Data
    # app.reqTickByTickData(nextOrderId(), QAN, "AllLast", 0, False)
    # app.reqRealTimeBars(nextOrderId(), QAN, 5, "MIDPOINT", True, [])
    # app.headTimestamp(nextOrderId(), QAn, 'TRADES', 0, "20200724 14:00:00", 1)
    # app.reqHistoricalTicks(nextOrderId(), contractX,"20200724 09:00:00","", 1000, 'TRADES',0,True,[])


def AskJeeves():
    method_list = [
        func for func in dir(TestClient) if callable(getattr(TestClient, func))
    ]

    while True:
        user_input = input("")
        func_input = user_input[4 : user_input.find("(")]
        vars_input = user_input[user_input.find("(") + 1 : -1]
        # if user_input in locals() and callable(locals()[user_input]):  # if it exists... Outside_call(QAN)
        if func_input in method_list:
            # locals()[user_input]()  # store a pointer to the function
            getattr(TestClient(EClient), func_input)(vars_input)
        elif user_input == "test":
            print("Hello!")
        elif user_input[:3] == "app":
            print("app")
        else:
            print(user_input[:3], "This is not a correct command.")


thread2 = Thread(target=AskJeeves)
thread2.daemon = False
thread2.start()

# app.Outside_call('QAN')

# app.disconnect()
if __name__ == "__main__":
    print("ToDo List")
    """
    Check of ReqID's to know that they completed
    Build Hourly Array
    Build Seconds Array
    Clean Hourly
    Clean Seconds
    Put into Model
    Take action
    """
import asyncio

import ib_async as ibi


class App:
    async def run(self):
        self.ib = ibi.IB()
        with await self.ib.connectAsync():
            contracts = await self.searchForContracts("SPY")
            for contract in contracts:
                self.ib.reqMktData(contract)

            async for tickers in self.ib.pendingTickersEvent:
                print(tickers)

    def stop(self):
        self.ib.disconnect()

    async def searchForContracts(self, pattern):
        descriptions = await self.ib.reqMatchingSymbolsAsync(pattern)
        tasks = [
            self.ib.reqContractDetailsAsync(descr.contract) for descr in descriptions
        ]
        results = await asyncio.gather(*tasks)
        return [cd.contract for cds in results for cd in cds]


app = App()
try:
    asyncio.run(app.run())
except (KeyboardInterrupt, SystemExit):
    app.stop()
