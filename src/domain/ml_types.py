"""
ML Trading Domain Types

Single source of truth for all ML trading types, enums, and data structures.
Provides type-safe definitions for signals, execution, risk assessment, and monitoring.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum, auto
from typing import Literal, NotRequired, TypedDict


# Signal Types and Status
class SignalType(Enum):
    """Trading signal types"""

    BUY = auto()
    SELL = auto()
    HOLD = auto()


class SignalStatus(Enum):
    """Signal execution status"""

    PENDING = auto()
    EXECUTED = auto()
    REJECTED = auto()
    CANCELLED = auto()


# Risk and Sizing
class SizingMode(Enum):
    """Position sizing strategies"""

    FIXED = auto()
    CONFIDENCE_WEIGHTED = auto()  # matches tests' CONFIDENCE_WEIGHTED
    KELLY = auto()
    VOLATILITY_ADJUSTED = auto()


class RiskLevel(Enum):
    """Risk assessment levels"""

    LOW = auto()
    MEDIUM = auto()
    HIGH = auto()
    CRITICAL = auto()


# Core ML Trading Signal
@dataclass(slots=True)
class MLTradingSignal:
    """ML-generated trading signal with metadata"""

    signal_id: str
    symbol: str
    signal_type: SignalType
    value: float
    confidence: float  # 0.0 to 1.0
    target_quantity: float
    # Original field name 'timestamp' retained for backward compatibility.
    # Execution layer expects 'signal_timestamp'; we mirror the value.
    timestamp: datetime | None = None
    signal_timestamp: datetime | None = None
    max_execution_time_seconds: float | None = None  # optional SLA guidance
    model_version: str = "unknown"
    strategy_name: str = "default"

    def __post_init__(self):  # pragma: no cover - trivial mapping
        if self.signal_timestamp is None:
            self.signal_timestamp = self.timestamp
        elif self.timestamp is None:
            self.timestamp = self.signal_timestamp


# Execution Types
@dataclass(slots=True)
class SignalExecution:
    """Result of executing a trading signal"""

    signal_id: str
    filled_qty: float
    status: SignalStatus
    execution_price: float | None = None
    message: str = ""
    execution_time: datetime | None = None


class ExecutionReport(TypedDict):
    """Summary report of execution performance"""

    total_signals: int
    successful_executions: int
    total_pnl: float
    accuracy_rate: float
    avg_execution_time: NotRequired[float]
    total_volume: NotRequired[float]


# Risk Assessment Types
class RiskAssessment(TypedDict):
    """Risk evaluation result"""

    risk_score: float  # 0.0 to 1.0
    overall_risk_level: RiskLevel
    recommended_action: Literal["trade", "skip", "reduce", "abort"]
    risk_factors: NotRequired[list[str]]


@dataclass(slots=True)
class PositionSizeResult:
    """Result of position sizing calculation"""

    final_size: float
    confidence_factor: float
    risk_adjusted: bool = False
    max_size: float | None = None
    sizing_method: SizingMode = SizingMode.FIXED


# Performance Monitoring Types
class MetricType(Enum):
    """Performance metric types"""

    PNL = auto()
    ACCURACY = auto()
    SHARPE_RATIO = auto()
    MAX_DRAWDOWN = auto()
    WIN_RATE = auto()


class AlertSeverity(Enum):
    """Alert severity levels"""

    INFO = auto()
    WARNING = auto()
    ERROR = auto()
    CRITICAL = auto()


@dataclass(slots=True)
class PerformanceMetric:
    """Individual performance metric"""

    name: str
    value: float
    metric_type: MetricType
    timestamp: datetime


@dataclass(slots=True)
class Alert:
    """System alert notification"""

    message: str
    severity: AlertSeverity
    timestamp: datetime
    resolved: bool = False


class ModelPerformanceReport(TypedDict):
    """Comprehensive model performance report"""

    model_version: str
    total_signals: int
    total_pnl: float
    accuracy_rate: float
    win_rate: float
    avg_confidence: float
    metrics: list[PerformanceMetric]
    alerts: NotRequired[list[Alert]]


# Order Management Types
class OrderAction(Enum):
    """Order actions"""

    BUY = auto()
    SELL = auto()


class OrderType(Enum):
    """Order types"""

    MARKET = auto()
    LIMIT = auto()
    STOP = auto()
    STOP_LIMIT = auto()


class OrderStatus(Enum):
    """Order status"""

    PENDING = auto()
    SUBMITTED = auto()
    FILLED = auto()
    CANCELLED = auto()
    REJECTED = auto()


@dataclass(slots=True)
class MLOrderMetadata:
    """ML-specific order metadata"""

    signal_id: str
    model_version: str
    strategy_name: str
    confidence_score: float
    predicted_price: float | None = None
    signal_timestamp: datetime | None = None


class MLExecutionQuality(TypedDict):
    """ML execution quality metrics"""

    signal_to_execution_latency: float
    price_improvement: float
    confidence_alignment: float
    execution_score: float


class MLExecutionReport(TypedDict):
    """ML-specific execution report"""

    signal_id: str
    execution_quality: MLExecutionQuality
    metadata: MLOrderMetadata
    actual_pnl: NotRequired[float]


# Export all public types
__all__ = [
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
]
