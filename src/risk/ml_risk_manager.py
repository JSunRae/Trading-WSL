#!/usr/bin/env python3
"""
ML Risk Management Integration

This service provides ML-specific risk management capabilities:
- ML confidence-based position sizing
- Dynamic risk limits based on model performance
- ML signal validation rules
- Portfolio-level ML signal coordination

Integrates with MLSignalExecutor and MLOrderManagementService to provide
comprehensive risk oversight for ML trading strategies.
"""

import logging
import sys
import threading
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
from src.domain.interfaces import RiskManager
from src.domain.ml_types import (
    MLTradingSignal,
    PositionSizeResult,
    RiskAssessment,
    RiskLevel,
    SizingMode,  # Keep this for method parameter
)


@dataclass
class RiskLimits:
    """Risk limits configuration"""

    # Position limits
    max_position_size: int  # Maximum shares per position
    max_portfolio_exposure: float  # Maximum portfolio value at risk (0-1)
    max_sector_exposure: float  # Maximum exposure per sector (0-1)
    max_single_stock_weight: float  # Maximum weight per stock (0-1)

    # ML-specific limits
    min_confidence_threshold: float  # Minimum signal confidence (0-1)
    max_signals_per_hour: int  # Rate limiting
    max_concurrent_signals: int  # Maximum active signals
    min_model_performance_score: float  # Minimum recent model performance

    # Drawdown and loss limits
    max_daily_loss: float  # Maximum daily loss in dollars
    max_position_loss: float  # Maximum loss per position
    stop_loss_threshold: float  # Automatic stop loss trigger

    # Correlation and concentration
    max_correlation_exposure: float  # Max exposure to correlated positions
    max_strategy_allocation: float  # Max allocation per strategy

    def __post_init__(self):
        """Validate risk limits"""
        if not (0.0 <= self.max_portfolio_exposure <= 1.0):
            raise ValueError("max_portfolio_exposure must be 0-1")
        if not (0.0 <= self.min_confidence_threshold <= 1.0):
            raise ValueError("min_confidence_threshold must be 0-1")


