#!/usr/bin/env python3
"""
ML Order Management Enhancement

This service extends the OrderManagementService with ML-specific capabilities:
- ML signal metadata tracking
- Execution quality scoring for ML orders
- Signal-to-execution alignment monitoring
- ML-specific execution reports

Integrates with MLSignalExecutor to provide comprehensive ML trading execution.
"""

import logging
import sys
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.config import get_config
from src.core.integrated_error_handling import handle_error, with_error_handling
from src.data.parquet_repository import ParquetRepository
from src.execution.ml_signal_executor import MLTradingSignal
from src.services.order_management_service import (
    Fill,
    Order,
    OrderManagementService,
    OrderRequest,
    OrderStatus,
)


@dataclass
class MLOrderMetadata:
    """ML-specific metadata for orders"""

    # Original signal information
    signal_id: str
    model_version: str
    strategy_name: str
    confidence_score: float
    predicted_price: float | None
    signal_timestamp: datetime

    # Execution context
    urgency_level: str  # NORMAL, HIGH, CRITICAL
    max_execution_time_seconds: int
    expected_holding_period_minutes: int | None
    risk_score: float | None

    # Quality tracking
    signal_to_order_latency_ms: float | None = None
    execution_quality_score: float | None = None
    alignment_score: float | None = None

    def __post_init__(self):
        """Validate ML metadata"""
        if not (0.0 <= self.confidence_score <= 1.0):
            raise ValueError(f"Confidence must be 0.0-1.0, got {self.confidence_score}")

        if self.urgency_level not in ["NORMAL", "HIGH", "CRITICAL"]:
            raise ValueError(f"Invalid urgency: {self.urgency_level}")


@dataclass
class MLExecutionQuality:
    """Execution quality metrics for ML orders"""

    order_id: int
    signal_id: str

    # Latency metrics
    signal_to_order_latency_ms: float
    order_to_fill_latency_ms: float
    total_execution_latency_ms: float

    # Price execution quality
    intended_price: float | None
    executed_price: float
    price_slippage_bps: float  # basis points
    price_improvement_bps: float  # negative = slippage, positive = improvement

    # Volume execution quality
    intended_quantity: int
    executed_quantity: int
    fill_rate: float  # executed / intended

    # Market impact
    market_impact_bps: float | None = None
    effective_spread_bps: float | None = None

    # Overall scoring
    execution_score: float = 0.0  # 0-100 score
    alignment_score: float = 0.0  # How well execution matched signal

    def calculate_scores(self):
        """Calculate overall execution and alignment scores"""
        # Execution score based on speed, slippage, and fill rate
        speed_score = max(
            0, 100 - (self.total_execution_latency_ms / 1000) * 10
        )  # Penalty for slow execution
        slippage_score = max(
            0, 100 - abs(self.price_slippage_bps) * 2
        )  # Penalty for slippage
        fill_score = self.fill_rate * 100  # Reward for complete fills

        self.execution_score = (
            speed_score * 0.3 + slippage_score * 0.4 + fill_score * 0.3
        )

        # Alignment score based on how well execution matched signal intent
        price_alignment = (
            100 - abs(self.price_slippage_bps) if self.intended_price else 80
        )
        volume_alignment = self.fill_rate * 100
        timing_alignment = max(
            0, 100 - (self.signal_to_order_latency_ms / 100)
        )  # Penalty for delay

        self.alignment_score = (
            price_alignment * 0.4 + volume_alignment * 0.4 + timing_alignment * 0.2
        )


