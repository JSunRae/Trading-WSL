"""E2E downloader for the first needed Warrior (symbol, trading_day).

Steps performed:
  1) Discover Warrior tasks and pick the first (symbol, day) that needs any of:
     hourly bars, 1-sec bars, or Level 2
  2) Connect to IB (Gateway preferred, then TWS as fallback)
  3) Download hourly and 1-sec bars for that day if missing and save to paths
     resolved by config.get_data_file_path("ib_download", ...)
    4) Backfill Level 2 via DataBento if needed (idempotent).
  5) Emit a single JSON summary to stdout and logs directory.

Usage examples:
  python -m src.tools.e2e_first_needed_download
    IB_PORT=7497 python -m src.tools.e2e_first_needed_download --verbose
  python -m src.tools.e2e_first_needed_download --since 3 --force-l2

This CLI mirrors the e2e test logic but is runnable standalone.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, TypedDict, cast

from src.core.config import get_config, reload_config
from src.infra.ib_conn import get_ib_connect_plan, try_connect_candidates
from src.lib.ib_async_wrapper import IBAsync
from src.services.market_data.artifact_check import (
    compute_needs,
    has_hourly,
    has_l2,
    has_seconds,
)
from src.services.market_data.backfill_api import backfill_l2
from src.services.market_data.warrior_backfill_orchestrator import find_warrior_tasks
from src.tools._cli_helpers import emit_describe_early, env_dep


def tool_describe() -> dict[str, Any]:
    return {
        "name": "e2e_first_needed_download",
        "description": (
            "Find first Warrior (symbol, day) missing hourly/seconds/L2; "
            "download IB hourly+1sec, backfill L2 via DataBento, and log paths/results"
        ),
        "inputs": {
            "--since": {
                "type": "int",
                "required": False,
                "description": "Only consider tasks with date >= today-N",
            },
            "--last": {
                "type": "int",
                "required": False,
                "description": "Keep only last N distinct dates after filters",
            },
            "--force-l2": {"type": "flag", "required": False},
            "--force-bars": {
                "type": "flag",
                "required": False,
                "description": "Force re-download hourly and 1-sec bars",
            },
            "--fallback-first": {
                "type": "flag",
                "required": False,
                "description": "If nothing needs download, pick first Warrior row anyway",
            },
            "--ib-host": {"type": "str", "required": False},
            "--ib-port": {"type": "int", "required": False},
            "--use-tws": {"type": "flag", "required": False},
            "--verbose": {"type": "flag", "required": False},
        },
        "outputs": {"stdout": "one JSON object + human logs in logs/e2e_*"},
        "dependencies": [
            env_dep("IB_HOST"),
            env_dep("IB_GATEWAY_PAPER_PORT"),
            env_dep("IB_PAPER_PORT"),
            env_dep("LEVEL2_DIRNAME"),
            env_dep("IB_DOWNLOADS_DIRNAME"),
            "env:DATABENTO_API_KEY",
        ],
        "examples": [
            "python -m src.tools.e2e_first_needed_download",
            "IB_PORT=7497 python -m src.tools.e2e_first_needed_download --verbose",
        ],
    }


def describe() -> dict[str, Any]:  # alias
    return tool_describe()


if emit_describe_early(tool_describe):  # pragma: no cover
    raise SystemExit(0)


class IBEvent(TypedDict, total=False):
    event: str
    symbol: str
    end_datetime: str
    paths: dict[str, str]
    rows: int
    script: str
    start_cmd: str
    error: str
    host: str
    candidates: list[int]
    port: int


def _ensure_e2e_logger(logs_dir: Path) -> None:
    e2e_log_path = logs_dir / "e2e_download.log"
    root = logging.getLogger()
    for h in root.handlers:
        if isinstance(h, logging.FileHandler) and getattr(h, "baseFilename", "") == str(
            e2e_log_path
        ):
            return
    fh = logging.FileHandler(e2e_log_path)
    fh.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    fh.setFormatter(fmt)
    root.addHandler(fh)
    root.setLevel(logging.INFO)


def _bootstrap_env_for_local_data() -> None:
    """If running in the repo, point config to ./data and reload.

    Sets:
      - ML_BASE_PATH to current working directory
      - WARRIOR_TRADES_FILENAME to data/WarriorTrading_Trades.csv (if exists)
    Then reloads config so subsequent calls see the overrides.
    """
    cwd = Path.cwd()
    warrior_csv_rel = Path("data/WarriorTrading_Trades.csv")
    warrior_csv = cwd / warrior_csv_rel
    changed = False
    if warrior_csv.exists():
        if os.environ.get("ML_BASE_PATH") != str(cwd):
            os.environ["ML_BASE_PATH"] = str(cwd)
            changed = True
        if os.environ.get("WARRIOR_TRADES_FILENAME") != str(warrior_csv_rel):
            os.environ["WARRIOR_TRADES_FILENAME"] = str(warrior_csv_rel)
            changed = True
    if changed:
        reload_config()


def _pick_first_needed(
    since: int | None, last: int | None, *, fallback_first: bool = False
) -> tuple[str, date] | None:
    tasks = find_warrior_tasks(since_days=since, last=last)
    for s, d in tasks:
        needs = compute_needs(s, d.strftime("%Y-%m-%d"))
        if needs.get("hourly") or needs.get("seconds") or needs.get("l2"):
            return s, d
    if fallback_first and tasks:
        return tasks[0]
    return None


# removed per centralization; autostart is handled inside try_connect_candidates


async def _fetch_ib_bars_if_needed(
    symbol: str,
    day: date,
    hourly_path: Path,
    sec_path: Path,
    before: dict[str, Any] | Any,
    ib_events: list[IBEvent],
    *,
    force_bars: bool = False,
    ib_host: str | None = None,
    ib_port: int | None = None,
    use_tws: bool = False,
) -> None:
    """Fetch hourly and 1-sec bars for the given day if needed using IBAsync."""
    ib = IBAsync()
    plan = get_ib_connect_plan()
    # CLI overrides: --ib-host / --ib-port / --use-tws
    if ib_host:
        plan["host"] = ib_host
    if ib_port is not None:
        port = int(ib_port)
        plan["candidates"] = [port] + [p for p in plan["candidates"] if p != port]
    if use_tws and 7497 not in plan["candidates"]:
        plan["candidates"].insert(0, 7497)
    host = plan["host"]
    client_id = int(plan["client_id"])  # ensure int
    candidates = [int(p) for p in plan["candidates"]]

    # Wrap connect to disable internal fallback because we provide our own candidates
    async def _connect_cb(h: str, p: int, c: int) -> bool:
        return await ib.connect(h, p, c, fallback=False)

    ok, _used_port = await try_connect_candidates(
        _connect_cb,
        host,
        candidates,
        client_id,
        autostart=True,
        events=cast(list[dict[str, Any]], ib_events),
    )
    if not ok:
        return

    try:
        contract = ib.create_stock_contract(symbol)
        end_ts = datetime.combine(
            day + timedelta(days=1), datetime.min.time()
        ).strftime("%Y%m%d %H:%M:%S")
        ib_events.append(
            {
                "event": "historical_request",
                "symbol": symbol,
                "end_datetime": end_ts,
                "paths": {"hourly": str(hourly_path), "seconds": str(sec_path)},
            }
        )
        if force_bars or before.get("hourly"):
            df_h = await ib.req_historical_data(
                contract, duration="1 D", bar_size="1 hour", end_datetime=end_ts
            )
            ib_events.append(
                {
                    "event": "hourly_result",
                    "rows": 0 if df_h is None else int(len(df_h)),
                }
            )
            if df_h is not None and not df_h.empty:
                hourly_path.parent.mkdir(parents=True, exist_ok=True)
                df_h.to_parquet(hourly_path)
        if force_bars or before.get("seconds"):
            df_s = await ib.req_historical_data(
                contract, duration="1 D", bar_size="1 sec", end_datetime=end_ts
            )
            ib_events.append(
                {
                    "event": "seconds_result",
                    "rows": 0 if df_s is None else int(len(df_s)),
                }
            )
            if df_s is not None and not df_s.empty:
                sec_path.parent.mkdir(parents=True, exist_ok=True)
                df_s.to_parquet(sec_path)
    finally:
        await ib.disconnect()


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--since", type=int, help="Include tasks with date >= today-N")
    p.add_argument("--last", type=int, help="Retain only last N distinct dates")
    p.add_argument(
        "--force-l2", action="store_true", help="Force L2 rewrite even if file exists"
    )
    p.add_argument(
        "--force-bars",
        action="store_true",
        help="Force re-download hourly and 1-sec bars",
    )
    p.add_argument(
        "--fallback-first",
        action="store_true",
        help="If no tasks need download, pick first Warrior row anyway",
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
    p.add_argument("--verbose", action="store_true")
    return p.parse_args()


def main() -> int:  # noqa: C901 - orchestration
    _bootstrap_env_for_local_data()
    cfg = get_config()
    args = _parse_args()

    # Setup logging file
    logs_dir = cfg.data_paths.logs_path
    logs_dir.mkdir(parents=True, exist_ok=True)
    _ensure_e2e_logger(logs_dir)

    # Discover first needed
    picked = _pick_first_needed(
        args.since, args.last, fallback_first=bool(args.fallback_first)
    )
    if not picked:
        print(
            json.dumps(
                {"status": "no_tasks", "message": "No Warrior tasks need downloads"},
                indent=2,
            )
        )
        return 0
    symbol, day = picked
    day_str = day.strftime("%Y-%m-%d")

    # Compute paths and existing state
    hourly_path = cfg.get_data_file_path(
        "ib_download", symbol=symbol, timeframe="1 hour", date_str=day_str
    )
    sec_path = cfg.get_data_file_path(
        "ib_download", symbol=symbol, timeframe="1 sec", date_str=day_str
    )
    before = compute_needs(symbol, day_str)

    # IB bars (async)
    ib_events: list[IBEvent] = []
    asyncio.run(
        _fetch_ib_bars_if_needed(
            symbol,
            day,
            hourly_path,
            sec_path,
            before,
            ib_events,
            force_bars=bool(args.force_bars),
            ib_host=args.ib_host,
            ib_port=args.ib_port,
            use_tws=bool(args.use_tws),
        )
    )

    # L2 backfill
    l2_result: dict[str, Any]
    if before.get("l2"):
        try:
            l2_result = backfill_l2(symbol, day, force=bool(args.force_l2))
        except Exception as e:  # pragma: no cover - vendor variability
            l2_result = {"status": "error", "error": str(e)}
    else:
        l2_result = {"status": "skipped_preexisting"}

    # After state and summary
    after_state = {
        "hourly": has_hourly(symbol, day_str),
        "seconds": has_seconds(symbol, day_str),
        "l2": has_l2(symbol, day_str),
    }
    summary = {
        "symbol": symbol,
        "day": day_str,
        "paths": {
            "warrior_csv": str(cfg.get_data_file_path("warrior_trading_trades")),
            "hourly": str(hourly_path),
            "seconds": str(sec_path),
            "level2_dir": str(
                cfg.data_paths.base_path / cfg.get_env("LEVEL2_DIRNAME") / symbol
            ),
            "ib_downloads_dir": str(
                cfg.data_paths.base_path / cfg.get_env("IB_DOWNLOADS_DIRNAME")
            ),
            "logs_dir": str(cfg.data_paths.logs_path),
        },
        "before_needs": before,
        "after_needs": after_state,
        "databento": {
            "enabled": bool(cfg.databento_api_key()),
            "result": l2_result,
        },
        "ib_events": ib_events,
        "env": {
            "L2_BACKFILL_WINDOW_ET": cfg.get_env("L2_BACKFILL_WINDOW_ET"),
            "DATABENTO_DATASET": cfg.get_env("DATABENTO_DATASET"),
            "DATABENTO_SCHEMA": cfg.get_env("DATABENTO_SCHEMA"),
        },
        "status": "ok",
    }

    # Persist and print
    out = cfg.data_paths.logs_path / f"e2e_single_{symbol}_{day_str}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))
    # Return non-zero if everything remained missing (indicates vendor/connectivity issues)
    if not any(after_state.values()):
        return 2
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
