"""Test selected public API surface via src.api facade only (fake IB mode)."""

import os

os.environ.setdefault("FORCE_FAKE_IB", "1")

from src.api import (  # noqa: E402
    MLPerformanceMonitor,
    MLSignalExecutor,
    MLTradingSignal,
    SignalType,
    forex,
    stock,
)


def test_basic_contract_factories():
    s = stock("AAPL")
    fx = forex("EURUSD")
    assert s and fx


def test_basic_ml_services_smoke():
    exec_ = MLSignalExecutor()
    monitor = MLPerformanceMonitor()
    sig = MLTradingSignal(
        signal_id="api_surface_001",
        symbol="AAPL",
        signal_type=SignalType.BUY,
        value=150.0,
        confidence=0.7,
        target_quantity=10,
    )
    exec_.validate_signal(sig)
    # For now just ensure monitor instantiated and signal validated without exercising decorated methods
    assert monitor is not None and sig.signal_id == "api_surface_001"
