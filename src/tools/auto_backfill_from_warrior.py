"""Automatic Warrior historical L2 backfill CLI.

Builds a task list from the Warrior list (unique (symbol, trading_day)) and
invokes the programmatic orchestrator. Designed for cron / CI usage where
idempotence and a single SUMMARY line are sufficient for guardrails.
"""

from __future__ import annotations

import argparse
import json
import os
from typing import Any

from src.services.market_data.warrior_backfill_orchestrator import (
    find_warrior_tasks,
    run_warrior_backfill,
)
from src.tools._cli_helpers import emit_describe_early  # type: ignore


def tool_describe() -> dict[str, Any]:
    return {
        "name": "auto_backfill_from_warrior",
        "description": "Automatically backfill historical L2 (08:00–11:30 ET) for Warrior list trading days using programmatic orchestrator.",
        "inputs": {
            "--since": {
                "type": "int",
                "required": False,
                "description": "Include tasks with trading_day >= today - N days",
            },
            "--last": {
                "type": "int",
                "required": False,
                "description": "Keep only last N distinct dates after other filters",
            },
            "--max-tasks": {"type": "int", "required": False},
            "--force": {"type": "flag", "required": False},
            "--strict": {"type": "flag", "required": False},
            "--dry-run": {"type": "flag", "required": False},
            "--max-workers": {
                "type": "int",
                "required": False,
                "description": "Override parallel worker count (default env L2_MAX_WORKERS or 4)",
            },
        },
        "outputs": {"stdout": "progress + single SUMMARY line"},
        "dependencies": [
            "optional:databento",
            "config:DATABENTO_API_KEY",
            "config:L2_BACKFILL_WINDOW_ET",
            "config:SYMBOL_MAPPING_FILE",
        ],
        "examples": [
            "python -m src.tools.auto_backfill_from_warrior --since 3",
            "python -m src.tools.auto_backfill_from_warrior --last 5 --dry-run",
        ],
    }


def describe() -> dict[str, Any]:  # alias
    return tool_describe()


if emit_describe_early(tool_describe):  # pragma: no cover
    raise SystemExit(0)


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--since", type=int, help="Include tasks with date >= today-N")
    p.add_argument("--last", type=int, help="Retain only last N distinct dates")
    p.add_argument("--max-tasks", type=int)
    p.add_argument("--force", action="store_true")
    p.add_argument("--strict", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument(
        "--max-workers",
        type=int,
        help="Number of parallel workers (default env L2_MAX_WORKERS or 4)",
    )
    return p.parse_args()


def _emit_summary_line(summary: dict[str, Any]) -> None:
    counts = summary.get("counts", {})
    line = (
        "SUMMARY "
        + " ".join(
            f"{k}={counts.get(k, 0)}"
            for k in sorted(["WRITE", "SKIP", "EMPTY", "ERROR"])
        )
        + f" total={summary.get('total_tasks', 0)} duration={summary.get('duration_sec', 0)}s concurrency={summary.get('concurrency', 1)}"
    )
    print(line)


def main() -> int:
    args = _parse_args()
    tasks = find_warrior_tasks(since_days=args.since, last=args.last)
    if args.max_tasks:
        tasks = tasks[: args.max_tasks]
    if args.dry_run:
        preview = {
            "task_count": len(tasks),
            "first_tasks": [(sym, d.strftime("%Y-%m-%d")) for sym, d in tasks[:10]],
            "since_days": args.since,
            "last": args.last,
            "max_tasks": args.max_tasks,
        }
        print(json.dumps(preview, indent=2))
        return 0
    # Determine workers
    # Accept both new and legacy environment variable names for worker count
    env_default = int(
        os.getenv("L2_MAX_WORKERS") or os.getenv("L2_BACKFILL_CONCURRENCY") or "4"
    )
    max_workers = args.max_workers or env_default
    summary = run_warrior_backfill(
        tasks,
        force=args.force,
        strict=args.strict,
        max_tasks=args.max_tasks,
        max_workers=max_workers,
    )
    _emit_summary_line(summary)
    if args.strict and summary["counts"].get("ERROR", 0) > 0:
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
