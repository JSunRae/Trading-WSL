"""
Test fixtures for ML trading system.

Provides typed fixtures to eliminate unknown types in tests.
"""

import asyncio
from datetime import UTC, datetime

import pytest

from src.domain.ml_types import (
    ExecutionReport,
    MLTradingSignal,
    PositionSizeResult,
    RiskAssessment,
    RiskLevel,
    SignalType,
    SizingMode,
)
from src.infra.service_registry import clear_registry, register_service


@pytest.fixture(autouse=True)
def register_test_services(fake_ib: object) -> None:
    """Register required services for IntegratedErrorHandler tests."""
    clear_registry()

    # Register fake ML signal execution service
    class FakeMLSignalExecution:
        def execute(self, *args: object, **kwargs: object) -> str:
            return "executed"

    register_service("ml_signal_execution", FakeMLSignalExecution())

    # Register fake ML risk management service
    class FakeMLRiskManagement:
        def assess(self, *args: object, **kwargs: object) -> str:
            return "assessed"

    register_service("ml_risk_management", FakeMLRiskManagement())


# Import required domain types directly to avoid pulling full public API (which
# transitively imports optional IB infrastructure) during test collection when
# the optional dependency may be absent.
# IB fixtures ---------------------------------------------------------------
try:  # Local availability shim
    from src.infra._ib_availability import ib_available
except Exception:  # pragma: no cover - extremely unlikely

    def ib_available() -> bool:  # type: ignore
        # Fallback: dependency unavailable
        return False


@pytest.fixture(scope="session")
def fake_ib():  # type: ignore[reportUnknownParameterType]
    """Provide a lightweight in-memory IB test double for unit tests."""
    from tests.fakes.fake_ib import FakeIB

    ib = FakeIB()
    return ib


@pytest.fixture(scope="session")
def ib_client(fake_ib):  # type: ignore[reportUnknownParameterType]
    """Default IB client fixture (fake unless real dependency installed)."""
    if ib_available():  # prefer real when installed but avoid auto-connect
        pytest.skip("Real ib_async installed; use explicit real_ib_client fixture")
    return fake_ib


@pytest.fixture(scope="session")
def real_ib_client():  # type: ignore[reportUnknownParameterType]
    """Optional real IB client (skipped if dependency missing)."""
    if not ib_available():
        pytest.skip("ib_async not installed; skipping real IB client fixture")
    # Lazy import & connection
    from src.infra.ib_client import get_ib  # type: ignore

    return asyncio.get_event_loop().run_until_complete(get_ib())


@pytest.fixture
def sample_signal() -> MLTradingSignal:
    """Sample trading signal for tests."""
    return MLTradingSignal(
        signal_id="TEST_001",
        symbol="AAPL",
        signal_type=SignalType.BUY,
        value=150.25,
        confidence=0.85,
        target_quantity=100.0,
        timestamp=datetime.now(UTC),
        model_version="test_v1",
        strategy_name="test_strategy",
    )


@pytest.fixture
def sample_sell_signal() -> MLTradingSignal:
    """Sample sell signal for tests."""
    return MLTradingSignal(
        signal_id="TEST_002",
        symbol="MSFT",
        signal_type=SignalType.SELL,
        value=300.50,
        confidence=0.75,
        target_quantity=50.0,
        timestamp=datetime.now(UTC),
        model_version="test_v1",
        strategy_name="test_strategy",
    )


@pytest.fixture
def sample_execution_report() -> ExecutionReport:
    """Sample execution report for tests."""
    return ExecutionReport(
        total_signals=10,
        successful_executions=8,
        total_pnl=1250.50,
        accuracy_rate=0.8,
        avg_execution_time=2.5,
        total_volume=1000.0,
    )


@pytest.fixture
def sample_risk_assessment() -> RiskAssessment:
    """Sample risk assessment for tests."""
    return RiskAssessment(
        risk_score=0.3,
        overall_risk_level=RiskLevel.LOW,
        recommended_action="trade",
        risk_factors=["low_volatility", "high_confidence"],
    )


@pytest.fixture
def sample_position_result() -> PositionSizeResult:
    """Sample position sizing result for tests."""
    return PositionSizeResult(
        final_size=100.0,
        confidence_factor=0.85,
        risk_adjusted=True,
        max_size=150.0,
        sizing_method=SizingMode.CONFIDENCE_WEIGHTED,
    )
