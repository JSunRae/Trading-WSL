from __future__ import annotations

from collections.abc import Callable
from typing import Any, Literal, NewType, Protocol, TypedDict
from datetime import datetime

# ---- Core scalars
Symbol = NewType("Symbol", str)
Exchange = NewType("Exchange", str)
Currency = NewType("Currency", str)

# ---- Bar sizes (adjust to your actual IB usage)
BarSize = Literal[
    "1 secs", "5 secs", "10 secs", "15 secs", "30 secs",
    "1 min", "2 mins", "3 mins", "5 mins", "10 mins", "15 mins", "20 mins", "30 mins",
    "1 hour", "2 hours", "3 hours", "4 hours", "8 hours",
    "1 day", "1 week", "1 month"
]

# ---- Protocols for common objects
class HasSymbol(Protocol):
    symbol: str

class HasStrftime(Protocol):
    """Protocol for datetime-like objects that have strftime method"""
    def strftime(self, fmt: str) -> str: ...

class HasTimezone(Protocol):
    """Protocol for timezone-aware datetime objects"""
    def tz_localize(self, tz: Any, **kwargs: Any) -> Any: ...
    tz: Any

class HasDateMethods(Protocol):
    """Protocol for objects with date methods"""
    def date(self) -> datetime: ...

class HasAddMethod(Protocol):
    """Protocol for objects that support addition"""
    def __add__(self, other: Any) -> Any: ...

class HasQualifyContracts(Protocol):
    """Protocol for IB connection objects"""
    def qualifyContracts(self, *args: Any, **kwargs: Any) -> Any: ...

class HasContractAttribs(Protocol):
    """Protocol for IB contract objects"""
    symbol: str
    secType: str
    exchange: str
    currency: str
    primaryExchange: str
    conId: int

# ---- Pandas helpers
try:
    import pandas as pd
    from pandas import DataFrame, Series

    # Re-export for type hints
    __all__ = ["Symbol", "Exchange", "Currency", "BarSize", "HasSymbol", "HasStrftime", "HasTimezone", 
               "HasDateMethods", "HasAddMethod", "HasQualifyContracts", "HasContractAttribs",
               "ErrorCaptureKw", "AnyFn", "DataFrame", "Series", "pd"]
except ImportError:
    DataFrame = Any  # type: ignore
    Series = Any     # type: ignore
    pd = Any         # type: ignore

    # Re-export for type hints (without pandas)
    __all__ = ["Symbol", "Exchange", "Currency", "BarSize", "HasSymbol", "HasStrftime", "HasTimezone",
               "HasDateMethods", "HasAddMethod", "HasQualifyContracts", "HasContractAttribs", 
               "ErrorCaptureKw", "AnyFn"]

# ---- Common dict shapes
class ErrorCaptureKw(TypedDict, total=False):
    module_name: str
    message: str
    duration: int
    show_popup: bool
    continueOn: bool

# ---- Generic callable type
AnyFn = Callable[..., Any]
