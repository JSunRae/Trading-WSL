#!/usr/bin/env python3
"""
ML Signal Executor

This service receives trading signals from the external ML repository and converts them
into executable trades via the Interactive Brokers API. It maintains full execution
tracking and validation without performing any feature engineering or data cleaning.

Key Responsibilities:
- Receive external ML trading signals
- Validate signal format and timing
- Convert signals to executable orders
- Track signal-to-execution alignment
- Monitor execution quality and latency
- Log all execution metadata for analysis

Architecture:
- Raw signal processing (no feature engineering)
- Low-latency execution pipeline
- Full execution audit trail
- Position reconciliation
- Risk management integration
"""

import logging
import sys
import threading
import time
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any
from typing import cast as _cast

import pandas as pd

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.config import get_config
from src.core.integrated_error_handling import with_error_handling
from src.data.parquet_repository import ParquetRepository
from src.domain.interfaces import PositionSizeResult
from src.domain.ml_types import SizingMode
from src.services.order_management_service import (
    OrderAction,
    OrderManagementService,
    OrderRequest,
    OrderStatus,
    OrderType,
    TimeInForce,
)


class SignalType(Enum):
    """Types of ML signals"""

    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"
    CLOSE_LONG = "CLOSE_LONG"
    CLOSE_SHORT = "CLOSE_SHORT"


class SignalStatus(Enum):
    """Signal processing status"""

    RECEIVED = "RECEIVED"
    VALIDATED = "VALIDATED"
    REJECTED = "REJECTED"
    EXECUTING = "EXECUTING"
    EXECUTED = "EXECUTED"
    FAILED = "FAILED"
    TIMEOUT = "TIMEOUT"


@dataclass
class MLTradingSignal:
    """
    Raw ML trading signal from external ML repository.
    No feature engineering - direct pass-through from ML system.
    """

    # Core signal data
    signal_id: str
    symbol: str
    signal_type: SignalType
    confidence: float  # 0.0 to 1.0
    target_quantity: int  # Signed: positive=long, negative=short

    # Timing and metadata
    signal_timestamp: datetime
    model_version: str
    strategy_name: str

    # Optional execution parameters
    max_execution_time_seconds: int = 300  # 5 minutes default
    price_tolerance_pct: float = 0.001  # 0.1% slippage tolerance
    urgency: str = "NORMAL"  # NORMAL, HIGH, CRITICAL

    # Optional risk parameters from ML repo
    expected_holding_period_minutes: int | None = None
    expected_return_pct: float | None = None
    risk_score: float | None = None

    def __post_init__(self):
        """Validate signal data"""
        if not (0.0 <= self.confidence <= 1.0):
            raise ValueError(f"Confidence must be 0.0-1.0, got {self.confidence}")

        # For CLOSE_LONG/CLOSE_SHORT the target_quantity isn't used; allow zero.
        if self.target_quantity == 0 and self.signal_type not in [
            SignalType.HOLD,
            SignalType.CLOSE_LONG,
            SignalType.CLOSE_SHORT,
        ]:
            raise ValueError("Non-HOLD signals must have non-zero quantity")

        if self.urgency not in ["NORMAL", "HIGH", "CRITICAL"]:
            raise ValueError(f"Invalid urgency: {self.urgency}")


@dataclass
class SignalExecution:
    """Tracks the execution of an ML signal"""

    signal_id: str
    signal: MLTradingSignal
    status: SignalStatus = SignalStatus.RECEIVED

    # Timing tracking
    received_time: datetime = field(default_factory=lambda: datetime.now(UTC))
    validation_time: datetime | None = None
    execution_start_time: datetime | None = None
    execution_complete_time: datetime | None = None

    # Execution details
    orders_created: list[int] = field(default_factory=list)
    total_filled_quantity: int = 0
    average_fill_price: float | None = None
    total_commission: float = 0.0

    # Performance metrics
    signal_to_execution_latency_ms: float | None = None
    execution_slippage_pct: float | None = None

    # Error tracking
    error_message: str | None = None
    retry_count: int = 0

    @property
    def is_complete(self) -> bool:
        """Check if execution is complete"""
        return self.status in [
            SignalStatus.EXECUTED,
            SignalStatus.FAILED,
            SignalStatus.TIMEOUT,
        ]

    @property
    def was_successful(self) -> bool:
        """Check if execution was successful"""
        return self.status == SignalStatus.EXECUTED


