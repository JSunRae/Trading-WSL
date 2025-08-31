#!/usr/bin/env python3
"""
ML Performance Monitoring Dashboard

This service provides comprehensive monitoring for ML trading strategies:
- ML signal performance tracking
- Execution quality monitoring
- Model performance analytics
- Alert system for execution issues
- Real-time dashboard capabilities

Integrates with all ML trading components to provide unified monitoring.
"""

import logging
import math
import statistics
import sys
import threading
import time
import uuid
from collections import defaultdict, deque
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.config import get_config
from src.core.integrated_error_handling import handle_error, with_error_handling
from src.data.parquet_repository import ParquetRepository
from src.execution.ml_signal_executor import MLTradingSignal, SignalStatus
from src.services.ml_order_management_service import (
    MLExecutionQuality,
)


class AlertSeverity(Enum):
    """Alert severity levels"""

    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class MetricType(Enum):
    """Types of performance metrics"""

    LATENCY = "LATENCY"
    EXECUTION_QUALITY = "EXECUTION_QUALITY"
    MODEL_PERFORMANCE = "MODEL_PERFORMANCE"
    RISK_METRIC = "RISK_METRIC"
    PNL = "PNL"
    SIGNAL_ACCURACY = "SIGNAL_ACCURACY"


@dataclass
class Alert:
    """Performance monitoring alert"""

    alert_id: str
    timestamp: datetime
    severity: AlertSeverity
    metric_type: MetricType
    title: str
    message: str

    # Context
    strategy_name: str | None = None
    model_version: str | None = None
    symbol: str | None = None
    signal_id: str | None = None

    # Resolution
    acknowledged: bool = False
    resolved: bool = False
    resolution_note: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert alert to dictionary"""
        return asdict(self)


@dataclass
class PerformanceMetric:
    """Performance metric data point"""

    timestamp: datetime
    metric_type: MetricType
    metric_name: str
    value: float

    # Context
    strategy_name: str | None = None
    model_version: str | None = None
    symbol: str | None = None

    # Metadata
    target_value: float | None = None
    threshold_warning: float | None = None
    threshold_critical: float | None = None


@dataclass
class ModelPerformanceReport:
    """Comprehensive model performance report"""

    model_version: str
    strategy_name: str
    evaluation_period: tuple[datetime, datetime]

    # Signal metrics
    total_signals: int
    signals_executed: int
    execution_rate: float

    # Accuracy metrics
    correct_predictions: int
    total_predictions: int
    accuracy_rate: float
    precision: float
    recall: float
    f1_score: float

    # Financial performance
    total_pnl: float
    sharpe_ratio: float
    max_drawdown: float
    win_rate: float
    avg_win: float
    avg_loss: float
    profit_factor: float

    # Execution quality
    avg_execution_score: float
    avg_latency_ms: float
    avg_slippage_bps: float

    # Risk metrics
    var_95: float  # Value at Risk
    max_position_size: int
    avg_confidence: float

    def generate_summary(self) -> str:
        """Generate performance summary"""
        return f"""
Model Performance Report: {self.model_version}
Strategy: {self.strategy_name}
Period: {self.evaluation_period[0].strftime("%Y-%m-%d")} to {self.evaluation_period[1].strftime("%Y-%m-%d")}

📊 Signal Performance:
- Total Signals: {self.total_signals:,}
- Execution Rate: {self.execution_rate:.1%}
- Accuracy: {self.accuracy_rate:.1%}
- F1 Score: {self.f1_score:.3f}

💰 Financial Performance:
- Total P&L: ${self.total_pnl:,.2f}
- Sharpe Ratio: {self.sharpe_ratio:.2f}
- Max Drawdown: {self.max_drawdown:.1%}
- Win Rate: {self.win_rate:.1%}
- Profit Factor: {self.profit_factor:.2f}

⚡ Execution Quality:
- Avg Execution Score: {self.avg_execution_score:.1f}/100
- Avg Latency: {self.avg_latency_ms:.0f}ms
- Avg Slippage: {self.avg_slippage_bps:.1f}bps

