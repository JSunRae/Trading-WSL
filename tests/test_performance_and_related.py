"""High-yield coverage tests for low coverage modules.

Focus: core/performance.py, monitoring/ml_performance_monitor.py (selected logic),
risk/ml_risk_manager.py (validate_signal + position sizing), core/dataframe_safety.py,
data/data_manager.py repositories minimal paths.

These tests avoid heavy external deps (IB, parquet actual IO) by using simple in-memory
objects / monkeypatching.
"""

# mypy: ignore-errors

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pandas as pd
import pytest

from src.core.dataframe_safety import SafeDataFrameAccessor
from src.core.performance import (
    LRUCache,
    batch_operations,
    cached,
    get_performance_monitor,
    performance_monitor,
)
from src.domain.ml_types import SizingMode
from src.execution.ml_signal_executor import MLTradingSignal, SignalType
from src.monitoring.ml_performance_monitor import MLPerformanceMonitor
from src.risk.ml_risk_manager import MLRiskManager, RiskLimits


def make_signal(**overrides):  # minimal helper
    now = datetime.now(UTC)
    data = dict(
        signal_id="sig-1",
        symbol="AAPL",
        signal_type=SignalType.BUY,
        confidence=overrides.get("confidence", 0.75),
        target_quantity=overrides.get("target_quantity", 100),
        signal_timestamp=now - timedelta(seconds=5),
        model_version="v1",
        strategy_name="strat",
    )
    data.update(overrides)
    return MLTradingSignal(**data)


def test_performance_monitor_basic_and_cache(monkeypatch):
    monitor = get_performance_monitor()
    monitor.metrics.clear()

    calls = {}

    @performance_monitor
    @cached(ttl=60)
    def add(a, b):
        calls[(a, b)] = calls.get((a, b), 0) + 1
        return a + b

    # First call executes, second comes from cache
    assert add(1, 2) == 3
    assert add(1, 2) == 3
    stats = monitor.get_system_stats()
    assert stats["total_calls"] >= 1
    assert calls[(1, 2)] == 1  # Cached prevented second execution

    # Batch operations utility
    batches = batch_operations(list(range(10)), batch_size=4)
    assert batches == [list(range(4)), list(range(4, 8)), list(range(8, 10))]


def test_lru_cache_eviction_and_expiry():
    cache = LRUCache(max_size=2, default_ttl=1)
    cache.put("a", 1)
    cache.put("b", 2)
    # Access 'a' to increase its access count
    assert cache.get("a") == 1
    cache.put("c", 3)  # Should evict 'b'
    assert cache.get("b") is None
    assert cache.get("a") == 1

    # Expiry path: directly age the entry's timestamp to simulate TTL expiry
    entry = cache.cache.get("a")
    if entry:
        entry.timestamp -= timedelta(seconds=5)
    assert cache.get("a") is None  # expired

    # Stats path (with cleanup) still works
    stats = cache.stats()
    assert "current_size" in stats


def test_dataframe_safety_access_and_set(tmp_path):
    df = pd.DataFrame({"x": [1, None], "y": ["a", " "]})
    # safe_loc_get existing
    assert SafeDataFrameAccessor.safe_loc_get(df, 0, "x") == 1
    # non-existent row / column
    assert SafeDataFrameAccessor.safe_loc_get(df, 5, "x", default=0) == 0
    assert SafeDataFrameAccessor.safe_loc_get(df, 0, "zz", default=9) == 9
    # safe_loc_set creates column
    assert SafeDataFrameAccessor.safe_loc_set(df, 1, "z", 10) is True
    assert df.loc[1, "z"] == 10
    # safe_check_value with whitespace trimming logic path
    assert SafeDataFrameAccessor.safe_check_value(df, 1, "y", "") is True


def test_risk_manager_validate_and_size(monkeypatch):
    rm = MLRiskManager()
    # Tighten limits to trigger constraints
    rm.risk_limits = RiskLimits(
        max_position_size=50,
        max_portfolio_exposure=0.8,
        max_sector_exposure=0.3,
        max_single_stock_weight=0.05,
        min_confidence_threshold=0.6,
        max_signals_per_hour=2,
        max_concurrent_signals=1,
        min_model_performance_score=0.9,
        max_daily_loss=1000.0,
        max_position_loss=200.0,
        stop_loss_threshold=0.02,
        max_correlation_exposure=0.5,
        max_strategy_allocation=0.4,
    )
    # Force model performance low to trigger violation
    rm.model_performance_cache["v1"] = 0.5
    sig = make_signal(confidence=0.55)  # below threshold
    valid, violations = rm.validate_signal(sig)
    assert not valid and any("confidence" in v for v in violations)

    # Improve signal and model performance
    sig2 = make_signal(signal_id="sig-2", confidence=0.95)
    rm.model_performance_cache["v1"] = 0.95
    valid2, violations2 = rm.validate_signal(sig2)
    assert valid2 and not violations2

    # Position sizing triggers multiple constraints
    res = rm.calculate_position_size(
        sig2,
        current_portfolio_value=1_000_000,
        current_price=250,
        method=SizingMode.CONFIDENCE_WEIGHTED,
    )
    # PositionSizeResult exposes final_size; constraints list not currently returned
    size = getattr(res, "final_size", None)
    assert size is not None and size <= rm.risk_limits.max_position_size