@dataclass
class ExecutionReport:
    """Comprehensive execution report for ML repository"""

    signal_id: str
    execution_summary: dict[str, Any]
    performance_metrics: dict[str, float]
    risk_metrics: dict[str, float]
    execution_quality: dict[str, Any]
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


class MLSignalExecutor:
    """
    Converts ML signals to executable trades with full tracking and validation.

    This is the critical bridge between the ML repository and the execution system.
    Maintains clean separation: no feature engineering, just raw signal execution.
    """

    def __init__(self, order_service: OrderManagementService | None = None):
        self.config = get_config()
        self.logger = logging.getLogger(__name__)

        # Core services
        self.order_service = order_service or OrderManagementService()
        self.parquet_repo = ParquetRepository()

        # Signal tracking
        self.active_signals: dict[str, SignalExecution] = {}
        self.completed_signals: dict[str, SignalExecution] = {}
        self._signal_lock = threading.Lock()

        # Performance tracking
        self.execution_stats = {
            "total_signals_received": 0,
            "signals_executed_successfully": 0,
            "signals_failed": 0,
            "signals_timed_out": 0,
            "average_latency_ms": 0.0,
            "average_slippage_pct": 0.0,
            "total_commission_paid": 0.0,
        }

        # Event handlers for ML repository callbacks
        self.signal_status_handlers: list[Callable[[SignalExecution], None]] = []
        self.execution_complete_handlers: list[Callable[[ExecutionReport], None]] = []

        # Risk management
        trading_config = getattr(self.config, "trading", {})
        if isinstance(trading_config, dict):
            # Help type checkers: ensure mapping[str, Any]
            tc_map = _cast(Mapping[str, Any], trading_config)
            mps_raw = tc_map.get("max_position_size", 1000)
            mdt_raw = tc_map.get("max_daily_trades", 100)
            try:
                self.max_position_size = int(mps_raw)  # type: ignore[assignment]
            except Exception:
                self.max_position_size = 1000
            try:
                self.max_daily_trades = int(mdt_raw)  # type: ignore[assignment]
            except Exception:
                self.max_daily_trades = 100
        else:
            self.max_position_size = int(
                getattr(trading_config, "max_position_size", 1000)
            )
            self.max_daily_trades = int(
                getattr(trading_config, "max_daily_trades", 100)
            )

        self.daily_trade_count = 0
        self.last_reset_date = datetime.now(UTC).date()

        self.logger.info("MLSignalExecutor initialized - ready to receive ML signals")

    # Implementation of SignalValidator and PositionSizer protocols
    def validate_signal(self, sig: MLTradingSignal) -> tuple[bool, list[str]]:
        """Validate a trading signal.

        Args:
            sig: The signal to validate

        Returns:
            Tuple of (is_valid, list_of_violations)
        """
        violations: list[str] = []

        # Check confidence range
        if sig.confidence < 0 or sig.confidence > 1:
            violations.append("confidence_out_of_range")

        # Check target quantity
        if sig.target_quantity == 0:
            violations.append("zero_target_quantity")

        # Check if symbol is valid (basic check)
        if not sig.symbol or len(sig.symbol) < 1:
            violations.append("invalid_symbol")

        # Check signal type
        if sig.signal_type not in [SignalType.BUY, SignalType.SELL, SignalType.HOLD]:
            violations.append("invalid_signal_type")

        return (len(violations) == 0, violations)

    def calculate_position_size(
        self,
        sig: MLTradingSignal,
        *,
        current_portfolio_value: float = 100000.0,
        current_price: float = 100.0,
        method: SizingMode = SizingMode.CONFIDENCE_WEIGHTED,
    ) -> PositionSizeResult:
        """Calculate position size for a signal.

        Args:
            sig: The trading signal
            current_portfolio_value: Current portfolio value
            current_price: Current market price
            method: Sizing method to use

        Returns:
            Position sizing result with final_size and confidence_factor
        """
        base_size = abs(sig.target_quantity)
        confidence_factor = self.confidence_factor(sig)

        if method == SizingMode.FIXED:
            final_size = base_size
        elif method == SizingMode.CONFIDENCE_WEIGHTED:
            final_size = int(base_size * confidence_factor)
        else:
            # Default to confidence weighted
            final_size = int(base_size * confidence_factor)

        return PositionSizeResult(
            final_size=final_size, confidence_factor=confidence_factor
        )

    def confidence_factor(self, sig: MLTradingSignal) -> float:
        """Calculate confidence factor for a signal.

        Args:
            sig: The trading signal

        Returns:
            Confidence factor between 0.0 and 1.0
        """
        return max(0.0, min(sig.confidence, 1.0))

    @with_error_handling("ml_signal_execution")
    def receive_signal(self, signal: MLTradingSignal) -> str:
        """
        Receive and process an ML trading signal.

        Args:
            signal: Raw ML trading signal from external ML repository

        Returns:
            str: Signal execution ID for tracking
        """
        execution_id = str(uuid.uuid4())

        with self._signal_lock:
            execution = SignalExecution(signal_id=execution_id, signal=signal)
            self.active_signals[execution_id] = execution
            self.execution_stats["total_signals_received"] += 1

        self.logger.info(
            f"Received ML signal {execution_id}: {signal.symbol} "
            f"{signal.signal_type.value} qty={signal.target_quantity} "
            f"confidence={signal.confidence:.3f}"
        )

        # Process signal asynchronously
        threading.Thread(
            target=self._process_signal_async, args=(execution_id,), daemon=True
        ).start()

        return execution_id

    def _process_signal_async(self, execution_id: str):
        """Process signal in background thread"""
        try:
            execution = self.active_signals[execution_id]

            # Step 1: Validate signal
            if not self._validate_signal(execution):
                return

            # Step 2: Execute signal
            if not self._execute_signal(execution):
                return

            # Step 3: Monitor execution
            self._monitor_execution(execution)

        except Exception as e:
            self.logger.error(f"Error processing signal {execution_id}: {e}")
            if execution_id in self.active_signals:
                self.active_signals[execution_id].status = SignalStatus.FAILED
                self.active_signals[execution_id].error_message = str(e)

    def _validate_signal(self, execution: SignalExecution) -> bool:
        """Validate ML signal before execution"""
        signal = execution.signal

        try:
            # Reset daily counter if new day
            current_date = datetime.now(UTC).date()
            if current_date > self.last_reset_date:
                self.daily_trade_count = 0
                self.last_reset_date = current_date

            # Check daily trade limit
            if self.daily_trade_count >= self.max_daily_trades:
                execution.status = SignalStatus.REJECTED
                execution.error_message = (
                    f"Daily trade limit exceeded ({self.max_daily_trades})"
                )
                self.logger.warning(
                    f"Signal {execution.signal_id} rejected: daily limit exceeded"
                )
                return False

            # Check position size limit
            if abs(signal.target_quantity) > self.max_position_size:
                execution.status = SignalStatus.REJECTED
                execution.error_message = f"Position size {signal.target_quantity} exceeds limit {self.max_position_size}"
                self.logger.warning(
                    f"Signal {execution.signal_id} rejected: position size too large"
                )
                return False

            # Check signal age (should be recent)
            signal_age = (datetime.now(UTC) - signal.signal_timestamp).total_seconds()
            if signal_age > 300:  # 5 minutes
                execution.status = SignalStatus.REJECTED
                execution.error_message = f"Signal too old: {signal_age:.1f} seconds"
                self.logger.warning(f"Signal {execution.signal_id} rejected: too old")
                return False

            # Check confidence threshold
            trading_config = getattr(self.config, "trading", {})
            if isinstance(trading_config, dict):
                tc_map = _cast(Mapping[str, Any], trading_config)
                mc_raw = tc_map.get("min_signal_confidence", 0.6)
                try:
                    min_confidence = float(mc_raw)  # type: ignore[assignment]
                except Exception:
                    min_confidence = 0.6
            else:
                min_confidence = getattr(trading_config, "min_signal_confidence", 0.6)

            if signal.confidence < min_confidence:
                execution.status = SignalStatus.REJECTED
                execution.error_message = f"Confidence {signal.confidence:.3f} below threshold {min_confidence}"
                self.logger.warning(
                    f"Signal {execution.signal_id} rejected: low confidence"
                )
                return False

            execution.status = SignalStatus.VALIDATED
            execution.validation_time = datetime.now(UTC)

            self.logger.info(f"Signal {execution.signal_id} validated successfully")
            return True

        except Exception as e:
            execution.status = SignalStatus.REJECTED
            execution.error_message = f"Validation error: {str(e)}"
            self.logger.error(
                f"Signal validation failed for {execution.signal_id}: {e}"
            )
            return False

    def _execute_signal(self, execution: SignalExecution) -> bool:
        """Convert validated signal to executable order"""
        signal = execution.signal

        try:
            execution.status = SignalStatus.EXECUTING
            execution.execution_start_time = datetime.now(UTC)

            # Determine order action and quantity
            if signal.signal_type == SignalType.BUY:
                action = OrderAction.BUY
                quantity = abs(signal.target_quantity)
            elif signal.signal_type == SignalType.SELL:
                action = OrderAction.SELL
                quantity = abs(signal.target_quantity)
            elif signal.signal_type in [SignalType.CLOSE_LONG, SignalType.CLOSE_SHORT]:
                # Get current position to determine close quantity
                current_position = self.order_service.get_position(signal.symbol)
                if not current_position or current_position.is_flat:
                    execution.error_message = (
                        f"No position to close for {signal.symbol}"
                    )
                    execution.status = SignalStatus.FAILED
                    return False

                if signal.signal_type == SignalType.CLOSE_LONG:
                    action = OrderAction.SELL
                    quantity = (
                        current_position.quantity
                        if current_position.quantity > 0
                        else 0
                    )
                else:  # CLOSE_SHORT
                    action = OrderAction.BUY
                    quantity = (
                        abs(current_position.quantity)
                        if current_position.quantity < 0
                        else 0
                    )

                if quantity == 0:
                    execution.error_message = (
                        f"No {signal.signal_type.value} position to close"
                    )
                    execution.status = SignalStatus.FAILED
                    return False
            else:  # HOLD
                execution.status = SignalStatus.EXECUTED
                execution.execution_complete_time = datetime.now(UTC)
                self.logger.info(f"HOLD signal {execution.signal_id} processed")
                return True

            # Create order request
            # Note: We currently don't have market data in this context to compute a safe
            # limit price. Previously we attempted to create a LIMIT order then mutate it
            # to MARKET as a fallback, but that triggers validation errors in OrderRequest.
            # To avoid invalid construction, directly use MARKET orders here.
            order_request = OrderRequest(
                symbol=signal.symbol,
                action=action,
                quantity=quantity,
                order_type=OrderType.MARKET,
                time_in_force=TimeInForce.DAY,
                outside_rth=False,
            )

            # Place order
            order = self.order_service.place_order(
                None, order_request
            )  # Connection will be injected

            if order:
                execution.orders_created.append(order.order_id)
                self.daily_trade_count += 1

                self.logger.info(
                    f"Order {order.order_id} placed for signal {execution.signal_id}"
                )
                return True
            else:
                execution.status = SignalStatus.FAILED
                execution.error_message = "Failed to place order"
                return False

        except Exception as e:
            execution.status = SignalStatus.FAILED
            execution.error_message = f"Execution error: {str(e)}"
            self.logger.error(f"Signal execution failed for {execution.signal_id}: {e}")
            return False

    def _monitor_execution(self, execution: SignalExecution):
        """Monitor order execution and update signal status"""
        signal = execution.signal

        # Ensure execution_start_time is set
        if execution.execution_start_time is None:
            execution.execution_start_time = datetime.now(UTC)

        timeout_time = self._compute_timeout_time(execution)

        while datetime.now(UTC) < timeout_time:
            try:
                all_filled, total_filled, total_value, total_commission = (
                    self._aggregate_orders_state(execution)
                )

                # Update execution tracking and averages
                self._update_execution_aggregates(
                    execution, total_filled, total_value, total_commission
                )

                if all_filled and total_filled > 0:
                    # Execution complete path
                    report = self._finalize_success(execution)
                    self.logger.info(
                        f"Signal {execution.signal_id} executed successfully: "
                        f"{total_filled} shares at avg ${execution.average_fill_price:.4f}"
                    )
                    self._notify_execution_complete_handlers(report)
                    return

                # Early failure if everything is inactive and nothing filled
                if self._all_orders_inactive(execution) and total_filled == 0:
                    execution.status = SignalStatus.FAILED
                    execution.error_message = "All orders failed or were cancelled"
                    self.execution_stats["signals_failed"] += 1
                    self.logger.warning(
                        f"Signal {execution.signal_id} failed - all orders cancelled/failed"
                    )
                    return

                # Wait before next poll
                time.sleep(1)

            except Exception as e:
                self.logger.error(
                    f"Error monitoring execution {execution.signal_id}: {e}"
                )
                time.sleep(1)

        # Timeout reached
        execution.status = SignalStatus.TIMEOUT
        execution.error_message = (
            f"Execution timeout after {signal.max_execution_time_seconds} seconds"
        )
        self.execution_stats["signals_timed_out"] += 1
        self.logger.warning(f"Signal {execution.signal_id} timed out")

    # ---- helpers for monitoring loop ----
    def _compute_timeout_time(self, execution: SignalExecution) -> datetime:
        """Return absolute timeout moment for an execution."""
        start = execution.execution_start_time or datetime.now(UTC)
        return start + timedelta(seconds=execution.signal.max_execution_time_seconds)

    def _aggregate_orders_state(
        self, execution: SignalExecution
    ) -> tuple[bool, int, float, float]:
        """Aggregate per-order state into simple totals.

        Returns: (all_filled, total_filled, total_value, total_commission)
        """
        all_filled = True
        total_filled = 0
        total_value = 0.0
        total_commission = 0.0
        for order_id in execution.orders_created:
            order = self.order_service.get_order(order_id)
            if not order:
                continue
            if order.status in (
                OrderStatus.PENDING_SUBMIT,
                OrderStatus.SUBMITTED,
                OrderStatus.PARTIAL_FILLED,
            ):
                all_filled = False
            total_filled += order.filled_quantity
            if order.avg_fill_price:
                total_value += order.filled_quantity * order.avg_fill_price
            total_commission += order.commission
        return all_filled, total_filled, total_value, total_commission

    def _update_execution_aggregates(
        self,
        execution: SignalExecution,
        total_filled: int,
        total_value: float,
        total_commission: float,
    ) -> None:
        """Update execution with aggregate totals and derived averages."""
        execution.total_filled_quantity = total_filled
        execution.total_commission = total_commission
        if total_filled > 0:
            execution.average_fill_price = total_value / total_filled

    def _finalize_success(self, execution: SignalExecution) -> ExecutionReport:
        """Finalize successful execution: statuses, stats, and report."""
        execution.status = SignalStatus.EXECUTED
        execution.execution_complete_time = datetime.now(UTC)
        execution.signal_to_execution_latency_ms = (
            execution.execution_complete_time - execution.received_time
        ).total_seconds() * 1000
        # Move to completed signals
        with self._signal_lock:
            self.completed_signals[execution.signal_id] = execution
            if execution.signal_id in self.active_signals:
                del self.active_signals[execution.signal_id]
        # Update global stats
        self.execution_stats["signals_executed_successfully"] += 1
        self.execution_stats["total_commission_paid"] += execution.total_commission
        # Build report
        return self._generate_execution_report(execution)

    def _all_orders_inactive(self, execution: SignalExecution) -> bool:
        """Return True if none of the orders are active."""
        for order_id in execution.orders_created:
            order = self.order_service.get_order(order_id)
            if order and order.is_active:
                return False
        return True

    def _generate_execution_report(self, execution: SignalExecution) -> ExecutionReport:
        """Generate comprehensive execution report for ML repository"""
        signal = execution.signal

        execution_summary = {
            "signal_id": execution.signal_id,
            "symbol": signal.symbol,
            "signal_type": signal.signal_type.value,
            "target_quantity": signal.target_quantity,
            "actual_quantity": execution.total_filled_quantity,
            "average_fill_price": execution.average_fill_price,
            "total_commission": execution.total_commission,
            "execution_status": execution.status.value,
        }

        performance_metrics = {
            "signal_to_execution_latency_ms": execution.signal_to_execution_latency_ms
            or 0.0,
            "fill_rate_pct": (
                execution.total_filled_quantity / abs(signal.target_quantity)
            )
            * 100
            if signal.target_quantity != 0
            else 0.0,
            "slippage_pct": execution.execution_slippage_pct or 0.0,
            "commission_per_share": execution.total_commission
            / max(execution.total_filled_quantity, 1),
        }

        risk_metrics = {
            "position_size_risk": abs(execution.total_filled_quantity)
            / max(self.max_position_size, 1),
            "confidence_score": float(signal.confidence),
        }

        execution_quality = {
            "orders_created": len(execution.orders_created),
            "retry_count": execution.retry_count,
            "execution_time_seconds": (
                execution.execution_complete_time - execution.execution_start_time
            ).total_seconds()
            if (execution.execution_complete_time and execution.execution_start_time)
            else None,
            "execution_urgency": signal.urgency,
        }

        return ExecutionReport(
            signal_id=execution.signal_id,
            execution_summary=execution_summary,
            performance_metrics=performance_metrics,
            risk_metrics=risk_metrics,
            execution_quality=execution_quality,
        )

    def get_signal_status(self, signal_id: str) -> SignalExecution | None:
        """Get current status of a signal execution"""
        with self._signal_lock:
            if signal_id in self.active_signals:
                return self.active_signals[signal_id]
            elif signal_id in self.completed_signals:
                return self.completed_signals[signal_id]
            else:
                return None

    def get_execution_stats(self) -> dict[str, Any]:
        """Get execution performance statistics"""
        with self._signal_lock:
            stats = self.execution_stats.copy()
            stats["active_signals"] = len(self.active_signals)
            stats["completed_signals"] = len(self.completed_signals)

            # Calculate success rate
            total_processed = (
                stats["signals_executed_successfully"]
                + stats["signals_failed"]
                + stats["signals_timed_out"]
            )
            if total_processed > 0:
                stats["success_rate_pct"] = (
                    stats["signals_executed_successfully"] / total_processed
                ) * 100
            else:
                stats["success_rate_pct"] = 0.0

            return stats

    def add_signal_status_handler(self, handler: Callable[[SignalExecution], None]):
        """Add callback for signal status updates"""
        self.signal_status_handlers.append(handler)

    def add_execution_complete_handler(
        self, handler: Callable[[ExecutionReport], None]
    ):
        """Add callback for execution completion"""
        self.execution_complete_handlers.append(handler)

    def _notify_signal_status_handlers(self, execution: SignalExecution):
        """Notify signal status handlers"""
        for handler in self.signal_status_handlers:
            try:
                handler(execution)
            except Exception as e:
                self.logger.error(f"Error in signal status handler: {e}")

    def _notify_execution_complete_handlers(self, report: ExecutionReport):
        """Notify execution complete handlers"""
        for handler in self.execution_complete_handlers:
            try:
                handler(report)
            except Exception as e:
                self.logger.error(f"Error in execution complete handler: {e}")

    @with_error_handling("execution_logging")
    def save_execution_log(self, execution: SignalExecution):
        """Save execution details to persistent storage"""
        try:
            # Choose a representative timestamp for the log row
            ts = execution.execution_complete_time or execution.received_time
            log_data = {
                "signal_id": execution.signal_id,
                "symbol": execution.signal.symbol,
                "signal_type": execution.signal.signal_type.value,
                "target_quantity": execution.signal.target_quantity,
                "confidence": execution.signal.confidence,
                "model_version": execution.signal.model_version,
                "strategy_name": execution.signal.strategy_name,
                "status": execution.status.value,
                "timestamp": ts.isoformat(),
                "received_time": execution.received_time.isoformat(),
                "execution_complete_time": execution.execution_complete_time.isoformat()
                if execution.execution_complete_time
                else None,
                "latency_ms": execution.signal_to_execution_latency_ms,
                "filled_quantity": execution.total_filled_quantity,
                "average_fill_price": execution.average_fill_price,
                "total_commission": execution.total_commission,
                "error_message": execution.error_message,
            }

            # Save to Parquet for analysis
            # Convert log data to DataFrame for Parquet storage
            log_df = pd.DataFrame([log_data])
            log_df["timestamp"] = pd.to_datetime(log_df["timestamp"], errors="coerce")
            log_df = log_df.set_index("timestamp", drop=True)

            # Use existing save_data method with execution logs
            ts_str = log_data.get("timestamp")
            date_str = ts_str[:10] if isinstance(ts_str, str) and ts_str else None
            self.parquet_repo.save_data(
                log_df, symbol="EXECUTION_LOG", timeframe="signals", date_str=date_str
            )

        except Exception as e:
            self.logger.error(
                f"Failed to save execution log for {execution.signal_id}: {e}"
            )


# Factory function for easy instantiation
def create_ml_signal_executor(
    order_service: OrderManagementService | None = None,
) -> MLSignalExecutor:
    """Create and configure ML signal executor"""
    return MLSignalExecutor(order_service)


# Example usage for ML repository integration
if __name__ == "__main__":
    # Example of how ML repository would use this service
    executor = create_ml_signal_executor()

    # Example signal from ML repository
    ml_signal = MLTradingSignal(
        signal_id="ml_model_v1_20250731_001",
        symbol="AAPL",
        signal_type=SignalType.BUY,
        confidence=0.75,
        target_quantity=100,
        signal_timestamp=datetime.now(UTC),
        model_version="lstm_v1.2.3",
        strategy_name="momentum_reversal",
    )

    # Process signal
    execution_id = executor.receive_signal(ml_signal)
    print(f"Signal submitted for execution: {execution_id}")

    # Monitor status
    import time

    for _ in range(30):  # Monitor for 30 seconds
        status = executor.get_signal_status(execution_id)
        if status:
            print(f"Status: {status.status.value}")
            if status.is_complete:
                break
        time.sleep(1)

    # Get final stats
    stats = executor.get_execution_stats()
    print(f"Execution stats: {stats}")