@dataclass
class MLExecutionReport:
    """Comprehensive execution report for ML strategies"""

    strategy_name: str
    time_period: tuple[datetime, datetime]
    total_signals: int
    executed_orders: int

    # Performance metrics
    avg_execution_score: float
    avg_alignment_score: float
    avg_signal_to_fill_latency_ms: float
    avg_slippage_bps: float
    total_commission: float

    # Success rates
    signal_execution_rate: float  # signals that became orders
    order_fill_rate: float  # orders that were filled
    partial_fill_rate: float

    # Quality distribution
    execution_score_distribution: dict[str, int]  # score ranges
    high_quality_executions: int  # score > 80
    low_quality_executions: int  # score < 50

    # Model performance correlation
    high_confidence_execution_quality: float  # avg score for confidence > 0.8
    low_confidence_execution_quality: float  # avg score for confidence < 0.5

    def generate_summary(self) -> str:
        """Generate human-readable summary"""
        return f"""
ML Execution Report - {self.strategy_name}
Period: {self.time_period[0].strftime("%Y-%m-%d %H:%M")} to {self.time_period[1].strftime("%Y-%m-%d %H:%M")}

📊 Execution Overview:
- Signals Processed: {self.total_signals:,}
- Orders Executed: {self.executed_orders:,}
- Signal→Order Rate: {self.signal_execution_rate:.1%}
- Order Fill Rate: {self.order_fill_rate:.1%}

⚡ Performance Metrics:
- Average Execution Score: {self.avg_execution_score:.1f}/100
- Average Alignment Score: {self.avg_alignment_score:.1f}/100
- Average Latency: {self.avg_signal_to_fill_latency_ms:.0f}ms
- Average Slippage: {self.avg_slippage_bps:.1f} bps

💰 Cost Analysis:
- Total Commission: ${self.total_commission:,.2f}
- Estimated Slippage Cost: ${(self.avg_slippage_bps / 10000) * 100000:,.2f} per $100k traded

🎯 Quality Distribution:
- High Quality (>80): {(self.high_quality_executions / self.executed_orders * 100):.1f}%
- Low Quality (<50): {(self.low_quality_executions / self.executed_orders * 100):.1f}%

🧠 Model Performance Correlation:
- High Confidence Execution Quality: {self.high_confidence_execution_quality:.1f}
- Low Confidence Execution Quality: {self.low_confidence_execution_quality:.1f}
"""


