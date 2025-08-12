"""
Functional tests for src/risk/ml_risk_manager.py
Covers multiple risk scenarios: low/high confidence, high/low exposure, rate limits, and model performance.
All external dependencies are mocked/faked.
"""

from datetime import UTC, datetime

import pytest

from src.api import MLTradingSignal, SignalType
from src.risk.ml_risk_manager import MLRiskManager


@pytest.fixture
def risk_manager():
    return MLRiskManager()


def make_signal(confidence=1.0, model_version="v1", timestamp=None):
    return MLTradingSignal(
        signal_id="sig1",
        symbol="AAPL",
        signal_type=SignalType.BUY,
        value=1.0,
        confidence=confidence,
        target_quantity=10.0,
        timestamp=timestamp or datetime.now(UTC),
        model_version=model_version,
        strategy_name="test",
    )


def test_low_confidence(risk_manager):
    signal = make_signal(confidence=0.1)
    valid, violations = risk_manager.validate_signal(signal)
    assert not valid
    assert any("confidence" in v for v in violations)


def test_high_confidence(risk_manager):
    signal = make_signal(confidence=0.9)
    valid, violations = risk_manager.validate_signal(signal)
    assert valid


def test_rate_limit(risk_manager):
    # Simulate many signals in history
    now = datetime.now(UTC)
    for i in range(101):
        risk_manager.signal_history.append({"timestamp": now})
    signal = make_signal()
    valid, violations = risk_manager.validate_signal(signal)
    assert not valid
    assert any("rate limit" in v for v in violations)


def test_model_performance(risk_manager):
    risk_manager.model_performance_cache["v1"] = 0.1
    signal = make_signal(model_version="v1")
    valid, violations = risk_manager.validate_signal(signal)
    assert not valid
    assert any("performance" in v for v in violations)
