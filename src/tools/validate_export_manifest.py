"""Validate a TF_1 export manifest against Trading rules.

Reads a manifest JSON file, validates schema_version, production alias,
and promotion thresholds using promotion.rule.json, then prints a JSON
result to stdout and returns a non-zero exit code on failure.
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.services.ml_contracts.export_manifest_validator import (
    validate_export_manifest,
)
from src.tools._cli_helpers import emit_describe_early


def tool_describe() -> dict[str, Any]:
    return {
        "name": "validate_export_manifest",
        "description": "Validate TF_1 export manifest against Trading promotion rules and schema.",
        "inputs": {
            "--manifest": {"type": "path", "required": True},
            "--model-dir": {
                "type": "path",
                "required": False,
                "description": "Directory containing production.alias for non-dry emissions",
            },
            "--rule": {
                "type": "path",
                "required": False,
                "description": "Override path to promotion.rule.json",
            },
        },
        "outputs": {"stdout": "JSON validation result"},
        "dependencies": [
            "optional:jsonschema",
            "config:PROMOTION_RULE_JSON (repo root promotion.rule.json by default)",
        ],
        "examples": [
            "python -m src.tools.validate_export_manifest --manifest tf1_export_manifest.json",
        ],
    }


def describe() -> dict[str, Any]:  # alias
    return tool_describe()


if emit_describe_early(tool_describe):  # pragma: no cover
    raise SystemExit(0)


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--manifest", required=True, help="Path to export manifest JSON")
    p.add_argument("--rule", help="Path to promotion.rule.json")
    p.add_argument(
        "--model-dir",
        help="Model directory expected to contain a production.alias file",
    )
    return p.parse_args()


def main() -> int:
    args = _parse_args()
    run_id = datetime.now(UTC).strftime("%Y%m%d-%H%M%S-%f")
    manifest_path = Path(args.manifest)
    if not manifest_path.exists():
        print(
            json.dumps(
                {"ok": False, "errors": [f"manifest not found: {manifest_path}"]}
            )
        )
        return 1
    try:
        manifest = json.loads(manifest_path.read_text())
    except Exception as e:
        print(json.dumps({"ok": False, "errors": [f"invalid json: {e}"]}))
        return 1

    # The validator expects a repo_root containing promotion.rule.json.
    # If --rule is provided, use its parent directory; otherwise default to repo root.
    repo_root = (
        Path(args.rule).parent if args.rule else Path(__file__).resolve().parents[2]
    )
    model_dir = Path(args.model_dir) if args.model_dir else None
    t0 = datetime.now(UTC).timestamp()
    result = validate_export_manifest(
        manifest, repo_root=repo_root, require_alias_file_in=model_dir
    )
    dur_ms = int((datetime.now(UTC).timestamp() - t0) * 1000)
    # Enrich with observability
    model_id = None
    try:
        model_id = manifest.get("model", {}).get("id")
    except Exception:
        model_id = None
    # Attempt to infer symbols and data window if present (best-effort)
    # Optional best-effort observability fields (safe defaults to None)
    symbols: list[str] | None = None
    data_window: dict[str, Any] | None = None
    symbol: str | None = None

    enriched = {
        **result,
        "model_id": model_id,
        "stage_latency_ms": {"validation": dur_ms},
        "run_id": run_id,
        "symbols": symbols,
        "symbol": symbol,
        "data_window": data_window,
    }
    print(json.dumps(enriched, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