class MLRiskManager(RiskManager):
    """ML-specific risk management system"""

    def __init__(self):
        self.config = get_config()
        self.parquet_repo = ParquetRepository()
        self.logger = logging.getLogger(__name__)

        # Load risk limits from config
        risk_config = getattr(self.config, "ml_risk_management", {})
        self.risk_limits = RiskLimits(
            max_position_size=risk_config.get("max_position_size", 10000),
            max_portfolio_exposure=risk_config.get("max_portfolio_exposure", 0.8),
            max_sector_exposure=risk_config.get("max_sector_exposure", 0.3),
            max_single_stock_weight=risk_config.get("max_single_stock_weight", 0.1),
            min_confidence_threshold=risk_config.get("min_confidence_threshold", 0.6),
            max_signals_per_hour=risk_config.get("max_signals_per_hour", 100),
            max_concurrent_signals=risk_config.get("max_concurrent_signals", 50),
            min_model_performance_score=risk_config.get(
                "min_model_performance_score", 0.5
            ),
            max_daily_loss=risk_config.get("max_daily_loss", 10000.0),
            max_position_loss=risk_config.get("max_position_loss", 1000.0),
            stop_loss_threshold=risk_config.get("stop_loss_threshold", 0.02),
            max_correlation_exposure=risk_config.get("max_correlation_exposure", 0.5),
            max_strategy_allocation=risk_config.get("max_strategy_allocation", 0.4),
        )

        # Tracking
        self.active_signals: dict[str, MLTradingSignal] = {}  # signal_id -> signal
        # Signal tracking for rate limiting
        self.signal_history: deque[dict[str, Any]] = deque(
            maxlen=1000
        )  # Keep last 1000 signals
        self.model_performance_cache: dict[
            str, float
        ] = {}  # model_version -> performance
        self.sector_exposures: dict[str, float] = defaultdict(
            float
        )  # sector -> exposure
        self.position_correlations: dict[
            tuple[str, str], float
        ] = {}  # (symbol1, symbol2) -> correlation

        # Risk monitoring
        self.risk_breaches: list[dict[str, Any]] = []
        self.daily_pnl_tracker: dict[str, float] = defaultdict(float)  # date -> pnl

        # Threading
        self._lock = threading.Lock()

    @with_error_handling("ml_risk_management")
    def validate_signal(self, signal: MLTradingSignal) -> tuple[bool, list[str]]:
        """
        Validate ML signal against risk rules

        Returns:
            Tuple of (is_valid, list_of_violations)
        """
        violations: list[str] = []

        try:
            with self._lock:
                # Check confidence threshold
                if signal.confidence < self.risk_limits.min_confidence_threshold:
                    violations.append(
                        f"Signal confidence {signal.confidence:.2f} below threshold {self.risk_limits.min_confidence_threshold:.2f}"
                    )

                # Check rate limiting
                recent_signals: list[dict[str, Any]] = [
                    s
                    for s in self.signal_history
                    if s["timestamp"] > datetime.now(UTC) - timedelta(hours=1)
                ]
                if len(recent_signals) >= self.risk_limits.max_signals_per_hour:
                    violations.append(
                        f"Signal rate limit exceeded: {len(recent_signals)}/{self.risk_limits.max_signals_per_hour} per hour"
                    )

                # Check concurrent signal limits
                active_count = len(self.active_signals)
                if active_count >= self.risk_limits.max_concurrent_signals:
                    violations.append(
                        f"Maximum concurrent signals reached: {active_count}/{self.risk_limits.max_concurrent_signals}"
                    )

                # Check model performance
                model_performance = self.model_performance_cache.get(
                    signal.model_version, 1.0
                )  # Default to good if unknown
                if model_performance < self.risk_limits.min_model_performance_score:
                    violations.append(
                        f"Model performance {model_performance:.2f} below threshold {self.risk_limits.min_model_performance_score:.2f}"
                    )

                # Check daily loss limits
                today = datetime.now().strftime("%Y-%m-%d")
                daily_loss = abs(
                    min(0, self.daily_pnl_tracker[today])
                )  # Only count losses
                if daily_loss > self.risk_limits.max_daily_loss:
                    violations.append(
                        f"Daily loss limit exceeded: ${daily_loss:,.2f} > ${self.risk_limits.max_daily_loss:,.2f}"
                    )

                # Log signal for rate limiting
                self.signal_history.append(
                    {
                        "signal_id": signal.signal_id,
                        "timestamp": datetime.now(UTC),
                        "symbol": signal.symbol,
                        "strategy": signal.strategy_name,
                    }
                )

                # Store active signal if valid
                if not violations:
                    self.active_signals[signal.signal_id] = signal

                is_valid = len(violations) == 0

                if violations:
                    self.logger.warning(
                        f"Signal {signal.signal_id} validation failed: {violations}"
                    )
                else:
                    self.logger.info(f"Signal {signal.signal_id} passed validation")

                return is_valid, violations

        except Exception as e:
            handle_error(e, module=__name__, function="validate_signal")
            return False, [f"Validation error: {str(e)}"]

    @with_error_handling("ml_risk_management")
    def calculate_position_size(
        self,
        signal: MLTradingSignal,
        current_portfolio_value: float,
        current_price: float,
        method: SizingMode = SizingMode.CONFIDENCE_WEIGHTED,
    ) -> PositionSizeResult:
        """
        Calculate optimal position size for ML signal

        Args:
            signal: ML trading signal
            current_portfolio_value: Current portfolio value
            current_price: Current stock price
            method: Position sizing method

        Returns:
            PositionSizeResult with sizing recommendation
        """
        try:
            constraints: list[str] = []
            warnings: list[str] = []

            # Base position size (1% of portfolio as starting point)
            base_allocation = current_portfolio_value * 0.01
            base_size = int(base_allocation / current_price) if current_price > 0 else 0

            # Confidence factor
            confidence_factor = signal.confidence
            if method == SizingMode.CONFIDENCE_WEIGHTED:
                # Linear scaling: 0.5 confidence = 0.5x size, 1.0 confidence = 1.0x size
                confidence_factor = max(0.1, signal.confidence)  # Minimum 10% size

            confidence_adjusted_size = int(base_size * confidence_factor)

            # Model performance factor
            model_performance = self.model_performance_cache.get(
                signal.model_version, 0.8
            )  # Default to good
            performance_factor = model_performance

            # Risk factor based on signal confidence (inverse relationship)
            # Lower confidence = smaller position (more conservative)
            risk_factor = max(
                0.1, signal.confidence
            )  # Use confidence directly as risk factor

            # Calculate risk-adjusted size
            risk_adjusted_size = int(
                confidence_adjusted_size * performance_factor * risk_factor
            )

            # Apply hard constraints
            final_size = risk_adjusted_size

            # Position size limit
            if final_size > self.risk_limits.max_position_size:
                constraints.append(
                    f"Reduced from {final_size:,} to {self.risk_limits.max_position_size:,} (position size limit)"
                )
                final_size = self.risk_limits.max_position_size

            # Portfolio exposure limit
            position_value = final_size * current_price
            max_position_value = (
                current_portfolio_value * self.risk_limits.max_single_stock_weight
            )
            if position_value > max_position_value:
                max_size = int(max_position_value / current_price)
                constraints.append(
                    f"Reduced from {final_size:,} to {max_size:,} (single stock weight limit)"
                )
                final_size = max_size

            # Check if position is too small to be meaningful
            if final_size < 10:
                warnings.append(
                    "Position size very small - consider increasing base allocation or confidence threshold"
                )

            # Check for high concentration risk
            if (
                position_value > current_portfolio_value * 0.05
            ):  # More than 5% of portfolio
                warnings.append(
                    "High concentration risk - position represents significant portfolio allocation"
                )

            result = PositionSizeResult(
                final_size=float(final_size),
                confidence_factor=confidence_factor,
                risk_adjusted=True,
                max_size=float(self.risk_limits.max_position_size),
                sizing_method=method,
            )

            self.logger.info(
                f"Position sizing for {signal.symbol}: {final_size:,} shares (confidence: {signal.confidence:.2f})"
            )

            return result

        except Exception as e:
            handle_error(e, module=__name__, function="calculate_position_size")
            # Return conservative fallback
            return PositionSizeResult(
                final_size=0.0,
                confidence_factor=0.0,
                risk_adjusted=True,
                max_size=0.0,
                sizing_method=method,
            )

    @with_error_handling("ml_risk_management")
    def assess_signal_risk(  # noqa: C901
        self,
        signal: MLTradingSignal,
        current_portfolio_positions: dict[str, int] | None = None,
        market_volatility: float = 0.2,
    ) -> RiskAssessment:
        """
        Comprehensive risk assessment for ML signal

        Args:
            signal: ML trading signal
            current_portfolio_positions: Current positions {symbol: quantity}
            market_volatility: Current market volatility (VIX-like measure)

        Returns:
            RiskAssessment with detailed risk analysis
        """
        try:
            if current_portfolio_positions is None:
                current_portfolio_positions = {}

            # Individual risk factors calculation
            confidence_risk = (1.0 - signal.confidence) * 100

            model_performance = self.model_performance_cache.get(
                signal.model_version, 0.8
            )
            model_performance_risk = (1.0 - model_performance) * 100

            # Portfolio Concentration Risk
            current_position = current_portfolio_positions.get(signal.symbol, 0)
            total_positions = sum(
                abs(pos) for pos in current_portfolio_positions.values()
            )
            concentration_risk = 0.0
            if total_positions > 0:
                current_weight = abs(current_position) / total_positions
                concentration_risk = min(100.0, current_weight * 500)

            # Market risk from volatility
            market_risk = min(100.0, market_volatility * 100)

            # Correlation risk calculation
            correlation_risk = self._calculate_correlation_risk(
                signal.symbol, current_portfolio_positions
            )

            # Overall risk score (0.0 to 1.0 scale as per TypedDict)
            overall_risk_score = (
                confidence_risk * 0.25
                + model_performance_risk * 0.25
                + concentration_risk * 0.20
                + market_risk * 0.15
                + correlation_risk * 0.15
            ) / 100.0  # Convert to 0.0-1.0 scale

            # Determine risk level based on score
            if overall_risk_score < 0.25:
                risk_level = RiskLevel.LOW
            elif overall_risk_score < 0.50:
                risk_level = RiskLevel.MEDIUM
            elif overall_risk_score < 0.75:
                risk_level = RiskLevel.HIGH
            else:
                risk_level = RiskLevel.CRITICAL

            # Determine recommendation (using TypedDict allowed values)
            if risk_level == RiskLevel.LOW:
                recommended_action = "trade"
            elif risk_level == RiskLevel.MEDIUM:
                recommended_action = "trade"
            elif risk_level == RiskLevel.HIGH:
                recommended_action = "reduce"
            else:  # CRITICAL
                recommended_action = "abort"

            # Create risk factors list
            risk_factors: list[str] = []
            if confidence_risk > 60:
                risk_factors.append("Low signal confidence")
            if model_performance_risk > 60:
                risk_factors.append("Poor model performance")
            if concentration_risk > 60:
                risk_factors.append("High portfolio concentration")
            if market_risk > 70:
                risk_factors.append("High market volatility")

            # Return TypedDict-compatible assessment
            assessment: RiskAssessment = {
                "risk_score": overall_risk_score,
                "overall_risk_level": risk_level,
                "recommended_action": recommended_action,
                "risk_factors": risk_factors,
            }

            self.logger.info(
                f"Risk assessment for {signal.symbol}: {risk_level.value} ({overall_risk_score:.3f}) - {recommended_action}"
            )

            return assessment

        except Exception as e:
            handle_error(e, module=__name__, function="assess_signal_risk")
            # Return conservative assessment
            return {
                "risk_score": 1.0,
                "overall_risk_level": RiskLevel.CRITICAL,
                "recommended_action": "abort",
                "risk_factors": ["Risk assessment failed - manual review required"],
            }

    def _calculate_correlation_risk(
        self, symbol: str, current_positions: dict[str, int]
    ) -> float:
        """Calculate risk from correlated positions"""
        try:
            correlation_risk = 0

            for existing_symbol, quantity in current_positions.items():
                if existing_symbol == symbol or quantity == 0:
                    continue

                # Get correlation (would be loaded from market data in production)
                correlation_key = (
                    min(symbol, existing_symbol),
                    max(symbol, existing_symbol),
                )
                correlation = self.position_correlations.get(
                    correlation_key, 0.3
                )  # Default medium correlation

                # Risk increases with high correlation and large existing position
                position_weight = abs(quantity) / 1000  # Normalize position size
                correlation_contribution = (
                    abs(correlation) * position_weight * 20
                )  # Scale factor
                correlation_risk += correlation_contribution

            return min(100, correlation_risk)

        except Exception as e:
            self.logger.error(f"Error calculating correlation risk: {e}")
            return 50  # Default medium risk

    def update_model_performance(self, model_version: str, performance_score: float):
        """Update cached model performance score"""
        if not (0.0 <= performance_score <= 1.0):
            raise ValueError("Performance score must be 0-1")

        self.model_performance_cache[model_version] = performance_score
        self.logger.info(
            f"Updated performance for {model_version}: {performance_score:.3f}"
        )

    def update_daily_pnl(self, pnl_change: float, date: str | None = None):
        """Update daily P&L tracking"""
        if date is None:
            date = datetime.now().strftime("%Y-%m-%d")

        self.daily_pnl_tracker[date] += pnl_change

        # Check for breach of daily loss limit
        if self.daily_pnl_tracker[date] < -self.risk_limits.max_daily_loss:
            breach = {
                "type": "DAILY_LOSS_LIMIT",
                "date": date,
                "loss": abs(self.daily_pnl_tracker[date]),
                "limit": self.risk_limits.max_daily_loss,
                "timestamp": datetime.now(UTC),
            }
            self.risk_breaches.append(breach)
            self.logger.error(
                f"Daily loss limit breached: ${abs(self.daily_pnl_tracker[date]):,.2f}"
            )

    def signal_completed(self, signal_id: str):
        """Mark signal as completed/inactive"""
        with self._lock:
            if signal_id in self.active_signals:
                del self.active_signals[signal_id]
                self.logger.info(f"Signal {signal_id} marked as completed")

    def get_risk_dashboard(self) -> dict[str, Any]:
        """Get real-time risk dashboard data"""
        try:
            today = datetime.now().strftime("%Y-%m-%d")
            recent_breaches = [
                b
                for b in self.risk_breaches
                if b["timestamp"] > datetime.now(UTC) - timedelta(hours=24)
            ]

            return {
                "active_signals": len(self.active_signals),
                "signals_today": len(
                    [
                        s
                        for s in self.signal_history
                        if s["timestamp"].date() == datetime.now().date()
                    ]
                ),
                "daily_pnl": self.daily_pnl_tracker[today],
                "daily_loss_limit": self.risk_limits.max_daily_loss,
                "risk_limit_utilization": {
                    "position_count": f"{len(self.active_signals)}/{self.risk_limits.max_concurrent_signals}",
                    "daily_loss": f"${abs(min(0, self.daily_pnl_tracker[today])):,.2f}/${self.risk_limits.max_daily_loss:,.2f}",
                },
                "recent_breaches": len(recent_breaches),
                "model_performance": dict(self.model_performance_cache),
                "risk_status": "HEALTHY"
                if len(recent_breaches) == 0
                else "WARNING"
                if len(recent_breaches) < 3
                else "CRITICAL",
            }

        except Exception as e:
            handle_error(e, module=__name__, function="get_risk_dashboard")
            return {"error": str(e)}

    def save_risk_assessment(self, assessment: RiskAssessment):
        """Save risk assessment to Parquet for analysis"""
        try:
            log_data = {
                "timestamp": datetime.now(UTC).isoformat(),
                "overall_risk_level": assessment["overall_risk_level"].value,
                "risk_score": assessment["risk_score"],
                "recommended_action": assessment["recommended_action"],
                "risk_factors": str(assessment.get("risk_factors", [])),
            }

            # Convert to DataFrame and save
            log_df = pd.DataFrame([log_data])
            log_df["timestamp"] = pd.to_datetime(log_df["timestamp"])
            log_df = log_df.set_index("timestamp")

            # Save with date for organization
            date_str = datetime.now().strftime("%Y-%m-%d")
            self.parquet_repo.save_data(
                log_df,
                symbol="ML_RISK_ASSESSMENT",
                timeframe="risk_logs",
                date_str=date_str,
            )

        except Exception as e:
            self.logger.error(f"Failed to save risk assessment: {e}")


# Convenience function for integration
def create_ml_risk_manager() -> MLRiskManager:
    """Create ML risk management service"""
    return MLRiskManager()


if __name__ == "__main__":
    # Demo the ML risk management service
    print("🛡️ ML Risk Management Service Demo")
    print("=" * 40)

    risk_manager = MLRiskManager()
    print("✅ ML Risk Manager initialized")
    print(
        f"📊 Risk Limits: Max position {risk_manager.risk_limits.max_position_size:,}, Min confidence {risk_manager.risk_limits.min_confidence_threshold:.2f}"
    )
    print("🔒 Ready to validate signals and manage ML trading risk")
    print("📈 Provides confidence-based position sizing and dynamic risk assessment")
