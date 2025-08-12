from __future__ import annotations
from typing import Any
from collections.abc import Sequence

class IB:
    async def connect(self, host: str = ..., port: int = ..., clientId: int = ...) -> None: ...
    async def disconnect(self) -> None: ...
    async def reqHistoricalData(
        self, contract: Contract, endDateTime: str, durationStr: str,
        barSizeSetting: str, whatToShow: str, useRTH: int,
        formatDate: int, keepUpToDate: bool, chartOptions: Sequence[Any] | None = ...
    ) -> list[BarData]: ...
    async def reqMktData(self, contract: Contract, genericTickList: str = ..., snapshot: bool = ...) -> Ticker: ...
    async def cancelMktData(self, contract: Contract) -> None: ...
    def isConnected(self) -> bool: ...

class Contract: 
    symbol: str
    secType: str
    exchange: str
    currency: str

class Stock(Contract):
    def __init__(self, symbol: str, exchange: str = ..., currency: str = ...) -> None: ...

class Forex(Contract):
    def __init__(self, pair: str, exchange: str = ...) -> None: ...

class Future(Contract):
    def __init__(self, symbol: str, lastTradeDateOrContractMonth: str, exchange: str = ...) -> None: ...

class Option(Contract):
    def __init__(self, symbol: str, lastTradeDateOrContractMonth: str, strike: float, right: str, exchange: str = ...) -> None: ...

class BarData:
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    barCount: int
    WAP: float

class Ticker:
    contract: Contract
    bid: float
    ask: float
    last: float
    bidSize: float
    askSize: float
    lastSize: float
    
class MarketDepth:
    position: int
    marketMaker: str
    operation: int
    side: int
    price: float
    size: float
