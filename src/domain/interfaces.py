"""Service interfaces for ML trading infrastructure.

These Protocol classes define the contracts that service implementations must follow,
enabling proper type checking and eliminating Unknown types in tests.
"""

from __future__ import annotations

from typing import Protocol

from src.domain.ml_types import (
    ExecutionReport,
    MLTradingSignal,
    RiskAssessment,
    SizingMode,
)


class SignalValidator(Protocol):
    """Protocol for signal validation services."""

    def validate_signal(self, sig: MLTradingSignal) -> tuple[bool, list[str]]:
        """Validate a trading signal.

        Args:
            sig: The signal to validate

        Returns:
            Tuple of (is_valid, list_of_violations)
        """
        ...


class PositionSizer(Protocol):
    """Protocol for position sizing services."""

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
        ...

    def confidence_factor(self, sig: MLTradingSignal) -> float:
        """Calculate confidence factor for a signal.

        Args:
            sig: The trading signal

        Returns:
            Confidence factor between 0.0 and 1.0
        """
        ...


class RiskManager(Protocol):
    """Protocol for risk management services."""

    def assess_signal_risk(
        self,
        sig: MLTradingSignal,
        current_portfolio_positions: dict[str, int] | None = None,
        market_volatility: float = 0.2,
    ) -> RiskAssessment:
        """Assess risk for a trading signal.

        Args:
            sig: The trading signal
            current_portfolio_positions: Current positions
            market_volatility: Market volatility factor

        Returns:
            Risk assessment with score and level
        """
        ...


class PerformanceMonitor(Protocol):
    """Protocol for performance monitoring services."""

    def record_signal_generated(self, sig: MLTradingSignal) -> None:
        """Record that a signal was generated.

        Args:
            sig: The generated signal
        """
        ...

    def record_position_pnl(self, signal_id: str, pnl: float, is_final: bool = False) -> None:
        """Record P&L for a position.

        Args:
            signal_id: ID of the signal
            pnl: Profit/loss amount
            is_final: Whether this is the final P&L
        """
        ...

    def generate_model_report(self, model_name: str, days_lookback: int = 30) -> ExecutionReport:
        """Generate a performance report for a model.

        Args:
            model_name: Name of the model
            days_lookback: Number of days to look back

        Returns:
            Execution report with performance metrics
        """
        ...

    def get_dashboard_data(self) -> dict[str, float | int | str]:
        """Get dashboard data.

        Returns:
            Dictionary with dashboard metrics
        """
        ...


# Additional result types needed by the protocols
class PositionSizeResult:
    """Result of position sizing calculation."""

    def __init__(self, final_size: int, confidence_factor: float):
        self.final_size = final_size
        self.confidence_factor = confidence_factor
