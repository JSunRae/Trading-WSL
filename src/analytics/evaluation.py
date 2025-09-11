"""Evaluation helpers to compute trading metrics for manifests and logging."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

import numpy as np

from src.analytics.financial_metrics import (
    compute_equity_curve,
    compute_max_drawdown,
    compute_sharpe_ratio,
)


@dataclass(frozen=True)
class TradingMetrics:
    sharpe_sim: float
    max_drawdown_sim: float
    f1_macro: float | None = None
    profit_factor: float | None = None
    win_rate: float | None = None
    var_95: float | None = None


def evaluate_trading_metrics(
    *,
    returns: list[float] | np.ndarray | None = None,
    pnl: list[float] | np.ndarray | None = None,
) -> TradingMetrics:
    """Compute Sharpe and Max Drawdown from returns or PnL.

    Args:
        returns: Period returns (preferred for Sharpe). If None, will derive from PnL-based equity.
        pnl: Per-period PnL. Used for equity and drawdown; also derives returns if returns is None.
    """
    r: np.ndarray
    if returns is not None:
        r = np.asarray(list(returns), dtype=float)
    elif pnl is not None:
        eq = compute_equity_curve(pnl, as_returns=False, starting_equity=1.0)
        if len(eq) >= 2:
            r = np.asarray(
                [eq[i] / eq[i - 1] - 1.0 for i in range(1, len(eq))], dtype=float
            )
        else:
            r = np.asarray([], dtype=float)
    else:
        r = np.asarray([], dtype=float)

    # Sharpe
    sharpe = compute_sharpe_ratio(r, periods_per_year=252)

    # Max drawdown via equity curve (prefer PnL equity if available)
    if pnl is not None:
        eq_curve = compute_equity_curve(pnl, as_returns=False, starting_equity=1.0)
    else:
        eq_curve = compute_equity_curve(r, as_returns=True, starting_equity=1.0)
    maxdd = float(compute_max_drawdown(eq_curve))

    # Optional extras
    wins = [float(x) for x in (pnl or []) if x is not None and x > 0]
    losses = [float(x) for x in (pnl or []) if x is not None and x < 0]
    profit_factor = (
        (sum(wins) / abs(sum(losses))) if losses else (float("inf") if wins else 0.0)
    )
    win_rate = (len(wins) / len(wins + losses)) if (wins or losses) else 0.0
    var_95 = float(np.percentile(pnl, 5)) if pnl is not None and len(pnl) > 0 else 0.0

    return TradingMetrics(
        sharpe_sim=float(sharpe),
        max_drawdown_sim=maxdd,
        f1_macro=None,
        profit_factor=profit_factor,
        win_rate=win_rate,
        var_95=var_95,
    )


def metrics_to_tf1_manifest(
    metrics: TradingMetrics, *, f1: float | None = None
) -> dict[str, Any]:
    """Render metrics using TF_1 manifest keys (sharpe, max_drawdown, f1).

    This matches examples/tf1_export_manifest.sample.json and the current
    export validator's expectations.
    """
    return {
        "sharpe": metrics.sharpe_sim,
        "max_drawdown": metrics.max_drawdown_sim,
        "f1": float(f1) if f1 is not None else 0.0,
        # Optional extras (ignored by validator; allowed via additionalProperties)
        "profit_factor": metrics.profit_factor,
        "win_rate": metrics.win_rate,
        "var_95": metrics.var_95,
    }


def metrics_to_trading_contract(
    metrics: TradingMetrics, *, f1_macro: float | None = None
) -> dict[str, Any]:
    """Render metrics using Trading contract keys (sharpe_sim, max_drawdown_sim, f1_macro).

    This aligns with contracts/schemas/manifest.schema.json.
    """
    return {
        "sharpe_sim": metrics.sharpe_sim,
        "max_drawdown_sim": metrics.max_drawdown_sim,
        "f1_macro": float(f1_macro) if f1_macro is not None else 0.0,
        # Optional extras (schema allows additionalProperties)
        "profit_factor": metrics.profit_factor,
        "win_rate": metrics.win_rate,
        "var_95": metrics.var_95,
    }


def metrics_to_manifest(
    metrics: TradingMetrics,
    *,
    f1_value: float | None = None,
    style: Literal["tf1", "trading"] = "tf1",
) -> dict[str, Any]:
    """Convenience wrapper to render either TF_1 or Trading-style metrics dict.

    Args:
        metrics: Computed metrics.
        f1_value: F1 (macro) to include; key name depends on style.
        style: "tf1" -> keys: sharpe, max_drawdown, f1; "trading" -> sharpe_sim, max_drawdown_sim, f1_macro.
    """
    if style == "trading":
        return metrics_to_trading_contract(metrics, f1_macro=f1_value)
    return metrics_to_tf1_manifest(metrics, f1=f1_value)
