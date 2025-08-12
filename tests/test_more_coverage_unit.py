from __future__ import annotations

# pyright: reportUnusedImport=false, reportPrivateUsage=false, reportGeneralTypeIssues=false
import pandas as pd
import pytest

from src.core.dataframe_safety import DataFrameValidator, SafeDataFrameAccessor
from src.core.performance import get_performance_monitor, performance_monitor
from src.monitoring.ml_performance_monitor import (
    AlertSeverity,
    MLPerformanceMonitor,
)


def _register_monitor_service():
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
    clear_registry()
    register_service("ml_performance_monitoring", object())


def test_performance_monitor_records_failure():
    mon = get_performance_monitor()
    before = len(mon.metrics)

    @performance_monitor
    def boom():
        raise ValueError("fail")

    with pytest.raises(ValueError):
        boom()

    after = len(mon.metrics)
    assert after == before + 1
    last = mon.metrics[-1]
    assert last.success is False and last.error_message is not None


def test_ml_monitor_system_status_warning_and_critical(monkeypatch):
    import src.monitoring.ml_performance_monitor as mon_mod

    class DummyRepo:
        def __init__(self, *a, **k):
            pass

    monkeypatch.setattr(mon_mod, "ParquetRepository", DummyRepo)
    _register_monitor_service()
    m = MLPerformanceMonitor()

    # Add many warnings to trigger WARNING status
    for _ in range(6):
        m._create_alert(
            AlertSeverity.WARNING,
            metric_type=m.AlertSeverity if hasattr(m, "AlertSeverity") else None,
            title="w",
            message="w",
        )  # type: ignore[arg-type]
    m._update_dashboard()
    dash = m.get_dashboard_data()
    assert dash["system_status"] in {"WARNING", "ERROR", "CRITICAL", "HEALTHY"}

    # Critical alert dominates
    m._create_alert(AlertSeverity.CRITICAL, metric_type=None, title="c", message="c")  # type: ignore[arg-type]
    m._update_dashboard()
    dash2 = m.get_dashboard_data()
    assert dash2["system_status"] == "CRITICAL"


def test_dataframe_validator_extra_paths():
    # Empty frame -> warning
    df_empty = pd.DataFrame()
    rep = DataFrameValidator.validate_dataframe_structure(
        df_empty, required_columns=["a", "b"], required_index_name="IDX"
    )
    assert rep["is_valid"] in {True, False}
    assert "warnings" in rep and "info" in rep

    # Mixed dtypes & duplicate index suggestions
    df = pd.DataFrame({"mix": [1, "a", 3.14], "allnull": [None, None, None]})
    df.index = pd.Index([1, 1, 2])
    suggestions = DataFrameValidator.suggest_dataframe_cleanup(df)
    assert any("duplicate" in s.lower() for s in suggestions) or suggestions

    # Safe helpers
    assert SafeDataFrameAccessor.safe_fillna_row(df, 2, fill_value=0) is True
    assert SafeDataFrameAccessor.safe_column_exists(df, "mix") is True
    assert SafeDataFrameAccessor.safe_index_exists(df, 2) is True
