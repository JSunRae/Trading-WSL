#!/usr/bin/env python3
"""Quick Start Guide for Trading Project (describe-only stub).

This script exists primarily to provide stable --describe metadata used by
automation and CI tooling. The interactive guidance content was removed to
avoid heavy imports and keep --describe fast and reliable.
"""

from __future__ import annotations

from typing import Any

from src.tools._cli_helpers import emit_describe_early  # type: ignore


def tool_describe() -> dict[str, Any]:
    return {
        "name": "quick_start",
        "description": "Display project structure, IB setup guidance, and usage examples (describe-only stub).",
        "inputs": {},
        "outputs": {"stdout": "Guidance text or schema"},
        "dependencies": [
            "config:IB_HOST",
            "config:IB_PAPER_PORT",
            "config:IB_LIVE_PORT",
        ],
        "examples": [
            "python -m src.tools.quick_start --describe",
        ],
    }


def describe() -> dict[str, Any]:  # backward compatibility
    return tool_describe()


if __name__ == "__main__":  # pragma: no cover
    # Ultra-early guard to print JSON and exit when --describe is present.
    # If not present, exit successfully without side effects.
    if emit_describe_early(tool_describe):
        raise SystemExit(0)
    raise SystemExit(0)
