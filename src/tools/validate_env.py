"""Validate required environment / config keys.

Reads `reports/env_keys.json` for required key list and reports status.
Safe to run without full IB stack. Produces structured JSON and supports
`--describe` for metadata schema.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from ._cli_helpers import env_dep, load_config_safely, print_json, redact


def _load_required_keys() -> list[str]:
    report = Path("reports/env_keys.json")
    if not report.exists():
        return []
    try:
        data = json.loads(report.read_text())
        return list(data.get("keys", []))
    except Exception:  # pragma: no cover
        return []


def _collect_values(keys: list[str]) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for k in keys:
        values[k] = os.getenv(k)
    return values


def _validate(keys: list[str], values: dict[str, Any]) -> dict[str, Any]:
    missing = [k for k in keys if not values.get(k)]
    cfg = load_config_safely()
    # Attempt to surface a few IB connection resolved defaults
    resolved = {
        "IB_HOST": getattr(cfg.ib_connection, "host", None),
        "IB_GATEWAY_PAPER_PORT": getattr(cfg.ib_connection, "gateway_paper_port", None),
        "IB_GATEWAY_LIVE_PORT": getattr(cfg.ib_connection, "gateway_live_port", None),
        "IB_PAPER_PORT": getattr(cfg.ib_connection, "paper_port", None),
        "IB_LIVE_PORT": getattr(cfg.ib_connection, "live_port", None),
        "IB_CLIENT_ID": getattr(cfg.ib_connection, "client_id", None),
    }
    status = "ok" if not missing else "incomplete"
    return {
        "status": status,
        "missing": missing,
        "defined": [k for k, v in values.items() if v],
        "resolved_values": {k: redact(k, v) for k, v in resolved.items()},
        "total_keys": len(keys),
    }


def describe() -> dict[str, Any]:
    keys = _load_required_keys()
    return {
        "name": "validate_env",
        "description": "Validate presence of required environment/config keys.",
        "inputs": {
            "--describe": {"type": "flag", "required": False},
        },
        "outputs": {"stdout": "JSON validation report", "files": []},
        "dependencies": [
            env_dep("IB_HOST"),
            env_dep("IB_GATEWAY_PAPER_PORT"),
            env_dep("IB_GATEWAY_LIVE_PORT"),
        ],
        "examples": [
            "python -m src.tools.validate_env",
            "python -m src.tools.validate_env --describe",
        ],
        "keys_count": len(keys),
        "version": "1.0.0",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Environment key validator")
    parser.add_argument(
        "--describe", action="store_true", help="Show tool description JSON and exit"
    )
    args = parser.parse_args(argv)
    if args.describe:
        return print_json(describe())
    keys = _load_required_keys()
    values = _collect_values(keys)
    report = _validate(keys, values)
    return print_json(report)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
