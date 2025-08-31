"""Type definitions for the trading system."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any, Protocol, TypedDict, TypeVar

import numpy as np
import pandas as pd
from numpy.typing import NDArray

# Import project-wide types explicitly to avoid star-import issues with analyzers
from .project_types import Symbol

# Type variables
T = TypeVar("T")
ErrorHandlerT = TypeVar("ErrorHandlerT", bound=Callable[..., Any])

# Basic type aliases (Python 3.12+ `type` syntax)
type Timestamp = pd.Timestamp | datetime
type Price = float
type Volume = int
type RequestId = int

# Numpy arrays
type FloatArray = NDArray[np.floating[Any]]
type IntArray = NDArray[np.integer[Any]]
type BoolArray = NDArray[np.bool_]


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
    secType: str  # noqa: N815
    exchange: str
    currency: str


class IBWrapper(Protocol):
    """Protocol for IB API wrapper interface."""

    def error(
        self,
        reqId: int,  # noqa: N803
        errorCode: int,  # noqa: N803
        errorString: str,  # noqa: N803
        advancedOrderRejectJson: str = "",  # noqa: N803
    ) -> None: ...
    def connectAck(self) -> None: ...  # noqa: N802
    def connectionClosed(self) -> None: ...  # noqa: N802


class IBClient(Protocol):
    """Protocol for IB API client interface."""

    def connect(self, host: str, port: int, clientId: int) -> None: ...  # noqa: N803
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
type TickCallback = Callable[[TickRecord], None]
type BarCallback = Callable[[BarRecord], None]
type DepthCallback = Callable[[DepthRecord], None]
type ErrorCallback = Callable[[ErrorContext], None]
type ConnectionCallback = Callable[[bool], None]

# Async callback types (for async handlers)
type AsyncTickCallback = Callable[[TickRecord], Awaitable[None]]
type AsyncBarCallback = Callable[[BarRecord], Awaitable[None]]
type AsyncDepthCallback = Callable[[DepthRecord], Awaitable[None]]
type AsyncErrorCallback = Callable[[ErrorContext], Awaitable[None]]

# Generic container types
type DataDict = dict[str, Any]
type ConfigDict = dict[str, Any]
type MetricsDict = dict[str, float | int]

# Queue types for async processing
type TickQueue = asyncio.Queue[TickRecord]
type BarQueue = asyncio.Queue[BarRecord]
type ErrorQueue = asyncio.Queue[ErrorContext]

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
