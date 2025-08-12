"""Type stubs for ibapi.wrapper"""

from typing import Any

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
    def historicalData(self, reqId: TickerId, bar: Any) -> None: ...
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
