import types
from datetime import UTC, datetime, timedelta

from src.monitoring.ml_performance_monitor import (
    AlertSeverity,
    MetricType,
    MLPerformanceMonitor,
)


class DummyRepo:
    def __init__(self, *a, **k):
        self.saved = []

    def save_data(self, df, symbol: str, timeframe: str, date_str: str):
        # record call arguments only
        self.saved.append((len(df), symbol, timeframe, date_str))


def _register_service():
    from src.core.integrated_error_handling import (
        ConnectionPriority,
        RetryConfig,
        ServiceConfig,
        get_integrated_error_handler,
    )
    from src.infra.service_registry import clear_registry, register_service

    handler = get_integrated_error_handler()
    if "ml_performance_monitoring" not in handler.service_configs:
        handler.register_service(
            ServiceConfig(
                name="ml_performance_monitoring",
                retry_config=RetryConfig(max_attempts=1, base_delay=0.01),
                priority=ConnectionPriority.LOW,
                timeout=1.0,
                failure_threshold=3,
            )
        )
    # Ensure a dummy service_obj is resolvable to avoid connection injection
    clear_registry()
    register_service("ml_performance_monitoring", object())


def test_anomaly_detection_and_dashboard(monkeypatch):
    # Stub ParquetRepository
    import src.monitoring.ml_performance_monitor as mon_mod

    monkeypatch.setattr(mon_mod, "ParquetRepository", DummyRepo)
    _register_service()

    m = MLPerformanceMonitor()

    # Feed metrics just under threshold and one large outlier
    for _ in range(15):
        m._record_metric(MetricType.MODEL_PERFORMANCE, "test_metric", 10.0)
    m._record_metric(MetricType.MODEL_PERFORMANCE, "test_metric", 100.0)

    # Trigger anomaly check
    m._check_metric_anomalies()
    alerts = m.get_recent_alerts()
    assert any("Anomaly" in a.title for a in alerts)

    # Update dashboard
    m._update_dashboard()
    dash = m.get_dashboard_data()
    assert dash["alerts"]["total_active"] >= 1
    assert "metrics" in dash


def test_status_and_alert_lifecycle(monkeypatch):
    import src.monitoring.ml_performance_monitor as mon_mod

    monkeypatch.setattr(mon_mod, "ParquetRepository", DummyRepo)
    _register_service()

    m = MLPerformanceMonitor()

    # Create multiple alerts of varying severity
    m._create_alert(AlertSeverity.WARNING, MetricType.LATENCY, "W1", "msg")
    m._create_alert(AlertSeverity.ERROR, MetricType.PNL, "E1", "msg")
    m._create_alert(AlertSeverity.CRITICAL, MetricType.PNL, "C1", "msg")

    m._update_dashboard()
    dash = m.get_dashboard_data()
    assert dash["system_status"] in {"CRITICAL", "ERROR", "WARNING", "HEALTHY"}

    # Acknowledge and resolve first alert
    first = m.get_recent_alerts(limit=1)[-1]
    assert m.acknowledge_alert(first.alert_id)
    assert m.resolve_alert(first.alert_id, "ok")


def test_signal_execution_report_and_save(monkeypatch):
    import src.monitoring.ml_performance_monitor as mon_mod

    monkeypatch.setattr(mon_mod, "ParquetRepository", DummyRepo)
    _register_service()

    m = MLPerformanceMonitor()

    # Build a minimal signal
    from src.execution.ml_signal_executor import MLTradingSignal, SignalType

    sig = MLTradingSignal(
        signal_id="s1",
        symbol="AAPL",
        signal_type=SignalType.BUY,
        confidence=0.7,
        target_quantity=10,
        signal_timestamp=datetime.now(UTC) - timedelta(days=1),
        model_version="v1",
        strategy_name="strat",
    )

    m.record_signal_generated(sig)

    # Execution quality using SimpleNamespace-like object
    q = types.SimpleNamespace(
        signal_id="s1",
        execution_score=80.0,
        total_execution_latency_ms=200.0,
        price_slippage_bps=1.0,
    )
    m.record_execution_quality(q, {"strategy_name": "strat", "model_version": "v1"})

    # Record PnL
    m.record_position_pnl("s1", 5.0, is_final=True)
    assert m.signal_outcomes["s1"]["final_pnl"] == 5.0
    assert m.signal_outcomes["s1"]["outcome_determined"] is True

    # Generate report
    report = m.generate_model_report("v1", strategy_name="strat", days_lookback=7)
    assert report.total_signals >= 1
    assert report.avg_confidence > 0

    # Save data (uses DummyRepo)
    m.save_performance_data()
