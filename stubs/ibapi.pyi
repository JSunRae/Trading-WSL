"""Type stubs for Interactive Brokers API (ibapi)"""

from typing import Any

class Contract:
    symbol: str
    secType: str
    exchange: str
    currency: str
    primaryExchange: str
    localSymbol: str
    tradingClass: str
    multiplier: str
    right: str
    strike: float
    expiry: str
    def __init__(self) -> None: ...

class BarData:
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: int
    wap: float
    count: int

TickerId = int

class EWrapper:
    def __init__(self) -> None: ...
    def connectAck(self) -> None: ...
    def connectionClosed(self) -> None: ...
    def error(
        self,
        reqId: TickerId,
        errorCode: int,
        errorString: str,
        advancedOrderRejectJson: str = "",
    ) -> None: ...
    def historicalData(self, reqId: TickerId, bar: BarData) -> None: ...
    def historicalDataEnd(self, reqId: int, start: str, end: str) -> None: ...
    def tickPrice(
        self, reqId: TickerId, tickType: int, price: float, attrib: Any
    ) -> None: ...
    def tickSize(self, reqId: TickerId, tickType: int, size: int) -> None: ...
    def updateMktDepth(
        self,
        reqId: TickerId,
        position: int,
        operation: int,
        side: int,
        price: float,
        size: int,
    ) -> None: ...
    def updateMktDepthL2(
        self,
        reqId: TickerId,
        position: int,
        marketMaker: str,
        operation: int,
        side: int,
        price: float,
        size: int,
        isSmartDepth: bool,
    ) -> None: ...

class EClient:
    def __init__(self, wrapper: EWrapper) -> None: ...
    def connect(self, host: str, port: int, clientId: int) -> bool: ...
    def disconnect(self) -> None: ...
    def run(self) -> None: ...
    def reqHistoricalData(
        self,
        reqId: int,
        contract: Contract,
        endDateTime: str,
        durationStr: str,
        barSizeSetting: str,
        whatToShow: str,
        useRTH: int,
        formatDate: int,
        keepUpToDate: bool,
        chartOptions: list[Any],
    ) -> None: ...
    def reqMktData(
        self,
        reqId: int,
        contract: Contract,
        genericTickList: str,
        snapshot: bool,
        regulatorySnapshot: bool,
        mktDataOptions: list[Any],
    ) -> None: ...
    def cancelMktData(self, reqId: int) -> None: ...
    def reqMktDepth(
        self,
        reqId: int,
        contract: Contract,
        numRows: int,
        isSmartDepth: bool,
        mktDepthOptions: list[Any],
    ) -> None: ...
    def cancelMktDepth(self, reqId: int, isSmartDepth: bool) -> None: ...