🛡️ Risk Metrics:
- VaR (95%): ${self.var_95:,.2f}
- Avg Confidence: {self.avg_confidence:.2f}
"""


class MLPerformanceMonitor:
    """Comprehensive ML trading performance monitoring system"""

    def __init__(self):
        self.config = get_config()
        self.parquet_repo = ParquetRepository()
        self.logger = logging.getLogger(__name__)

        # Monitoring configuration
        monitor_config = getattr(self.config, "ml_monitoring", {})  # pyright: ignore[reportUnknownMemberType]  # dynamic config access
        self.latency_threshold_ms = monitor_config.get("latency_threshold_ms", 500)
        self.execution_quality_threshold = monitor_config.get(
            "execution_quality_threshold", 70
        )
        self.min_accuracy_threshold = monitor_config.get("min_accuracy_threshold", 0.6)
        self.max_drawdown_threshold = monitor_config.get("max_drawdown_threshold", 0.1)

        # Real-time data storage
        self.metrics: dict[str, deque] = defaultdict(
            lambda: deque(maxlen=10000)
        )  # metric_name -> values
        self.alerts: deque = deque(maxlen=1000)  # Recent alerts

        # Performance tracking
        self.strategy_performance: dict[str, dict] = defaultdict(
            dict
        )  # strategy -> metrics
        self.model_performance: dict[str, dict] = defaultdict(
            dict
        )  # model_version -> metrics
        self.signal_outcomes: dict[str, dict] = {}  # signal_id -> outcome data

        # Real-time dashboard data
        self.dashboard_data: dict[str, Any] = {}
        self.last_dashboard_update = datetime.now(UTC)

        # Threading for background monitoring
        self._monitoring_active = False
        self._monitor_thread: threading.Thread | None = None
        self._lock = threading.Lock()

        # Alert handlers
        self.alert_handlers: list[Callable[[Alert], None]] = []

    def start_monitoring(self):
        """Start background monitoring thread"""
        if self._monitoring_active:
            return

        self._monitoring_active = True
        self._monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._monitor_thread.start()
        self.logger.info("ML Performance monitoring started")

    def stop_monitoring(self):
        """Stop background monitoring"""
        self._monitoring_active = False
        if self._monitor_thread:
            self._monitor_thread.join(timeout=5)
        self.logger.info("ML Performance monitoring stopped")

    def _monitor_loop(self):
        """Background monitoring loop"""
        while self._monitoring_active:
            try:
                self._update_dashboard()
                self._check_alert_conditions()
                time.sleep(30)  # Update every 30 seconds
            except Exception as e:
                handle_error(e, module=__name__, function="_monitor_loop")
                time.sleep(60)  # Wait longer on error

    @with_error_handling("ml_performance_monitoring")
    def record_signal_generated(self, signal: MLTradingSignal):
        """Record when a new ML signal is generated"""
        try:
            with self._lock:
                # Store signal for outcome tracking
                self.signal_outcomes[signal.signal_id] = {
                    "signal": signal,
                    "generated_time": datetime.now(UTC),
                    "status": SignalStatus.RECEIVED,
                    "execution_data": None,
                    "final_pnl": None,
                    "outcome_determined": False,
                }

                # Update strategy metrics
                strategy_key = f"{signal.strategy_name}_{signal.model_version}"
                if strategy_key not in self.strategy_performance:
                    self.strategy_performance[strategy_key] = {
                        "total_signals": 0,
                        "confidence_sum": 0,
                        "signals_today": 0,
                    }

                self.strategy_performance[strategy_key]["total_signals"] += 1
                self.strategy_performance[strategy_key]["confidence_sum"] += (
                    signal.confidence
                )

                # Check if today's signal
                if signal.signal_timestamp.date() == datetime.now().date():
                    self.strategy_performance[strategy_key]["signals_today"] += 1

                # Record confidence metric
                self._record_metric(
                    MetricType.MODEL_PERFORMANCE,
                    "signal_confidence",
                    signal.confidence,
                    strategy_name=signal.strategy_name,
                    model_version=signal.model_version,
                )

                self.logger.debug(f"Recorded signal generation: {signal.signal_id}")

        except Exception as e:
            handle_error(e, module=__name__, function="record_signal_generated")

    @with_error_handling("ml_performance_monitoring")
    def record_execution_quality(
        self, quality: MLExecutionQuality, ml_metadata: dict[str, Any]
    ):
        """Record execution quality metrics"""
        try:
            with self._lock:
                # Update signal outcome
                if quality.signal_id in self.signal_outcomes:
                    self.signal_outcomes[quality.signal_id]["execution_data"] = quality
                    self.signal_outcomes[quality.signal_id]["status"] = (
                        SignalStatus.EXECUTED
                    )

                # Record execution metrics
                self._record_metric(
                    MetricType.EXECUTION_QUALITY,
                    "execution_score",
                    quality.execution_score,
                    strategy_name=ml_metadata.get("strategy_name"),
                    model_version=ml_metadata.get("model_version"),
                )

                self._record_metric(
                    MetricType.LATENCY,
                    "total_execution_latency",
                    quality.total_execution_latency_ms,
                    strategy_name=ml_metadata.get("strategy_name"),
                )

                self._record_metric(
                    MetricType.EXECUTION_QUALITY,
                    "price_slippage",
                    quality.price_slippage_bps,
                    strategy_name=ml_metadata.get("strategy_name"),
                )

                # Check for alerts
                if quality.execution_score < self.execution_quality_threshold:
                    self._create_alert(
                        AlertSeverity.WARNING,
                        MetricType.EXECUTION_QUALITY,
                        "Low Execution Quality",
                        f"Execution score {quality.execution_score:.1f} below threshold {self.execution_quality_threshold}",
                        strategy_name=ml_metadata.get("strategy_name"),
                        signal_id=quality.signal_id,
                    )

                if quality.total_execution_latency_ms > self.latency_threshold_ms:
                    self._create_alert(
                        AlertSeverity.WARNING,
                        MetricType.LATENCY,
                        "High Execution Latency",
                        f"Execution latency {quality.total_execution_latency_ms:.0f}ms above threshold {self.latency_threshold_ms}ms",
                        strategy_name=ml_metadata.get("strategy_name"),
                        signal_id=quality.signal_id,
                    )

                self.logger.debug(
                    f"Recorded execution quality for signal {quality.signal_id}"
                )

        except Exception as e:
            handle_error(e, module=__name__, function="record_execution_quality")

    @with_error_handling("ml_performance_monitoring")
    def record_position_pnl(self, signal_id: str, pnl: float, is_final: bool = False):
        """Record P&L for a position"""
        try:
            with self._lock:
                if signal_id in self.signal_outcomes:
                    self.signal_outcomes[signal_id]["final_pnl"] = pnl
                    if is_final:
                        self.signal_outcomes[signal_id]["outcome_determined"] = True

                # Record P&L metric
                signal_data = self.signal_outcomes.get(signal_id, {})
                signal = signal_data.get("signal")

                if signal:
                    self._record_metric(
                        MetricType.PNL,
                        "position_pnl",
                        pnl,
                        strategy_name=signal.strategy_name,
                        model_version=signal.model_version,
                        symbol=signal.symbol,
                    )

                self.logger.debug(f"Recorded P&L for signal {signal_id}: ${pnl:.2f}")

        except Exception as e:
            handle_error(e, module=__name__, function="record_position_pnl")

    def _record_metric(
        self,
        metric_type: MetricType,
        metric_name: str,
        value: float,
        strategy_name: str | None = None,
        model_version: str | None = None,
        symbol: str | None = None,
    ):
        """Record a performance metric"""
        metric = PerformanceMetric(
            timestamp=datetime.now(UTC),
            metric_type=metric_type,
            metric_name=metric_name,
            value=value,
            strategy_name=strategy_name,
            model_version=model_version,
            symbol=symbol,
        )

        # Store in time series
        metric_key = f"{metric_type.value}_{metric_name}"
        self.metrics[metric_key].append(metric)

    def _create_alert(
        self,
        severity: AlertSeverity,
        metric_type: MetricType,
        title: str,
        message: str,
        **context,
    ):
        """Create a new alert"""
        alert = Alert(
            alert_id=str(uuid.uuid4()),
            timestamp=datetime.now(UTC),
            severity=severity,
            metric_type=metric_type,
            title=title,
            message=message,
            **context,
        )

        self.alerts.append(alert)

        # Notify alert handlers
        for handler in self.alert_handlers:
            try:
                handler(alert)
            except Exception as e:
                self.logger.error(f"Alert handler failed: {e}")

        # Log alert
        self.logger.log(
            logging.ERROR
            if severity in [AlertSeverity.ERROR, AlertSeverity.CRITICAL]
            else logging.WARNING
            if severity == AlertSeverity.WARNING
            else logging.INFO,
            f"ALERT [{severity.value}] {title}: {message}",
        )

    def _update_dashboard(self):
        """Update dashboard data"""
        try:
            now = datetime.now(UTC)

            # Get recent metrics (last hour)
            recent_metrics: dict[str, dict[str, Any]] = {}
            for metric_key, metric_deque in self.metrics.items():
                recent_values = [
                    m.value
                    for m in metric_deque
                    if m.timestamp > now - timedelta(hours=1)
                ]
                if recent_values:
                    recent_metrics[metric_key] = {
                        "current": recent_values[-1],
                        "avg": statistics.mean(recent_values),
                        "min": min(recent_values),
                        "max": max(recent_values),
                        "count": len(recent_values),
                    }

            # Get active alerts
            active_alerts = [a for a in self.alerts if not a.resolved]

            # Update dashboard
            self.dashboard_data = {
                "last_updated": now.isoformat(),
                "system_status": self._determine_system_status(active_alerts),
                "metrics": recent_metrics,
                "alerts": {
                    "total_active": len(active_alerts),
                    "by_severity": {
                        severity.value: len(
                            [a for a in active_alerts if a.severity == severity]
                        )
                        for severity in AlertSeverity
                    },
                    "recent": [a.to_dict() for a in list(self.alerts)[-10:]],
                },
                "strategies": self._get_strategy_summary(),
                "models": self._get_model_summary(),
            }

            self.last_dashboard_update = now

        except Exception as e:
            handle_error(e, module=__name__, function="_update_dashboard")

    def _determine_system_status(self, active_alerts: list[Alert]) -> str:
        """Determine overall system status"""
        critical_alerts = [
            a for a in active_alerts if a.severity == AlertSeverity.CRITICAL
        ]
        error_alerts = [a for a in active_alerts if a.severity == AlertSeverity.ERROR]
        warning_alerts = [
            a for a in active_alerts if a.severity == AlertSeverity.WARNING
        ]

        if critical_alerts:
            return "CRITICAL"
        elif error_alerts:
            return "ERROR"
        elif len(warning_alerts) > 5:
            return "WARNING"
        else:
            return "HEALTHY"

    def _get_strategy_summary(self) -> dict[str, dict]:
        """Get summary of strategy performance"""
        summary = {}

        for strategy_key, data in self.strategy_performance.items():
            if data["total_signals"] > 0:
                avg_confidence = data["confidence_sum"] / data["total_signals"]
                summary[strategy_key] = {
                    "total_signals": data["total_signals"],
                    "signals_today": data.get("signals_today", 0),
                    "avg_confidence": avg_confidence,
                }

        return summary

    def _get_model_summary(self) -> dict[str, dict]:
        """Get summary of model performance"""
        summary = {}

        for model_version, data in self.model_performance.items():
            summary[model_version] = data

        return summary

    def _check_alert_conditions(self):
        """Check for conditions that should trigger alerts"""
        try:
            now = datetime.now(UTC)

            # Check for stale data
            if self.metrics:
                latest_metric_time = max(
                    max(m.timestamp for m in metric_deque)
                    for metric_deque in self.metrics.values()
                    if metric_deque
                )

                if now - latest_metric_time > timedelta(minutes=10):
                    self._create_alert(
                        AlertSeverity.WARNING,
                        MetricType.SIGNAL_ACCURACY,
                        "Stale Data Detected",
                        f"No metrics received for {(now - latest_metric_time).total_seconds() / 60:.0f} minutes",
                    )

            # Check for unusual patterns in recent metrics
            self._check_metric_anomalies()

        except Exception as e:
            handle_error(e, module=__name__, function="_check_alert_conditions")

    def _check_metric_anomalies(self):
        """Check for anomalies in metrics"""
        try:
            for metric_key, metric_deque in self.metrics.items():
                if len(metric_deque) < 10:
                    continue

                recent_values = [
                    m.value for m in list(metric_deque)[-20:]
                ]  # Last 20 values

                if len(recent_values) >= 10:
                    mean_val = statistics.mean(recent_values)
                    stdev = (
                        statistics.stdev(recent_values) if len(recent_values) > 1 else 0
                    )

                    # Check latest value against 2-sigma bounds
                    if stdev > 0:
                        latest_value = recent_values[-1]
                        z_score = abs(latest_value - mean_val) / stdev

                        if z_score > 2.5:  # More than 2.5 standard deviations
                            self._create_alert(
                                AlertSeverity.WARNING,
                                MetricType.MODEL_PERFORMANCE,
                                "Metric Anomaly Detected",
                                f"Unusual value in {metric_key}: {latest_value:.2f} (z-score: {z_score:.2f})",
                            )

        except Exception as e:
            self.logger.error(f"Error checking metric anomalies: {e}")

    @with_error_handling("ml_performance_monitoring")
    def generate_model_report(
        self,
        model_version: str,
        strategy_name: str | None = None,
        days_lookback: int = 30,
    ) -> ModelPerformanceReport:
        """Generate comprehensive model performance report"""
        try:
            end_time = datetime.now(UTC)
            start_time = end_time - timedelta(days=days_lookback)

            # Filter signals for this model
            relevant_signals = {}
            for signal_id, outcome_data in self.signal_outcomes.items():
                signal = outcome_data["signal"]
                if (
                    signal.model_version == model_version
                    and (not strategy_name or signal.strategy_name == strategy_name)
                    and signal.signal_timestamp >= start_time
                ):
                    relevant_signals[signal_id] = outcome_data

            if not relevant_signals:
                # Return empty report
                return ModelPerformanceReport(
                    model_version=model_version,
                    strategy_name=strategy_name or "ALL",
                    evaluation_period=(start_time, end_time),
                    total_signals=0,
                    signals_executed=0,
                    execution_rate=0,
                    correct_predictions=0,
                    total_predictions=0,
                    accuracy_rate=0,
                    precision=0,
                    recall=0,
                    f1_score=0,
                    total_pnl=0,
                    sharpe_ratio=0,
                    max_drawdown=0,
                    win_rate=0,
                    avg_win=0,
                    avg_loss=0,
                    profit_factor=0,
                    avg_execution_score=0,
                    avg_latency_ms=0,
                    avg_slippage_bps=0,
                    var_95=0,
                    max_position_size=0,
                    avg_confidence=0,
                )

            # Calculate metrics
            total_signals = len(relevant_signals)
            executed_signals = len(
                [
                    s
                    for s in relevant_signals.values()
                    if s["execution_data"] is not None
                ]
            )

            # Financial metrics
            pnl_values = [
                s["final_pnl"]
                for s in relevant_signals.values()
                if s["final_pnl"] is not None
            ]
            total_pnl = sum(pnl_values) if pnl_values else 0

            wins = [p for p in pnl_values if p > 0]
            losses = [p for p in pnl_values if p < 0]

            win_rate = len(wins) / len(pnl_values) if pnl_values else 0
            avg_win = statistics.mean(wins) if wins else 0
            avg_loss = statistics.mean(losses) if losses else 0

            # Execution quality metrics
            execution_data = [
                s["execution_data"]
                for s in relevant_signals.values()
                if s["execution_data"] is not None
            ]

            avg_execution_score = (
                statistics.mean([e.execution_score for e in execution_data])
                if execution_data
                else 0
            )
            avg_latency = (
                statistics.mean([e.total_execution_latency_ms for e in execution_data])
                if execution_data
                else 0
            )
            avg_slippage = (
                statistics.mean([e.price_slippage_bps for e in execution_data])
                if execution_data
                else 0
            )

            # Confidence metrics
            confidences = [s["signal"].confidence for s in relevant_signals.values()]
            avg_confidence = statistics.mean(confidences) if confidences else 0

            # Calculate additional metrics (simplified for demo)
            sharpe_ratio = (
                total_pnl / (statistics.stdev(pnl_values) * math.sqrt(252))
                if len(pnl_values) > 1
                else 0
            )
            max_drawdown = (
                min(pnl_values) / max(max(pnl_values), 1) if pnl_values else 0
            )
            profit_factor = (
                sum(wins) / abs(sum(losses)) if losses else float("inf") if wins else 0
            )
            var_95 = float(np.percentile(pnl_values, 5)) if pnl_values else 0.0

            return ModelPerformanceReport(
                model_version=model_version,
                strategy_name=strategy_name or "ALL",
                evaluation_period=(start_time, end_time),
                total_signals=total_signals,
                signals_executed=executed_signals,
                execution_rate=executed_signals / total_signals
                if total_signals > 0
                else 0,
                correct_predictions=len(wins),  # Simplified: positive PnL = correct
                total_predictions=len(pnl_values),
                accuracy_rate=win_rate,
                precision=win_rate,  # Simplified
                recall=win_rate,  # Simplified
                f1_score=win_rate,  # Simplified
                total_pnl=total_pnl,
                sharpe_ratio=sharpe_ratio,
                max_drawdown=max_drawdown,
                win_rate=win_rate,
                avg_win=avg_win,
                avg_loss=avg_loss,
                profit_factor=profit_factor,
                avg_execution_score=avg_execution_score,
                avg_latency_ms=avg_latency,
                avg_slippage_bps=avg_slippage,
                var_95=var_95,
                max_position_size=max(
                    [s["signal"].target_quantity for s in relevant_signals.values()],
                    default=0,
                ),
                avg_confidence=avg_confidence,
            )

        except Exception as e:
            handle_error(e, module=__name__, function="generate_model_report")
            raise

    def get_dashboard_data(self) -> dict[str, Any]:
        """Get current dashboard data"""
        # Update if stale
        if datetime.now(UTC) - self.last_dashboard_update > timedelta(minutes=1):
            self._update_dashboard()

        return self.dashboard_data.copy()

    def get_recent_alerts(
        self, severity: AlertSeverity | None = None, limit: int = 50
    ) -> list[Alert]:
        """Get recent alerts, optionally filtered by severity"""
        alerts = list(self.alerts)

        if severity:
            alerts = [a for a in alerts if a.severity == severity]

        return alerts[-limit:]

    def acknowledge_alert(self, alert_id: str, note: str | None = None) -> bool:
        """Acknowledge an alert"""
        for alert in self.alerts:
            if alert.alert_id == alert_id:
                alert.acknowledged = True
                if note:
                    alert.resolution_note = note
                self.logger.info(f"Alert {alert_id} acknowledged")
                return True
        return False

    def resolve_alert(self, alert_id: str, resolution_note: str) -> bool:
        """Resolve an alert"""
        for alert in self.alerts:
            if alert.alert_id == alert_id:
                alert.resolved = True
                alert.resolution_note = resolution_note
                self.logger.info(f"Alert {alert_id} resolved: {resolution_note}")
                return True
        return False

    def add_alert_handler(self, handler: Callable[[Alert], None]):
        """Add alert notification handler"""
        self.alert_handlers.append(handler)

    def save_performance_data(self):
        """Save performance data to Parquet for historical analysis"""
        try:
            # Save recent metrics
            all_metrics: list[dict[str, Any]] = []
            for _metric_key, metric_deque in self.metrics.items():
                for metric in list(metric_deque)[-1000:]:  # Last 1000 per metric
                    all_metrics.append(
                        {
                            "timestamp": metric.timestamp.isoformat(),
                            "metric_type": metric.metric_type.value,
                            "metric_name": metric.metric_name,
                            "value": metric.value,
                            "strategy_name": metric.strategy_name,
                            "model_version": metric.model_version,
                            "symbol": metric.symbol,
                        }
                    )

            if all_metrics:
                metrics_df = pd.DataFrame(all_metrics)
                metrics_df["timestamp"] = pd.to_datetime(metrics_df["timestamp"])
                metrics_df = metrics_df.set_index("timestamp")

                date_str = datetime.now().strftime("%Y-%m-%d")
                self.parquet_repo.save_data(
                    metrics_df,
                    symbol="ML_PERFORMANCE_METRICS",
                    timeframe="monitoring",
                    date_str=date_str,
                )

            # Save alerts
            alert_data = [a.to_dict() for a in list(self.alerts)[-1000:]]
            if alert_data:
                alerts_df = pd.DataFrame(alert_data)
                alerts_df["timestamp"] = pd.to_datetime(alerts_df["timestamp"])
                alerts_df = alerts_df.set_index("timestamp")

                self.parquet_repo.save_data(
                    alerts_df,
                    symbol="ML_ALERTS",
                    timeframe="monitoring",
                    date_str=date_str,
                )

        except Exception as e:
            handle_error(e, module=__name__, function="save_performance_data")


# Convenience function for integration
def create_ml_performance_monitor() -> MLPerformanceMonitor:
    """Create ML performance monitoring service"""
    monitor = MLPerformanceMonitor()
    monitor.start_monitoring()
    return monitor


if __name__ == "__main__":
    # Demo the ML performance monitoring service
    print("📊 ML Performance Monitoring Service Demo")
    print("=" * 45)

    monitor = MLPerformanceMonitor()
    monitor.start_monitoring()

    print("✅ ML Performance Monitor initialized and started")
    print("📈 Real-time monitoring of ML trading performance")
    print("🚨 Alert system for execution issues and anomalies")
    print("📋 Comprehensive dashboard and reporting capabilities")

    # Show dashboard structure
    dashboard = monitor.get_dashboard_data()
    print(f"\n📊 Dashboard Status: {dashboard.get('system_status', 'UNKNOWN')}")
    print(f"🔔 Active Alerts: {dashboard.get('alerts', {}).get('total_active', 0)}")

    time.sleep(2)
    monitor.stop_monitoring()
    print("\n✅ Demo completed")
