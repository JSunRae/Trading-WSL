#!/usr/bin/env python3
"""
Test ML imports without requiring the full dependency chain
"""

from datetime import UTC


def test_direct_ml_imports():
    """Test importing ML modules directly (no returns)."""
    from src.execution.ml_signal_executor import MLTradingSignal, SignalType
    from src.risk.ml_risk_manager import MLRiskManager

    assert MLTradingSignal.__name__
    assert SignalType.BUY.name == "BUY"
    assert MLRiskManager.__name__
    assert hasattr(MLRiskManager, "validate_signal")


def test_ml_signal_creation():
    from datetime import datetime

    from src.execution.ml_signal_executor import MLTradingSignal, SignalType

    signal = MLTradingSignal(
        signal_id="test_001",
        symbol="AAPL",
        signal_type=SignalType.BUY,
        confidence=0.75,
        target_quantity=100,
        signal_timestamp=datetime.now(UTC),
        model_version="test_v1",
        strategy_name="test_strategy",
    )
    assert signal.signal_type is SignalType.BUY


def test_domain_api_imports():
    from src.api import MLTradingSignal as DomainMLTradingSignal
    from src.api import RiskLevel, SizingMode
    from src.api import SignalType as DomainSignalType

    assert DomainMLTradingSignal.__name__
    assert RiskLevel.LOW.name == "LOW"
    assert SizingMode.FIXED.name
    assert DomainSignalType.BUY.name == "BUY"


if __name__ == "__main__":  # pragma: no cover
    # Manual run for debugging
    test_direct_ml_imports()
    test_ml_signal_creation()
    test_domain_api_imports()
    print("Manual run complete")
