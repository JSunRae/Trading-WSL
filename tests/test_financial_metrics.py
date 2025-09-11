import math

import numpy as np

from src.analytics.financial_metrics import (
    compute_equity_curve,
    compute_max_drawdown,
    compute_sharpe_ratio,
)


def test_sharpe_ratio_basic_alternating() -> None:
    # Alternating +1% and -1% daily returns -> mean ~ 0, Sharpe ~ 0
    returns = [0.01, -0.01] * 50
    sharpe = compute_sharpe_ratio(returns, periods_per_year=252)
    assert abs(sharpe) < 1e-6


def test_equity_and_drawdown_from_pnl() -> None:
    # PnL series starting from 100 equity
    pnl = [10, -20, 5]
    equity = compute_equity_curve(pnl, as_returns=False, starting_equity=100)
    # Equity should be [110, 90, 95]
    assert np.allclose(equity, np.array([110.0, 90.0, 95.0]))
    # Max drawdown: from 110 peak down to 90 -> -20/110 ≈ -0.1818
    max_dd = compute_max_drawdown(equity)
    assert math.isclose(max_dd, -20.0 / 110.0, rel_tol=1e-6)


def test_max_drawdown_from_returns_equity_curve() -> None:
    # Returns that dip then recover beyond peak
    returns = [0.10, -0.25, 0.05, 0.20]  # Start at 1.0
    equity = compute_equity_curve(returns, as_returns=True, starting_equity=1.0)
    # Equity ~ [1.1, 0.825, 0.86625, 1.0395]
    assert len(equity) == 4
    # Max drawdown happens from 1.1 down to 0.825 => -0.25
    max_dd = compute_max_drawdown(equity)
    assert math.isclose(max_dd, -0.25, rel_tol=1e-9)
