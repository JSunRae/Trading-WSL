"""Minimal type stubs for IBKR async client surface (vendor-agnostic)."""

from collections.abc import Awaitable, Sequence
from typing import Any

class Contract:
    """Base contract class."""

    symbol: str
    secType: str
    exchange: str
    currency: str
    conId: int

class Stock(Contract):
    """Stock contract."""
    def __init__(
        self, symbol: str, exchange: str = "SMART", currency: str = "USD"
    ) -> None: ...

class Forex(Contract):
    """Forex contract."""
    def __init__(self, pair: str, exchange: str = "IDEALPRO") -> None: ...

class Future(Contract):
    """Future contract."""
    def __init__(self, symbol: str, exchange: str, currency: str) -> None: ...

class Option(Contract):
    """Option contract."""
    def __init__(
        self,
        symbol: str,
        lastTradeDateOrContractMonth: str,
        strike: float,
        right: str,
        exchange: str = "SMART",
        currency: str = "USD",
    ) -> None: ...

class BarData:
    """Historical bar data."""

    date: Any
    open: float
    high: float
    low: float
    close: float
    volume: int

class EClient:
    """IB API client base class."""
    def reqMktDepth(
        self, tickerId: int, contract: Contract, numRows: int, isSmartDepth: bool
    ) -> None: ...
    def cancelMktDepth(self, tickerId: int) -> None: ...

class IB(EClient):
    """Interactive Brokers connection class."""
    def connect(self, host: str, port: int, clientId: int) -> IB: ...
    def connectAsync(self, host: str, port: int, clientId: int) -> Awaitable[IB]: ...
    def disconnect(self) -> None: ...
    def isConnected(self) -> bool: ...
    def reqHistoricalData(
        self,
        contract: Contract,
        endDateTime: str,
        durationStr: str,
        barSizeSetting: str,
        whatToShow: str = "TRADES",
        useRTH: bool = True,
        formatDate: int = 1,
        keepUpToDate: bool = False,
        chartOptions: Sequence[Any] | None = None,
        timeout: float = 60.0,
    ) -> list[BarData]: ...
    def reqHistoricalDataAsync(
        self,
        contract: Contract,
        endDateTime: str,
        durationStr: str,
        barSizeSetting: str,
        whatToShow: str = "TRADES",
        useRTH: int = 1,
        formatDate: int = 1,
        keepUpToDate: bool = False,
        chartOptions: Sequence[Any] | None = None,
        timeout: float = 60.0,
    ) -> Awaitable[list[BarData]]: ...
    def reqMktData(
        self,
        contract: Contract,
        genericTickList: str = "",
        snapshot: bool = False,
    ) -> Any: ...
    def reqContractDetails(self, contract: Contract) -> list[Any]: ...
    def reqContractDetailsAsync(self, contract: Contract) -> Awaitable[list[Any]]: ...
    def placeOrder(self, contract: Contract, order: Any) -> Any: ...
    def cancelOrder(self, order: Any) -> None: ...
    def sleep(self, seconds: float = 0.02) -> None: ...
    def run(self) -> None: ...

# Order types
class MarketOrder:
    def __init__(self, action: str, totalQuantity: float) -> None: ...

class LimitOrder:
    def __init__(self, action: str, totalQuantity: float, lmtPrice: float) -> None: ...