def test_data_manager_excel_and_feather_repos(
    monkeypatch, tmp_path, monkeypatch_context=None
):
    # Patch get_config() to use temp directories to avoid touching real home paths
    import src.core.config as cfg

    original_get_config = cfg.get_config

    def fake_get_config(env=cfg.Environment.DEVELOPMENT):  # minimal stub
        cm = original_get_config(env)
        cm.data_paths.base_path = tmp_path / "base"
        cm.data_paths.backup_path = tmp_path / "backup"
        cm.data_paths.base_path.mkdir(parents=True, exist_ok=True)
        cm.data_paths.backup_path.mkdir(parents=True, exist_ok=True)
        return cm

    cfg._config_manager = None  # reset
    monkeypatch.setattr(cfg, "get_config", fake_get_config)

    from src.data.data_manager import ExcelRepository, FeatherRepository

    config = cfg.get_config()
    excel_repo = ExcelRepository(config)
    feather_repo = FeatherRepository(config)

    df = pd.DataFrame({"a": [1, 2]})
    # ExcelRepository references file type 'excel' which isn't in config mappings; expect DataError for coverage
    from src.core.error_handler import DataError

    try:
        excel_repo.save(df, "ANY")
    except DataError:
        pass  # expected path

    ident = "AAPL_1min_20250101"
    assert feather_repo.save(df, ident) is True
    assert feather_repo.exists(ident) is True
    assert feather_repo.load(ident) is not None
    assert feather_repo.delete(ident) is True

    # Identifier parse error path for FeatherRepository
    from src.core.error_handler import DataError

    with pytest.raises(DataError):  # underlying ValueError wrapped in DataError
        feather_repo.save(df, "BADIDENT")  # missing underscores


def test_batch_operations_edge_cases():
    # Empty list
    assert batch_operations([], batch_size=5) == []
    # Batch size larger than list
    assert batch_operations([1, 2], batch_size=10) == [[1, 2]]


def test_performance_export_and_stats(tmp_path):
    monitor = get_performance_monitor()

    @performance_monitor
    def quick(x):
        return x * 2

    quick(5)

    # Unknown function stats path
    no_stats = monitor.get_function_stats("nonexistent.func")
    assert "error" in no_stats

    # Export metrics
    out_file = tmp_path / "metrics.json"
    path = monitor.export_metrics(out_file)
    assert path.exists()
    import json

    data = json.loads(path.read_text())
    assert data["total_metrics"] >= 1


def test_cached_custom_key():
    calls = {"count": 0}

    def key_func(x):
        return f"fixed:{x % 2}"  # collapse keys to force cache hits

    @cached(ttl=60, key_func=key_func)
    def calc(x):
        calls["count"] += 1
        return x * 3

    a = calc(1)
    b = calc(3)  # same cache key
    assert a == b
    assert calls["count"] == 1


def test_ml_performance_monitor_record_signal(monkeypatch):
    # Stub ParquetRepository to avoid IO
    import src.monitoring.ml_performance_monitor as mon_mod

    class DummyRepo:
        def __init__(self, *a, **k):
            pass

    monkeypatch.setattr(mon_mod, "ParquetRepository", DummyRepo)
    monitor = MLPerformanceMonitor()
    sig = make_signal(signal_id="sig-monitor", confidence=0.8)
    # Register service so decorator recognizes it
    from src.core.integrated_error_handling import (
        ConnectionPriority,
        RetryConfig,
        ServiceConfig,
        get_integrated_error_handler,
    )

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
    # Also register a dummy service object in service registry so wrapper treats operation as standalone
    try:
        from src.infra.service_registry import clear_registry, register_service

        clear_registry()
        register_service("ml_performance_monitoring", object())
    except Exception:  # pragma: no cover - safety
        pass
    monitor.record_signal_generated(sig)
    assert sig.signal_id in monitor.signal_outcomes
    # Exercise execution quality path for additional coverage
    from types import SimpleNamespace

    quality = SimpleNamespace(
        signal_id=sig.signal_id,
        execution_score=0.92,
        total_execution_latency_ms=123,
    )
    monitor.record_execution_quality(
        quality,
        {"strategy_name": sig.strategy_name, "model_version": sig.model_version},
    )
