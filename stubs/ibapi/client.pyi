"""Type stubs for ibapi.client"""

from typing import Any

from .contract import Contract
from .wrapper import EWrapper

# Type aliases for IB API
TagValue = Any  # IB's TagValue class for options

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
        chartOptions: list[TagValue],
    ) -> None: ...
    def reqMktData(
        self,
        reqId: int,
        contract: Contract,
        genericTickList: str,
        snapshot: bool,
        regulatorySnapshot: bool,
        mktDataOptions: list[TagValue],
    ) -> None: ...
    def cancelMktData(self, reqId: int) -> None: ...
    def reqMktDepth(
        self,
        reqId: int,
        contract: Contract,
        numRows: int,
        isSmartDepth: bool,
        mktDepthOptions: list[TagValue],
    ) -> None: ...
    def cancelMktDepth(self, reqId: int, isSmartDepth: bool) -> None: ...
