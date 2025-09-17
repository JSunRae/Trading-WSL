"""Automatic Warrior historical L2 backfill CLI.

Builds a task list from the Warrior list (unique (symbol, trading_day)) and
invokes the programmatic orchestrator. Designed for cron / CI usage where
idempotence and a single SUMMARY line are sufficient for guardrails.
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import UTC, date, datetime
from typing import Any

from src.services.market_data.artifact_check import compute_needs
from src.services.market_data.warrior_backfill_orchestrator import (
    find_warrior_tasks,
    run_warrior_backfill,
)
from src.tools._cli_helpers import emit_describe_early


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
            "--fetch-bars": {"type": "flag", "required": False},
            "--force-bars": {"type": "flag", "required": False},
            "--ib-host": {"type": "str", "required": False},
            "--ib-port": {"type": "int", "required": False},
            "--use-tws": {"type": "flag", "required": False},
        },
        "outputs": {"stdout": "progress + single SUMMARY line"},
        "dependencies": [
            "optional:databento",
            "config:DATABENTO_API_KEY",
            "config:L2_BACKFILL_WINDOW_ET",
            "config:SYMBOL_MAPPING_FILE",
            # IB-related (optional)
            "config:IB_HOST",
            "config:IB_GATEWAY_PAPER_PORT",
            "config:IB_PAPER_PORT",
            "config:IB_DOWNLOADS_DIRNAME",
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


def _fetch_ib_bars_for_task(  # noqa: C901
    symbol: str,
    day: date,
    *,
    force_bars: bool = False,
    ib_host: str | None = None,
    ib_port: int | None = None,
    use_tws: bool = False,
) -> None:
    """Download hourly and 1-sec bars for a single (symbol, day) via IB.

    Best-effort: swallows exceptions to not block L2 backfill.
    Uses lazy imports to avoid hard deps during --describe.
    """
    try:
        # Lazy imports
        import asyncio as _asyncio  # type: ignore
        from datetime import datetime as _dt
        from datetime import timedelta as _td

        from src.core.config import get_config as _getcfg  # type: ignore
        from src.infra.ib_conn import (  # type: ignore
            get_ib_connect_plan as _plan,
        )
        from src.infra.ib_conn import (
            try_connect_candidates as _try_connect,
        )
        from src.lib.ib_async_wrapper import IBAsync as _IBAsync  # type: ignore
    except Exception:
        return

    cfg = _getcfg()
    ds = day.strftime("%Y-%m-%d")
    # Check needs first
    before = compute_needs(symbol, ds)
    if not force_bars and not (before.get("hourly") or before.get("seconds")):
        return

    hourly_path = cfg.get_data_file_path(
        "ib_download", symbol=symbol, timeframe="1 hour", date_str=ds
    )
    sec_path = cfg.get_data_file_path(
        "ib_download", symbol=symbol, timeframe="1 sec", date_str=ds
    )

    async def _run() -> None:
        ib = _IBAsync()
        plan = _plan()
        # Overrides
        if ib_host:
            plan["host"] = ib_host
        if ib_port is not None:
            port = int(ib_port)
            plan["candidates"] = [port] + [p for p in plan["candidates"] if p != port]
        if use_tws and 7497 not in plan["candidates"]:
            plan["candidates"].insert(0, 7497)
        host = plan["host"]
        client_id = int(plan["client_id"])
        candidates = [int(p) for p in plan["candidates"]]

        async def _connect_cb(h: str, p: int, c: int) -> bool:
            return await ib.connect(h, p, c, fallback=False)

        ok, _ = await _try_connect(
            _connect_cb, host, candidates, client_id, autostart=True, events=[]
        )
        if not ok:
            await ib.disconnect()
            return
        try:
            contract = ib.create_stock_contract(symbol)
            end_ts = _dt.combine(day + _td(days=1), _dt.min.time()).strftime(
                "%Y%m%d %H:%M:%S"
            )
            if force_bars or before.get("hourly"):
                df_h = await ib.req_historical_data(
                    contract, duration="1 D", bar_size="1 hour", end_datetime=end_ts
                )
                if df_h is not None and not df_h.empty:
                    hourly_path.parent.mkdir(parents=True, exist_ok=True)
                    df_h.to_parquet(hourly_path)
            if force_bars or before.get("seconds"):
                df_s = await ib.req_historical_data(
                    contract, duration="1 D", bar_size="1 sec", end_datetime=end_ts
                )
                if df_s is not None and not df_s.empty:
                    sec_path.parent.mkdir(parents=True, exist_ok=True)
                    df_s.to_parquet(sec_path)
        finally:
            await ib.disconnect()

    try:
        _asyncio.run(_run())
    except Exception:
        # Non-fatal
        return


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--since", type=int, help="Include tasks with date >= today-N")
    p.add_argument("--last", type=int, help="Retain only last N distinct dates")
    p.add_argument("--max-tasks", type=int)
    p.add_argument("--force", action="store_true")
    p.add_argument("--strict", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument(
        "--verbose", action="store_true", help="Emit per-row needs to stderr"
    )
    p.add_argument(
        "--max-workers",
        type=int,
        help="Number of parallel workers (default env L2_MAX_WORKERS or 4)",
    )
    # Merged IB controls
    p.add_argument(
        "--fetch-bars",
        action="store_true",
        help="Download IB hourly and 1-sec bars for all tasks before L2 backfill",
    )
    p.add_argument(
        "--force-bars",
        action="store_true",
        help="Force re-download of hourly and 1-sec bars (ignore existing)",
    )
    p.add_argument(
        "--ib-host", type=str, help="Override IB host (default from config/env)"
    )
    p.add_argument(
        "--ib-port", type=int, help="Override IB port (default tries: 4003, 4002, 7497)"
    )
    p.add_argument(
        "--use-tws",
        action="store_true",
        help="Prefer TWS (7497) over Gateway (4002); WSL default proxy is 4003",
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


def main() -> int:  # noqa: C901 - complexity accepted (out of scope)
    args = _parse_args()
    run_id = datetime.now(UTC).strftime("%Y%m%d-%H%M%S-%f")
    t0 = datetime.now(UTC).timestamp()
    tasks = find_warrior_tasks(since_days=args.since, last=args.last)
    discovery_ms = int((datetime.now(UTC).timestamp() - t0) * 1000)
    if args.max_tasks:
        tasks = tasks[: args.max_tasks]
    if args.dry_run:
        # Pull requested window for observability
        try:
            from src.core.config import get_config

            win_start, win_end = get_config().get_l2_backfill_window()
        except Exception:
            win_start, win_end = None, None
        symbols = {sym for sym, _ in tasks}
        # Date summaries (avoid dumping large lists)
        dates = [d for _, d in tasks]
        date_min = min(dates).strftime("%Y-%m-%d") if dates else None
        date_max = max(dates).strftime("%Y-%m-%d") if dates else None
        # Aggregate needs over unique tasks
        agg = {"need_hourly": 0, "need_seconds": 0, "need_l2": 0}
        completed = 0
        for sym, d in tasks:
            ds = d.strftime("%Y-%m-%d")
            needs = compute_needs(sym, ds)
            if needs.get("hourly"):
                agg["need_hourly"] += 1
            if needs.get("seconds"):
                agg["need_seconds"] += 1
            if needs.get("l2"):
                agg["need_l2"] += 1
            if not (needs.get("hourly") or needs.get("seconds") or needs.get("l2")):
                completed += 1
        preview = {
            "task_count": len(tasks),
            "since_days": args.since,
            "last": args.last,
            "max_tasks": args.max_tasks,
            "run_id": run_id,
            "requested_window_et": {"start": win_start, "end": win_end},
            "stage_latency_ms": {"discovery": discovery_ms},
            # Summary only: do not list all symbols
            "symbol_count": len(symbols),
            "date_range": {"min": date_min, "max": date_max},
            "completed_tasks_count": completed,
            "needs_summary": agg,
        }
        print(json.dumps(preview, indent=2))
        # Optional verbose per-row output to stderr
        if args.verbose:
            import sys as _sys

            for sym, d in tasks[:1000]:  # cap to keep output manageable
                ds = d.strftime("%Y-%m-%d")
                needs = compute_needs(sym, ds)
                _sys.stderr.write(
                    f"{ds},{sym} need hourly={bool(needs.get('hourly'))} "
                    f"seconds={bool(needs.get('seconds'))} l2={bool(needs.get('l2'))}\n"
                )
        return 0
    # Optionally fetch IB bars (hourly + 1-sec) for each task prior to L2
    if args.fetch_bars and tasks:
        for sym, d in tasks:
            try:
                _fetch_ib_bars_for_task(
                    sym,
                    d,
                    force_bars=bool(args.force_bars),
                    ib_host=args.ib_host,
                    ib_port=args.ib_port,
                    use_tws=bool(args.use_tws),
                )
            except Exception:
                pass
    # Determine workers then run L2 backfill
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
