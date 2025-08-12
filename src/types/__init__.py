"""Type definitions for the trading system."""

from __future__ import annotations

import asyncio
import sys
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any, Protocol, TypedDict, TypeVar, Union

import numpy as np
import pandas as pd
from numpy.typing import NDArray

if sys.version_info >= (3, 10):
    from typing import TypeAlias
else:
    from typing import TypeAlias

# Re-export all project types
from .project_types import *

# Type variables
T = TypeVar("T")
ErrorHandlerT = TypeVar("ErrorHandlerT", bound=Callable[..., Any])

# Basic type aliases
Timestamp: TypeAlias = pd.Timestamp | datetime
Price: TypeAlias = float
Volume: TypeAlias = int
Symbol: TypeAlias = str
RequestId: TypeAlias = int

# Numpy arrays
FloatArray: TypeAlias = NDArray[np.floating[Any]]
IntArray: TypeAlias = NDArray[np.integer[Any]]
BoolArray: TypeAlias = NDArray[np.bool_]


# Error and logging types
class ErrorContext(TypedDict, total=False):
    """Error context information."""

    reqId: int
    errorCode: int
    errorString: str
    timestamp: datetime
    symbol: str | None
    additional_info: dict[str, Any]


class LogRecord(TypedDict):
    """Structured log record."""

    level: str
    message: str
    timestamp: datetime
    module: str
    function: str | None


# Market data types
class TickRecord(TypedDict):
    """Market tick data record."""

    symbol: Symbol
    tick_type: int
    value: float
    timestamp: datetime


class BarRecord(TypedDict):
    """Historical bar record."""

    symbol: Symbol
    datetime: datetime
    open: Price
    high: Price
    low: Price
    close: Price
    volume: Volume
    wap: Price
    count: int


class DepthRecord(TypedDict):
    """Market depth record."""

    symbol: Symbol
    position: int
    operation: int  # 0=insert, 1=update, 2=delete
    side: int  # 0=ask, 1=bid
    price: Price
    size: Volume
    market_maker: str
    timestamp: datetime


# Configuration types
class ConnectionConfig(TypedDict, total=False):
    """IB connection configuration."""

    host: str
    port: int
    client_id: int
    timeout: float
    paper_trading: bool


class TradingConfig(TypedDict, total=False):
    """Trading system configuration."""

    connection: ConnectionConfig
    data_path: str
    log_level: str
    risk_limits: dict[str, Any]


# Protocol definitions for IB API compatibility
class IBContract(Protocol):
    """Protocol for Interactive Brokers contract objects."""

    symbol: str
    secType: str
    exchange: str
    currency: str


class IBWrapper(Protocol):
    """Protocol for IB API wrapper interface."""

    def error(
        self,
        reqId: int,
        errorCode: int,
        errorString: str,
        advancedOrderRejectJson: str = "",
    ) -> None: ...
    def connectAck(self) -> None: ...
    def connectionClosed(self) -> None: ...


class IBClient(Protocol):
    """Protocol for IB API client interface."""

    def connect(self, host: str, port: int, clientId: int) -> None: ...
    def disconnect(self) -> None: ...
    def run(self) -> None: ...


# Execution and order types
class ExecutionData(TypedDict):
    """Trade execution data."""

    symbol: Symbol
    side: str  # 'BUY' or 'SELL'
    quantity: int
    price: Price
    timestamp: datetime
    execution_id: str
    commission: float | None


class OrderData(TypedDict, total=False):
    """Order information."""

    symbol: Symbol
    action: str  # 'BUY' or 'SELL'
    quantity: int
    order_type: str  # 'MKT', 'LMT', etc.
    limit_price: Price | None
    stop_price: Price | None
    time_in_force: str
    order_id: int | None


# Data processing types
class DataValidationResult(TypedDict):
    """Result of data validation."""

    valid: bool
    errors: list[str]
    warnings: list[str]
    processed_records: int


class ProcessingStats(TypedDict):
    """Data processing statistics."""

    total_records: int
    valid_records: int
    error_records: int
    processing_time: float
    memory_usage: int


# Callback types
TickCallback: TypeAlias = Callable[[TickRecord], None]
BarCallback: TypeAlias = Callable[[BarRecord], None]
DepthCallback: TypeAlias = Callable[[DepthRecord], None]
ErrorCallback: TypeAlias = Callable[[ErrorContext], None]
ConnectionCallback: TypeAlias = Callable[[bool], None]

# Async callback types (for async handlers)
AsyncTickCallback: TypeAlias = Callable[[TickRecord], Awaitable[None]]
AsyncBarCallback: TypeAlias = Callable[[BarRecord], Awaitable[None]]
AsyncDepthCallback: TypeAlias = Callable[[DepthRecord], Awaitable[None]]
AsyncErrorCallback: TypeAlias = Callable[[ErrorContext], Awaitable[None]]

# Generic container types
DataDict: TypeAlias = dict[str, Any]
ConfigDict: TypeAlias = dict[str, Any]
MetricsDict: TypeAlias = dict[str, float | int]

# Queue types for async processing
TickQueue: TypeAlias = asyncio.Queue[TickRecord]
BarQueue: TypeAlias = asyncio.Queue[BarRecord]
ErrorQueue: TypeAlias = asyncio.Queue[ErrorContext]

__all__ = [
    # Type variables
    "T",
    "ErrorHandlerT",
    # Basic types
    "Timestamp",
    "Price",
    "Volume",
    "Symbol",
    "RequestId",
    # Numpy types
    "FloatArray",
    "IntArray",
    "BoolArray",
    # TypedDict classes
    "ErrorContext",
    "LogRecord",
    "TickRecord",
    "BarRecord",
    "DepthRecord",
    "ConnectionConfig",
    "TradingConfig",
    "ExecutionData",
    "OrderData",
    "DataValidationResult",
    "ProcessingStats",
    # Protocols
    "IBContract",
    "IBWrapper",
    "IBClient",
    # Callback types
    "TickCallback",
    "BarCallback",
    "DepthCallback",
    "ErrorCallback",
    "ConnectionCallback",
    "AsyncTickCallback",
    "AsyncBarCallback",
    "AsyncDepthCallback",
    "AsyncErrorCallback",
    # Container types
    "DataDict",
    "ConfigDict",
    "MetricsDict",
    # Queue types
    "TickQueue",
    "BarQueue",
    "ErrorQueue",
]
