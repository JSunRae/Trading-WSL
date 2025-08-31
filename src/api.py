"""Lightweight public API facade (lazy-loaded).

This module exposes a stable import surface while deferring heavy or optional
imports (e.g. IB integration, ML service implementations) until first access.
Importing ``src.api`` must not require optional extras.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any

# Mapping of exported names to callables that resolve and return the object.
_LAZY: dict[str, Any] = {}


def _export(name: str):  # small decorator to register lazy resolvers
    def dec(fn):
        _LAZY[name] = fn
        return fn

    return dec


# ---- Core light-weight types (safe to import eagerly) ---------------------
from .data import (  # noqa: E402
    ensure_columns as ensure_columns,
)
from .data import (  # noqa: E402
    load_excel as load_excel,
)
from .data import (  # noqa: E402
    save_excel as save_excel,
)
from .data import (  # noqa: E402
    to_records as to_records,
)
from .domain import interfaces as _ifc  # noqa: E402
from .domain import ml_types as _ml  # noqa: E402  (lightweight dataclasses)

# Re-export selected simple types directly (they don't pull optional deps)
Alert = _ml.Alert
AlertSeverity = _ml.AlertSeverity
ExecutionReport = _ml.ExecutionReport
MetricType = _ml.MetricType
MLExecutionQuality = _ml.MLExecutionQuality
MLExecutionReport = _ml.MLExecutionReport
MLOrderMetadata = _ml.MLOrderMetadata
MLTradingSignal = _ml.MLTradingSignal
ModelPerformanceReport = _ml.ModelPerformanceReport
OrderAction = _ml.OrderAction
OrderStatus = _ml.OrderStatus
OrderType = _ml.OrderType
PerformanceMetric = _ml.PerformanceMetric
PositionSizeResult = _ml.PositionSizeResult
RiskAssessment = _ml.RiskAssessment
RiskLevel = _ml.RiskLevel
SignalExecution = _ml.SignalExecution
SignalStatus = _ml.SignalStatus
SignalType = _ml.SignalType
SizingMode = _ml.SizingMode

PerformanceMonitor = _ifc.PerformanceMonitor
PositionSizer = _ifc.PositionSizer
RiskManager = _ifc.RiskManager
SignalValidator = _ifc.SignalValidator


# ---- Lazy heavy / optional components -------------------------------------
@_export("MLSignalExecutor")
def _load_ml_signal_executor():  # noqa: D401
    return import_module("src.execution.ml_signal_executor").MLSignalExecutor


@_export("MLRiskManager")
def _load_ml_risk_manager():  # noqa: D401
    return import_module("src.risk.ml_risk_manager").MLRiskManager


@_export("MLPerformanceMonitor")
def _load_ml_performance_monitor():  # noqa: D401
    return import_module("src.monitoring.ml_performance_monitor").MLPerformanceMonitor


@_export("MLOrderManagementService")
def _load_ml_order_management_service():  # noqa: D401
    return import_module(
        "src.services.ml_order_management_service"
    ).MLOrderManagementService


@_export("stock")
def _load_stock():  # noqa: D401
    return import_module("src.infra").stock


@_export("forex")
def _load_forex():  # noqa: D401
    return import_module("src.infra").forex


@_export("future")
def _load_future():  # noqa: D401
    return import_module("src.infra").future


@_export("req_hist")
def _load_req_hist():  # noqa: D401
    return import_module("src.infra").req_hist


@_export("req_mkt_depth")
def _load_req_mkt_depth():  # noqa: D401
    return import_module("src.infra").req_mkt_depth


@_export("req_tick_by_tick_data")
def _load_req_tbd():  # noqa: D401
    return import_module("src.infra").req_tick_by_tick_data


@_export("get_ib")
def _load_get_ib():  # noqa: D401
    return import_module("src.infra").get_ib


@_export("close_ib")
def _load_close_ib():  # noqa: D401
    return import_module("src.infra").close_ib


@_export("ib_client_available")
def _load_ib_client_available():  # noqa: D401
    return import_module("src.infra").ib_client_available


@_export("IBUnavailableError")
def _load_ib_unavailable_error():  # noqa: D401
    return import_module("src.infra.ib_client").IBUnavailableError


@_export("RateLimiter")
def _load_rate_limiter():  # noqa: D401
    return import_module("src.infra").RateLimiter


@_export("gather_bounded")
def _load_gather_bounded():  # noqa: D401
    return import_module("src.infra").gather_bounded


@_export("with_retry")
def _load_with_retry():  # noqa: D401
    return import_module("src.infra").with_retry


@_export("BarRow")
def _load_bar_row():  # noqa: D401
    return import_module("src.services.market_data.types").BarRow


@_export("BarSize")
def _load_bar_size():  # noqa: D401
    return import_module("src.services.market_data.types").BarSize


@_export("MarketSnapshot")
def _load_market_snapshot():  # noqa: D401
    return import_module("src.services.market_data.types").MarketSnapshot


@_export("TickRecord")
def _load_tick_record():  # noqa: D401
    return import_module("src.services.market_data.types").TickRecord


@_export("TickType")
def _load_tick_type():  # noqa: D401
    return import_module("src.services.market_data.types").TickType


@_export("WhatToShow")
def _load_what_to_show():  # noqa: D401
    return import_module("src.services.market_data.types").WhatToShow


def __getattr__(name: str) -> Any:  # noqa: D401
    if name in _LAZY:
        obj = _LAZY[name]()
        # Optional: cache the resolved object for future accesses
        globals()[name] = obj
        return obj
    raise AttributeError(name)


__all__ = [  # noqa: F822 - names are provided lazily via __getattr__
    # Signal Types
    "SignalType",
    "SignalStatus",
    "MLTradingSignal",
    "SignalExecution",
    # Risk and Sizing
    "SizingMode",
    "RiskLevel",
    "RiskAssessment",
    "PositionSizeResult",
    # Execution and Orders
    "ExecutionReport",
    "OrderAction",
    "OrderType",
    "OrderStatus",
    "MLOrderMetadata",
    "MLExecutionQuality",
    "MLExecutionReport",
    # Performance Monitoring
    "MetricType",
    "AlertSeverity",
    "PerformanceMetric",
    "Alert",
    "ModelPerformanceReport",
    # Market Data Types
    "BarRow",
    "BarSize",
    "MarketSnapshot",
    "TickRecord",
    "TickType",
    "WhatToShow",
    # Service Interfaces
    "SignalValidator",
    "PositionSizer",
    "RiskManager",
    "PerformanceMonitor",
    # Service Implementations
    "MLSignalExecutor",
    "MLRiskManager",
    "MLPerformanceMonitor",
    "MLOrderManagementService",
    # Infrastructure
    "get_ib",
    "close_ib",
    "req_hist",
    "req_mkt_depth",
    "req_tick_by_tick_data",
    "stock",
    "forex",
    "future",
    "RateLimiter",
    "gather_bounded",
    "with_retry",
    "ib_client_available",
    "IBUnavailableError",
    # Data helpers
    "load_excel",
    "save_excel",
    "to_records",
    "ensure_columns",
]
