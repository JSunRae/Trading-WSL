"""Analytics package: financial metrics and evaluation utilities."""

from .financial_metrics import (
    compute_drawdown_series,
    compute_equity_curve,
    compute_max_drawdown,
    compute_sharpe_ratio,
)

__all__ = [
    "compute_sharpe_ratio",
    "compute_max_drawdown",
    "compute_drawdown_series",
    "compute_equity_curve",
]
