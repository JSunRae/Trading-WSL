"""
Market Data Service Types - High-impact type definitions
Eliminates reportUnknownMemberType/reportUnknownVariableType cascades
"""

from datetime import datetime
from typing import Any, Literal, NotRequired, TypedDict


# Core bar data structure
class BarRow(TypedDict):
    """Standard OHLCV bar structure"""
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: float

# Tick-by-tick data structures
class TickRecord(TypedDict):
    """Standard tick-by-tick record"""
    timestamp: datetime
    price: float
    size: float
    side: str
    operation: str
    position: int
    market_maker: NotRequired[str]

class DOMTick(TypedDict):
    """Depth of Market tick structure"""
    position: int
    operation: str
    side: str
    price: float
    size: float
    market_maker: str

# Market depth structures
class BidAskLevel(TypedDict):
    """Single bid/ask level"""
    price: float
    size: float
    market_maker: NotRequired[str]

class MarketSnapshot(TypedDict):
    """Market depth snapshot"""
    timestamp: datetime
    bids: list[BidAskLevel]
    asks: list[BidAskLevel]
    symbol: str

# Trading-related literals
WhatToShow = Literal["TRADES", "MIDPOINT", "BID", "ASK", "BID_ASK"]
BarSize = Literal["1 sec", "5 sec", "10 sec", "15 sec", "30 sec", "1 min", "2 mins", "3 mins", "5 mins", "10 mins", "15 mins", "20 mins", "30 mins", "1 hour", "2 hours", "3 hours", "4 hours", "8 hours", "1 day", "1 week", "1 month"]
TickType = Literal["AllLast", "BidAsk", "MidPoint"]

# Container type aliases for common patterns
TickHistory = list[TickRecord]
BarHistory = list[BarRow]
SymbolTickMap = dict[str, TickHistory]
SymbolBarMap = dict[str, BarHistory]

# Level 2 data containers
Level2Bids = list[BidAskLevel]
Level2Asks = list[BidAskLevel]
Level2Data = dict[str, MarketSnapshot]

# Generic data containers (temporary Any usage)
DataCache = dict[str, Any]
TickBuffer = list[dict[str, Any]]
MarketDataBuffer = dict[str, list[dict[str, Any]]]
