"""Financial metrics utilities: Sharpe ratio, drawdowns, and equity curve.

These functions are framework-agnostic and operate on simple sequences
of returns or P&L to support both ML backtests and live monitoring.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

import numpy as np


def _to_array(x: Iterable[float] | np.ndarray) -> np.ndarray:
    arr = np.asarray(list(x), dtype=float)
    # Remove NaNs and infs
    return arr[np.isfinite(arr)]


def compute_equity_curve(
    pnl_or_returns: Iterable[float] | np.ndarray,
    *,
    as_returns: bool = False,
    starting_equity: float = 1.0,
) -> np.ndarray:
    """Compute equity curve from a series of PnL or returns.

    Args:
        pnl_or_returns: Sequence of per-period PnL (absolute) or returns (relative).
        as_returns: When True, interpret values as returns and compound multiplicatively.
                    When False, interpret values as PnL and do cumulative sum.
        starting_equity: Initial equity to start the curve.

    Returns:
        np.ndarray of equity values per period.
    """
    arr = _to_array(pnl_or_returns)
    if arr.size == 0:
        return np.array([float(starting_equity)])

    if as_returns:
        # Compound: E_t = E_{t-1} * (1 + r_t)
        returns = arr
        equity = [starting_equity]
        eq = starting_equity
        for r in returns:
            eq *= 1.0 + r
            equity.append(eq)
        return np.asarray(equity[1:])
    else:
        # Additive PnL: E_t = E_{t-1} + pnl_t
        cumsum = np.cumsum(arr)
        return starting_equity + cumsum


def compute_drawdown_series(equity_curve: Sequence[float] | np.ndarray) -> np.ndarray:
    """Compute drawdown series from an equity curve.

    Drawdown is expressed as a negative fraction of the running peak.
    Example: peak=120, equity=100 -> drawdown = (100-120)/120 = -0.1666.
    """
    eq = _to_array(equity_curve)
    if eq.size == 0:
        return np.array([])
    peaks = np.maximum.accumulate(eq)
    # Avoid division by zero; where peak is 0, set drawdown to 0
    with np.errstate(divide="ignore", invalid="ignore"):
        dd = (eq - peaks) / np.where(peaks == 0.0, np.nan, peaks)
    dd[~np.isfinite(dd)] = 0.0
    return dd


def compute_max_drawdown(equity_curve: Sequence[float] | np.ndarray) -> float:
    """Compute maximum drawdown as a negative fraction (e.g., -0.25 == -25%)."""
    dd = compute_drawdown_series(equity_curve)
    return float(dd.min()) if dd.size else 0.0


def compute_sharpe_ratio(
    returns: Iterable[float] | np.ndarray,
    *,
    risk_free_rate: float = 0.0,
    periods_per_year: int = 252,
) -> float:
    """Compute annualized Sharpe ratio from period returns.

    Args:
        returns: Sequence of period returns (not PnL). Values like 0.01 == 1%.
        risk_free_rate: Period risk-free rate to subtract from returns.
        periods_per_year: For annualization (252 daily, 12 monthly, etc.).

    Returns:
        Annualized Sharpe ratio. Returns 0.0 when insufficient data or 0 stdev.
    """
    r = _to_array(returns)
    if r.size < 2:
        return 0.0
    excess = r - risk_free_rate
    mu = excess.mean()
    sigma = excess.std(ddof=1)
    if not np.isfinite(sigma) or sigma == 0.0:
        return 0.0
    return float((mu / sigma) * math.sqrt(max(1, periods_per_year)))


@dataclass(frozen=True)
class FinancialSummary:
    sharpe: float
    max_drawdown: float


def summarize_financials(
    returns: Iterable[float] | np.ndarray,
    *,
    periods_per_year: int = 252,
    risk_free_rate: float = 0.0,
    starting_equity: float = 1.0,
) -> FinancialSummary:
    """Convenience to compute Sharpe and MaxDD from returns."""
    r = _to_array(returns)
    sharpe = compute_sharpe_ratio(
        r, risk_free_rate=risk_free_rate, periods_per_year=periods_per_year
    )
    equity = compute_equity_curve(r, as_returns=True, starting_equity=starting_equity)
    maxdd = compute_max_drawdown(equity)
    return FinancialSummary(sharpe=sharpe, max_drawdown=maxdd)
