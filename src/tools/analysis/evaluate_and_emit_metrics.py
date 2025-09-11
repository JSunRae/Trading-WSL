#!/usr/bin/env python3
"""Compute Sharpe and Max Drawdown from sample inputs and emit JSON.

Usage:
  python -m src.tools.analysis.evaluate_and_emit_metrics --returns 0.01,-0.005,0.007
  python -m src.tools.analysis.evaluate_and_emit_metrics --pnl 10,-5,2,3
  python -m src.tools.analysis.evaluate_and_emit_metrics --describe
"""

from __future__ import annotations

import argparse
import json
from typing import Any

from src.analytics.evaluation import (
    evaluate_trading_metrics,
    metrics_to_manifest,
)


def describe() -> dict[str, Any]:
    return {
        "name": "evaluate_and_emit_metrics",
        "description": "Compute Sharpe and Max Drawdown from returns or PnL and emit manifest-ready metrics.",
        "inputs": {
            "returns": "comma-separated list of floats",
            "pnl": "comma-separated list of floats",
        },
        "outputs": {
            "metrics": [
                "sharpe|sharpe_sim",
                "max_drawdown|max_drawdown_sim",
                "f1|f1_macro",
            ]
        },
        "examples": [
            "--returns 0.01,-0.005,0.007",
            "--pnl 10,-5,2,3",
        ],
    }


def parse_list(arg: str | None) -> list[float] | None:
    if not arg:
        return None
    return [float(x) for x in arg.split(",") if x]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--returns", type=str, default=None)
    parser.add_argument("--pnl", type=str, default=None)
    parser.add_argument("--describe", action="store_true")
    parser.add_argument(
        "--style",
        choices=["tf1", "trading"],
        default="tf1",
        help="Output key style: tf1 (sharpe, max_drawdown, f1) or trading (sharpe_sim, max_drawdown_sim, f1_macro)",
    )
    args = parser.parse_args()

    if args.describe:
        print(json.dumps(describe()))
        return

    returns = parse_list(args.returns)
    pnl = parse_list(args.pnl)

    m = evaluate_trading_metrics(returns=returns, pnl=pnl)
    out = metrics_to_manifest(m, f1_value=0.0, style=args.style)
    print(json.dumps(out))


if __name__ == "__main__":
    main()
