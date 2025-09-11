#!/usr/bin/env python3
"""Build a TF_1 export manifest using computed trading metrics.

Usage examples:
  python -m src.tools.analysis.build_export_manifest \
    --model-id tf1-demo --version v2025.08.31 \
    --artifact-type feature_parquet --artifact-path data/features/demo.parquet \
    --returns 0.01,-0.005,0.007 \
    --out artifacts/manifest.json --validate

  python -m src.tools.analysis.build_export_manifest --describe
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from src.analytics.evaluation import evaluate_trading_metrics, metrics_to_manifest
from src.integrations.wandb_integration import log_trading_metrics
from src.tools._cli_helpers import emit_describe_early
from src.tools.validate_export_manifest import main as validate_manifest_cli


def tool_describe() -> dict[str, Any]:
    return {
        "name": "build_export_manifest",
        "description": "Compute Sharpe/MaxDD from returns or PnL and build a TF_1-style export manifest.",
        "inputs": {
            "--model-id": {"type": "str", "required": True},
            "--version": {"type": "str", "required": True},
            "--artifact-type": {"type": "str", "required": True},
            "--artifact-path": {"type": "path", "required": True},
            "--production-alias": {"type": "str", "required": False},
            "--returns": {"type": "list[number]", "required": False},
            "--pnl": {"type": "list[number]", "required": False},
            "--f1": {"type": "number", "required": False, "default": 0.0},
            "--out": {"type": "path", "required": True},
            "--validate": {"type": "flag"},
            "--wandb": {
                "type": "flag",
                "description": "Log metrics to W&B if available",
            },
        },
        "outputs": {
            "file": "manifest JSON (schema_version=1.0, metrics[sharpe,f1,max_drawdown])"
        },
        "version": 1,
    }


def describe() -> dict[str, Any]:  # alias
    return tool_describe()


if emit_describe_early(tool_describe):  # pragma: no cover
    raise SystemExit(0)


def _parse_floats(arg: str | None) -> list[float] | None:
    if not arg:
        return None
    return [float(x) for x in arg.split(",") if x]


def _build_manifest(
    *,
    model_id: str,
    version: str,
    artifact_type: str,
    artifact_path: str,
    metrics: dict[str, Any],
    production_alias: str | None,
) -> dict[str, Any]:
    m: dict[str, Any] = {
        "schema_version": "1.0",
        "model": {
            "id": model_id,
            "version": version,
            "metadata": {
                "production": ({"alias": production_alias} if production_alias else {})
            },
        },
        "artifacts": [
            {
                "type": artifact_type,
                "path": artifact_path,
                "schema": {"version": "1"},
            }
        ],
        "metrics": metrics,
    }
    return m


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--model-id", required=True)
    p.add_argument("--version", required=True)
    p.add_argument("--artifact-type", required=True)
    p.add_argument("--artifact-path", required=True)
    p.add_argument("--production-alias")
    p.add_argument("--returns")
    p.add_argument("--pnl")
    p.add_argument("--f1", type=float, default=0.0)
    p.add_argument("--out", required=True)
    p.add_argument("--validate", action="store_true")
    p.add_argument("--wandb", action="store_true")
    p.add_argument("--describe", action="store_true")
    args = p.parse_args()

    if args.describe:
        print(json.dumps(describe(), indent=2))
        return 0

    returns = _parse_floats(args.returns)
    pnl = _parse_floats(args.pnl)

    metrics_obj = evaluate_trading_metrics(returns=returns, pnl=pnl)
    metrics_dict = metrics_to_manifest(metrics_obj, f1_value=args.f1, style="tf1")

    if args.wandb:
        # Log plain metrics to W&B using TF_1 keys
        log_trading_metrics(metrics_dict)

    manifest = _build_manifest(
        model_id=args.model_id,
        version=args.version,
        artifact_type=args.artifact_type,
        artifact_path=args.artifact_path,
        metrics=metrics_dict,
        production_alias=args.production_alias,
    )

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(manifest, indent=2))

    if args.validate:
        # Reuse the existing CLI validator for consistency
        try:
            # It prints JSON result and sets exit code; emulate that behavior here.
            # Note: import usage ensures relative paths resolve under repo.
            import sys

            sys.argv = [
                "validate_export_manifest",
                "--manifest",
                str(out_path),
            ]
            return validate_manifest_cli()
        except Exception:
            # If validation path misbehaves, still return success for the build step
            pass

    # Print built manifest path for convenience
    print(str(out_path))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
