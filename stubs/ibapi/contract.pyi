"""Type stubs for ibapi.contract"""

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
