"""Type stubs for ibapi.common"""

TickerId = int

class BarData:
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: int
    wap: float
    count: int