class MLOrderManagementService:
    """Enhanced order management with ML-specific capabilities"""

    def __init__(self, base_order_service: OrderManagementService):
        self.base_service = base_order_service
        self.config = get_config()
        self.parquet_repo = ParquetRepository()
        self.logger = logging.getLogger(__name__)

        # ML-specific tracking
        self.ml_orders: dict[int, MLOrderMetadata] = {}  # order_id -> metadata
        self.signal_orders: dict[str, list[int]] = defaultdict(
            list
        )  # signal_id -> order_ids
        self.execution_quality: dict[
            int, MLExecutionQuality
        ] = {}  # order_id -> quality

        # Performance tracking
        self.quality_history: deque[float] = deque(
            maxlen=10000
        )  # Recent execution quality
        self.latency_history: deque[float] = deque(
            maxlen=10000
        )  # Recent latency measurements

        # Real-time monitoring
        self.execution_alerts: list[str] = []
        self.quality_threshold = getattr(self.config, "ml_execution", {}).get(
            "min_quality_score", 70
        )
        self.latency_threshold_ms = getattr(self.config, "ml_execution", {}).get(
            "max_latency_ms", 500
        )

        # Register with base service for callbacks
        self.base_service.fill_handlers.append(self._handle_fill_callback)
        self.base_service.order_status_handlers.append(
            self._handle_order_status_callback
        )

    @with_error_handling("ml_order_management")
    def place_ml_order(
        self, signal: MLTradingSignal, order_request: OrderRequest
    ) -> tuple[Order, str]:
        """
        Place order with ML signal tracking

        Returns:
            Tuple of (Order, alert_message if any issues)
        """
        signal_received_time = datetime.now(UTC)
        alert_message = ""

        try:
            # Calculate signal-to-order latency
            signal_age_ms = (
                signal_received_time - signal.signal_timestamp
            ).total_seconds() * 1000

            # Check for stale signals
            max_signal_age_ms = getattr(self.config, "ml_execution", {}).get(
                "max_signal_age_ms", 5000
            )
            if signal_age_ms > max_signal_age_ms:
                alert_message = f"STALE SIGNAL: {signal_age_ms:.0f}ms old (max: {max_signal_age_ms}ms)"
                self.logger.warning(
                    f"Stale signal {signal.signal_id}: {signal_age_ms:.0f}ms old"
                )

            # Place order through base service
            order = self.base_service.place_order(
                None, order_request
            )  # Connection handled by base service

            # Create ML metadata
            ml_metadata = MLOrderMetadata(
                signal_id=signal.signal_id,
                model_version=signal.model_version,
                strategy_name=signal.strategy_name,
                confidence_score=signal.confidence,
                predicted_price=getattr(signal, "expected_return_pct", None),
                signal_timestamp=signal.signal_timestamp,
                urgency_level=signal.urgency,
                max_execution_time_seconds=signal.max_execution_time_seconds,
                expected_holding_period_minutes=signal.expected_holding_period_minutes,
                risk_score=signal.risk_score,
                signal_to_order_latency_ms=signal_age_ms,
            )

            # Store ML metadata
            self.ml_orders[order.order_id] = ml_metadata
            self.signal_orders[signal.signal_id].append(order.order_id)

            # Log ML order placement
            self.logger.info(
                f"ML Order placed: {order.order_id} for signal {signal.signal_id} "
                f"({signal.strategy_name}, confidence: {signal.confidence:.2f})"
            )

            return order, alert_message

        except Exception as e:
            error_msg = f"Failed to place ML order for signal {signal.signal_id}: {e}"
            handle_error(
                e,
                module=__name__,
                function="place_ml_order",
                context={
                    "signal_id": signal.signal_id,
                    "symbol": signal.symbol,
                    "confidence": signal.confidence,
                },
            )
            raise RuntimeError(error_msg) from e

    def _handle_fill_callback(self, fill: Fill):
        """Handle fill events for ML orders"""
        try:
            order_id = fill.order_id

            if order_id not in self.ml_orders:
                return  # Not an ML order

            ml_metadata = self.ml_orders[order_id]
            order = self.base_service.orders.get(order_id)

            if not order:
                return

            # Calculate execution quality
            fill_time = datetime.now(UTC)

            # Calculate latencies
            signal_to_order_latency = ml_metadata.signal_to_order_latency_ms or 0
            order_to_fill_latency = (
                (fill_time - order.submitted_time).total_seconds() * 1000
                if order.submitted_time
                else 0
            )
            total_latency = signal_to_order_latency + order_to_fill_latency

            # Calculate price metrics
            intended_price = ml_metadata.predicted_price or fill.price
            price_diff = fill.price - intended_price if intended_price else 0
            price_slippage_bps = (
                (price_diff / intended_price * 10000) if intended_price else 0
            )

            # Create quality assessment
            quality = MLExecutionQuality(
                order_id=order_id,
                signal_id=ml_metadata.signal_id,
                signal_to_order_latency_ms=signal_to_order_latency,
                order_to_fill_latency_ms=order_to_fill_latency,
                total_execution_latency_ms=total_latency,
                intended_price=intended_price,
                executed_price=fill.price,
                price_slippage_bps=price_slippage_bps,
                price_improvement_bps=-price_slippage_bps,  # Negative slippage is improvement
                intended_quantity=order.quantity,
                executed_quantity=fill.quantity,
                fill_rate=fill.quantity / order.quantity if order.quantity > 0 else 0,
            )

            # Calculate scores
            quality.calculate_scores()

            # Store quality metrics
            self.execution_quality[order_id] = quality
            self.quality_history.append(quality.execution_score)
            self.latency_history.append(total_latency)

            # Check for quality alerts
            if quality.execution_score < self.quality_threshold:
                alert = f"LOW QUALITY EXECUTION: Order {order_id} scored {quality.execution_score:.1f} (threshold: {self.quality_threshold})"
                self.execution_alerts.append(alert)
                self.logger.warning(alert)

            if total_latency > self.latency_threshold_ms:
                alert = f"HIGH LATENCY EXECUTION: Order {order_id} took {total_latency:.0f}ms (threshold: {self.latency_threshold_ms}ms)"
                self.execution_alerts.append(alert)
                self.logger.warning(alert)

            # Log execution quality
            self.logger.info(
                f"ML Execution Quality - Order {order_id}: "
                f"Score: {quality.execution_score:.1f}, "
                f"Latency: {total_latency:.0f}ms, "
                f"Slippage: {price_slippage_bps:.1f}bps"
            )

            # Save to Parquet for analysis
            self._save_execution_quality(quality, ml_metadata)

        except Exception as e:
            handle_error(e, module=__name__, function="_handle_fill_callback")

    def _handle_order_status_callback(self, order: Order):
        """Handle order status changes for ML orders"""
        try:
            if order.order_id not in self.ml_orders:
                return  # Not an ML order

            ml_metadata = self.ml_orders[order.order_id]

            # Log status changes with ML context
            self.logger.info(
                f"ML Order Status Update - {order.order_id}: {order.status.value} "
                f"(Signal: {ml_metadata.signal_id}, Strategy: {ml_metadata.strategy_name})"
            )

            # Handle timeouts for ML orders
            if order.status in [OrderStatus.SUBMITTED, OrderStatus.PARTIAL_FILLED]:
                submitted_time = order.submitted_time or order.created_time
                elapsed_seconds = (datetime.now() - submitted_time).total_seconds()

                if elapsed_seconds > ml_metadata.max_execution_time_seconds:
                    alert = f"ML ORDER TIMEOUT: Order {order.order_id} exceeded max execution time ({ml_metadata.max_execution_time_seconds}s)"
                    self.execution_alerts.append(alert)
                    self.logger.warning(alert)

                    # Could implement auto-cancellation here
                    # self.base_service.cancel_order(order.order_id)

        except Exception as e:
            handle_error(e, module=__name__, function="_handle_order_status_callback")

    def get_signal_execution_status(self, signal_id: str) -> dict[str, Any]:
        """Get execution status for a specific ML signal"""
        try:
            order_ids = self.signal_orders.get(signal_id, [])

            if not order_ids:
                return {"status": "NO_ORDERS", "signal_id": signal_id}

            orders_opt = [self.base_service.orders.get(oid) for oid in order_ids]
            orders: list[Order] = [o for o in orders_opt if o is not None]

            if not orders:
                return {"status": "ORDERS_NOT_FOUND", "signal_id": signal_id}

            # Aggregate status
            total_quantity: int = sum(o.quantity for o in orders)
            filled_quantity: int = sum(o.filled_quantity for o in orders)
            if filled_quantity > 0:
                numerator = sum(
                    float(o.avg_fill_price) * o.filled_quantity
                    for o in orders
                    if o.avg_fill_price is not None
                )
                avg_fill_price: float | None = (
                    numerator / filled_quantity if numerator else None
                )
            else:
                avg_fill_price = None

            # Get quality metrics
            quality_scores = [
                self.execution_quality[oid].execution_score
                for oid in order_ids
                if oid in self.execution_quality
            ]
            avg_quality = (
                sum(quality_scores) / len(quality_scores) if quality_scores else None
            )

            return {
                "status": "EXECUTED"
                if filled_quantity == total_quantity
                else "PARTIAL"
                if filled_quantity > 0
                else "PENDING",
                "signal_id": signal_id,
                "total_orders": len(orders),
                "total_quantity": total_quantity,
                "filled_quantity": filled_quantity,
                "fill_rate": filled_quantity / total_quantity
                if total_quantity > 0
                else 0,
                "avg_fill_price": avg_fill_price,
                "avg_execution_quality": avg_quality,
                "order_ids": order_ids,
            }

        except Exception as e:
            handle_error(e, module=__name__, function="get_signal_execution_status")
            return {"status": "ERROR", "signal_id": signal_id, "error": str(e)}

    def generate_execution_report(
        self, strategy_name: str | None = None, hours_lookback: int = 24
    ) -> MLExecutionReport:
        """Generate comprehensive ML execution report"""
        try:
            end_time = datetime.now(UTC)
            start_time = end_time - timedelta(hours=hours_lookback)

            # Filter orders by time and strategy
            relevant_orders = []
            for order_id, ml_meta in self.ml_orders.items():
                if ml_meta.signal_timestamp >= start_time:
                    if not strategy_name or ml_meta.strategy_name == strategy_name:
                        relevant_orders.append((order_id, ml_meta))

            if not relevant_orders:
                return MLExecutionReport(
                    strategy_name=strategy_name or "ALL_STRATEGIES",
                    time_period=(start_time, end_time),
                    total_signals=0,
                    executed_orders=0,
                    avg_execution_score=0,
                    avg_alignment_score=0,
                    avg_signal_to_fill_latency_ms=0,
                    avg_slippage_bps=0,
                    total_commission=0,
                    signal_execution_rate=0,
                    order_fill_rate=0,
                    partial_fill_rate=0,
                    execution_score_distribution={},
                    high_quality_executions=0,
                    low_quality_executions=0,
                    high_confidence_execution_quality=0,
                    low_confidence_execution_quality=0,
                )

            # Calculate metrics
            total_signals = len(
                set(ml_meta.signal_id for _, ml_meta in relevant_orders)
            )
            executed_orders = len(relevant_orders)

            # Get quality metrics
            quality_metrics = [
                self.execution_quality[oid]
                for oid, _ in relevant_orders
                if oid in self.execution_quality
            ]

            if quality_metrics:
                avg_execution_score = sum(
                    q.execution_score for q in quality_metrics
                ) / len(quality_metrics)
                avg_alignment_score = sum(
                    q.alignment_score for q in quality_metrics
                ) / len(quality_metrics)
                avg_latency = sum(
                    q.total_execution_latency_ms for q in quality_metrics
                ) / len(quality_metrics)
                avg_slippage = sum(q.price_slippage_bps for q in quality_metrics) / len(
                    quality_metrics
                )

                # Quality distribution
                high_quality = sum(1 for q in quality_metrics if q.execution_score > 80)
                low_quality = sum(1 for q in quality_metrics if q.execution_score < 50)

                # Confidence correlation
                high_conf_metrics = [
                    q
                    for oid, ml_meta in relevant_orders
                    if oid in self.execution_quality and ml_meta.confidence_score > 0.8
                    for q in [self.execution_quality[oid]]
                ]
                low_conf_metrics = [
                    q
                    for oid, ml_meta in relevant_orders
                    if oid in self.execution_quality and ml_meta.confidence_score < 0.5
                    for q in [self.execution_quality[oid]]
                ]

                high_conf_quality = (
                    sum(q.execution_score for q in high_conf_metrics)
                    / len(high_conf_metrics)
                    if high_conf_metrics
                    else 0
                )
                low_conf_quality = (
                    sum(q.execution_score for q in low_conf_metrics)
                    / len(low_conf_metrics)
                    if low_conf_metrics
                    else 0
                )
            else:
                avg_execution_score = avg_alignment_score = avg_latency = (
                    avg_slippage
                ) = 0
                high_quality = low_quality = 0
                high_conf_quality = low_conf_quality = 0

            # Calculate fill rates
            filled_orders = sum(
                1
                for oid, _ in relevant_orders
                if oid in self.base_service.orders
                and self.base_service.orders[oid].status == OrderStatus.FILLED
            )
            partial_orders = sum(
                1
                for oid, _ in relevant_orders
                if oid in self.base_service.orders
                and self.base_service.orders[oid].status == OrderStatus.PARTIAL_FILLED
            )

            # Calculate commission
            total_commission = sum(
                self.base_service.orders[oid].commission
                for oid, _ in relevant_orders
                if oid in self.base_service.orders
            )

            return MLExecutionReport(
                strategy_name=strategy_name or "ALL_STRATEGIES",
                time_period=(start_time, end_time),
                total_signals=total_signals,
                executed_orders=executed_orders,
                avg_execution_score=avg_execution_score,
                avg_alignment_score=avg_alignment_score,
                avg_signal_to_fill_latency_ms=avg_latency,
                avg_slippage_bps=avg_slippage,
                total_commission=total_commission,
                signal_execution_rate=executed_orders / total_signals
                if total_signals > 0
                else 0,
                order_fill_rate=filled_orders / executed_orders
                if executed_orders > 0
                else 0,
                partial_fill_rate=partial_orders / executed_orders
                if executed_orders > 0
                else 0,
                execution_score_distribution=self._calculate_score_distribution(
                    quality_metrics
                ),
                high_quality_executions=high_quality,
                low_quality_executions=low_quality,
                high_confidence_execution_quality=high_conf_quality,
                low_confidence_execution_quality=low_conf_quality,
            )

        except Exception as e:
            handle_error(e, module=__name__, function="generate_execution_report")
            raise

    def _calculate_score_distribution(
        self, quality_metrics: list[MLExecutionQuality]
    ) -> dict[str, int]:
        """Calculate distribution of execution scores"""
        if not quality_metrics:
            return {}

        distribution = {
            "90-100": 0,
            "80-89": 0,
            "70-79": 0,
            "60-69": 0,
            "50-59": 0,
            "0-49": 0,
        }

        for q in quality_metrics:
            score = q.execution_score
            if score >= 90:
                distribution["90-100"] += 1
            elif score >= 80:
                distribution["80-89"] += 1
            elif score >= 70:
                distribution["70-79"] += 1
            elif score >= 60:
                distribution["60-69"] += 1
            elif score >= 50:
                distribution["50-59"] += 1
            else:
                distribution["0-49"] += 1

        return distribution

    def _save_execution_quality(
        self, quality: MLExecutionQuality, metadata: MLOrderMetadata
    ):
        """Save execution quality data to Parquet for analysis"""
        try:
            # Combine quality and metadata for comprehensive logging
            log_data = {
                "timestamp": datetime.now(UTC).isoformat(),
                "order_id": quality.order_id,
                "signal_id": quality.signal_id,
                "strategy_name": metadata.strategy_name,
                "model_version": metadata.model_version,
                "confidence_score": metadata.confidence_score,
                "urgency_level": metadata.urgency_level,
                "execution_score": quality.execution_score,
                "alignment_score": quality.alignment_score,
                "total_latency_ms": quality.total_execution_latency_ms,
                "signal_to_order_latency_ms": quality.signal_to_order_latency_ms,
                "order_to_fill_latency_ms": quality.order_to_fill_latency_ms,
                "price_slippage_bps": quality.price_slippage_bps,
                "fill_rate": quality.fill_rate,
                "intended_quantity": quality.intended_quantity,
                "executed_quantity": quality.executed_quantity,
                "intended_price": quality.intended_price,
                "executed_price": quality.executed_price,
            }

            # Convert to DataFrame and save
            log_df = pd.DataFrame([log_data])
            log_df["timestamp"] = pd.to_datetime(log_df["timestamp"])
            log_df = log_df.set_index("timestamp")

            # Save with date for organization
            date_str = datetime.now().strftime("%Y-%m-%d")
            self.parquet_repo.save_data(
                log_df,
                symbol="ML_EXECUTION_QUALITY",
                timeframe="execution_logs",
                date_str=date_str,
            )

        except Exception as e:
            self.logger.error(f"Failed to save execution quality data: {e}")

    def get_recent_alerts(self, max_alerts: int = 10) -> list[str]:
        """Get recent execution alerts"""
        return self.execution_alerts[-max_alerts:]

    def clear_alerts(self):
        """Clear execution alerts"""
        self.execution_alerts.clear()

    def get_performance_summary(self) -> dict[str, Any]:
        """Get real-time performance summary"""
        try:
            recent_quality = (
                list(self.quality_history)[-100:] if self.quality_history else []
            )
            recent_latency = (
                list(self.latency_history)[-100:] if self.latency_history else []
            )

            return {
                "total_ml_orders": len(self.ml_orders),
                "recent_avg_quality": sum(recent_quality) / len(recent_quality)
                if recent_quality
                else 0,
                "recent_avg_latency_ms": sum(recent_latency) / len(recent_latency)
                if recent_latency
                else 0,
                "quality_trend": "improving"
                if len(recent_quality) >= 2 and recent_quality[-1] > recent_quality[0]
                else "declining"
                if len(recent_quality) >= 2
                else "stable",
                "active_alerts": len(self.execution_alerts),
                "orders_processed_today": len(
                    [
                        1
                        for ml_meta in self.ml_orders.values()
                        if ml_meta.signal_timestamp.date() == datetime.now().date()
                    ]
                ),
            }

        except Exception as e:
            handle_error(e, module=__name__, function="get_performance_summary")
            return {"error": str(e)}


# Convenience function for easy integration
def create_ml_order_service(
    base_order_service: OrderManagementService,
) -> MLOrderManagementService:
    """Create ML-enhanced order management service"""
    return MLOrderManagementService(base_order_service)


if __name__ == "__main__":
    # Demo the ML order management service
    print("🤖 ML Order Management Service Demo")
    print("=" * 40)

    # This would normally be integrated with the full system
    # Here we just demonstrate the structure
    print("✅ ML Order Management Service ready for integration")
    print("🔗 Integrates with MLSignalExecutor and OrderManagementService")
    print("📊 Provides execution quality scoring and ML-specific reporting")
    print("⚡ Monitors signal-to-execution alignment in real-time")
