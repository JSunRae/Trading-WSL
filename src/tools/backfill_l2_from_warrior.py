"""Historical Level-2 Backfill from DataBento for Warrior list symbols.

Fetch 08:00–11:30 ET (DST aware) order book from DataBento and store in IBKR-
compatible schema so downstream ML code can treat as interchangeable with IB live
L2. Optional dependency: works gracefully when DataBento SDK or API key absent.
"""

from __future__ import annotations

# --- ultra early describe guard ---
from typing import Any

from src.tools._cli_helpers import emit_describe_early  # type: ignore

# ruff: noqa: E402


def tool_describe() -> dict[str, Any]:
    return {
        "name": "backfill_l2_from_warrior",
        "description": "Backfill historical L2 (08:00-11:30 ET) from DataBento for each Warrior list trading day.",
        "inputs": {
            "--date": {"type": "str", "required": False},
            "--start": {"type": "str", "required": False},
            "--end": {"type": "str", "required": False},
            "--symbol": {"type": "str", "required": False},
            "--force": {"type": "flag", "required": False},
            "--dry-run": {"type": "flag", "required": False},
            "--strict": {"type": "flag", "required": False},
            "--max-tasks": {"type": "int", "required": False},
            "--since": {"type": "str", "required": False},
            "--last": {"type": "int", "required": False},
        },
        "outputs": {"stdout": "progress log"},
        "dependencies": [
            "optional:databento",
            "config:DATABENTO_API_KEY",
            "config:L2_BACKFILL_WINDOW_ET",
            "config:SYMBOL_MAPPING_FILE",
        ],
        "examples": [
            "python -m src.tools.backfill_l2_from_warrior --date 2025-07-29",
            "python -m src.tools.backfill_l2_from_warrior --start 2025-07-01 --end 2025-07-10 --symbol AAPL",
        ],
    }


def describe() -> dict[str, Any]:  # compatibility alias
    return tool_describe()


if emit_describe_early(tool_describe):  # pragma: no cover
    raise SystemExit(0)
# ---------------------------------------------------------------------------

import argparse
import logging
import os
import sys
from dataclasses import dataclass
from datetime import date, datetime
from zoneinfo import ZoneInfo

import pandas as pd

from src.core.config import get_config

# Import module so tests can monkeypatch data_management_service.WarriorList
from src.services import data_management_service  # type: ignore
from src.services.market_data.backfill_api import backfill_l2
from src.services.market_data.databento_l2_service import DataBentoL2Service
from src.services.market_data.l2_paths import with_source_suffix


@dataclass
class BackfillTask:
    symbol: str  # local symbol
    trading_day: date


ET_TZ = ZoneInfo("America/New_York")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--date")
    p.add_argument("--start")
    p.add_argument("--end")
    p.add_argument("--symbol")
    p.add_argument("--force", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--strict", action="store_true")
    p.add_argument("--max-tasks", type=int)
    p.add_argument("--since")
    p.add_argument("--last", type=int)
    return p.parse_args()


def iter_date_range(
    single: str | None, start: str | None, end: str | None
) -> list[date]:
    if single:
        return [datetime.strptime(single, "%Y-%m-%d").date()]
    if start and end:
        s = datetime.strptime(start, "%Y-%m-%d").date()
        e = datetime.strptime(end, "%Y-%m-%d").date()
        if e < s:
            raise ValueError("--end before --start")
        days: list[date] = []
        cur = s
        while cur <= e:
            days.append(cur)
            cur = date.fromordinal(cur.toordinal() + 1)
        return days
    return []


def load_warrior_dates(symbol_filter: str | None) -> list[BackfillTask]:
    # Access WarriorList via module attribute (enables monkeypatching in tests)
    warrior_list_cls = data_management_service.WarriorList  # type: ignore[attr-defined]
    df = warrior_list_cls("Load")  # type: ignore[arg-type]
    tasks: list[BackfillTask] = []
    if df is None or df.empty:
        return tasks
    # Heuristic columns: expecting at least a SYMBOL and DATE column or similar.
    cols = {c.lower(): c for c in df.columns}
    sym_col = cols.get("symbol") or list(df.columns)[0]
    date_col = cols.get("date") or cols.get("trading_day") or list(df.columns)[1]
    for _, row in df.iterrows():
        sym = str(row[sym_col]).upper()
        if symbol_filter and sym != symbol_filter.upper():
            continue
        try:
            d = row[date_col]
            if isinstance(d, str):
                trading_day = datetime.strptime(d.split()[0], "%Y-%m-%d").date()
            elif isinstance(d, datetime | pd.Timestamp):  # type: ignore[arg-type]
                trading_day = d.date()
            else:
                continue
            tasks.append(BackfillTask(symbol=sym, trading_day=trading_day))
        except Exception:
            continue
    # Deduplicate
    uniq: dict[tuple[str, date], BackfillTask] = {
        (t.symbol, t.trading_day): t for t in tasks
    }
    return list(uniq.values())


from pathlib import Path


def _configure_logger(base_path: os.PathLike[str] | str) -> logging.Logger:
    """Configure a dedicated logger (idempotent) writing to stdout + file.

    Format kept as raw message to preserve existing test expectations.
    """
    logger = logging.getLogger("backfill_l2")
    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    logger.setLevel(level)
    logger.propagate = False
    fmt = logging.Formatter("%(message)s")

    # Always recreate stream handler pointing at current sys.stdout (redirect_stdout compatibility)
    for h in list(logger.handlers):
        if isinstance(h, logging.StreamHandler):
            logger.removeHandler(h)
    sh = logging.StreamHandler(stream=sys.stdout)
    sh.setFormatter(fmt)
    logger.addHandler(sh)

    # Add file handler once
    if not any(isinstance(h, logging.FileHandler) for h in logger.handlers):
        try:  # pragma: no cover
            log_path = Path(base_path) / "backfill.log"
            fh = logging.FileHandler(log_path, encoding="utf-8")
            fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
            logger.addHandler(fh)
        except Exception:  # pragma: no cover
            pass
    return logger


def main() -> int:  # noqa: C901 - acceptable procedural orchestration
    args = parse_args()
    cfg = get_config()
    logger = _configure_logger(cfg.data_paths.base_path)

    requested_dates = iter_date_range(args.date, args.start, args.end)

    start_str, end_str = cfg.get_l2_backfill_window()
    # Window retained (unused directly after API extraction; preserved for potential logging or future parity checks)
    _ = (start_str, end_str)

    api_key = cfg.databento_api_key()

    vendor_service = DataBentoL2Service(api_key)

    try:
        tasks = load_warrior_dates(args.symbol)
    except FileNotFoundError as e:  # underlying WarriorTrading_Trades.xlsx missing
        logger.warning(f"Warning: {e}")
        tasks = []
    if requested_dates:
        tasks = [t for t in tasks if t.trading_day in set(requested_dates)]
        if not tasks:  # fallback: allow explicit date range even if warrior list absent
            fallback_symbol = args.symbol or "AAPL"
            tasks = [
                BackfillTask(symbol=fallback_symbol, trading_day=d)
                for d in requested_dates
            ]
    if args.since:
        try:
            since_d = datetime.strptime(args.since, "%Y-%m-%d").date()
            tasks = [t for t in tasks if t.trading_day >= since_d]
        except Exception:
            logger.warning("WARN invalid --since ignored")
    if args.last and args.last > 0:
        # Keep last N distinct dates after other filters
        by_date = sorted({t.trading_day for t in tasks})
        keep_dates = set(by_date[-args.last :])
        tasks = [t for t in tasks if t.trading_day in keep_dates]
    if args.max_tasks and args.max_tasks > 0:
        tasks = tasks[: args.max_tasks]
    if not tasks:
        logger.info("No tasks (no warrior entries or date filter empty)")
        # Still emit a summary line for consistency with tests expecting it
        conc = max(1, cfg.get_l2_backfill_concurrency())
        summary_line = f"SUMMARY WRITE=0 SKIP=0 EMPTY=0 WARN=0 ERROR=0 DRY=0 UNAVAIL=0 concurrency={conc}"
        logger.info(summary_line)
        print(summary_line)
        return 0

    # ---- task processing helpers ------------------------------------------------
    error_messages: dict[tuple[str, str], str] = {}
    zero_row_tasks: list[tuple[str, str]] = []

    def process_task(task: BackfillTask) -> tuple[str, str, str]:
        """Return (status, symbol, date_str). Status: SKIP|WRITE|EMPTY|WARN|ERROR.

        Delegates core logic to services.market_data.backfill_api.backfill_l2 to
        ensure single authoritative implementation. CLI-level status vocabulary
        preserved for backward compatibility tests.
        """
        local_symbol = task.symbol
        date_str = task.trading_day.strftime("%Y-%m-%d")
        # Handle dry-run early (avoid touching vendor)
        base_path = cfg.get_data_file_path(
            "level2", symbol=local_symbol, date_str=date_str
        )
        dest = with_source_suffix(base_path, "databento")
        if dest.exists() and not args.force:
            return ("SKIP", local_symbol, date_str)
        if args.dry_run:
            return ("DRY", local_symbol, date_str)
        if not vendor_service.is_available(api_key):
            msg = "DataBento unavailable (missing package or API key)."
            if args.strict:
                raise SystemExit(msg)
            logger.warning(f"WARN {local_symbol} {date_str} {msg}")
            print(f"WARN {local_symbol} {date_str} {msg}", flush=True)
            return ("WARN", local_symbol, date_str)
        result = backfill_l2(
            local_symbol, task.trading_day, force=args.force, strict=args.strict
        )
        status_map = {"written": "WRITE", "skipped": "SKIP", "error": "ERROR"}
        status = status_map.get(result["status"].lower(), "ERROR")
        if result.get("zero_rows"):
            zero_row_tasks.append((local_symbol, date_str))
            logger.warning(f"EMPTY {local_symbol} {date_str} (zero rows)")
            print(f"EMPTY {local_symbol} {date_str} (zero rows)", flush=True)
            return ("EMPTY", local_symbol, date_str)
        # Explicitly log error even if not surfaced earlier
        if status == "ERROR" and not result.get("error"):
            line = f"ERROR {local_symbol} {date_str} (unspecified error)"
            logger.error(line)
            print(line, flush=True)
        if status == "ERROR" and result.get("error"):
            error_messages[(local_symbol, date_str)] = result["error"]
            line = f"ERROR {local_symbol} {date_str} {result['error']}"
            logger.error(line)
            print(line, flush=True)
        return (status, local_symbol, date_str)

    ordered_tasks = sorted(tasks, key=lambda t: (t.trading_day.toordinal(), t.symbol))
    concurrency = max(1, cfg.get_l2_backfill_concurrency())
    summary = {
        k: 0 for k in ["WRITE", "SKIP", "EMPTY", "WARN", "ERROR", "DRY", "UNAVAIL"]
    }
    manifest_path = cfg.data_paths.base_path / "backfill_l2_manifest.jsonl"
    summary_json_path = cfg.data_paths.base_path / "backfill_l2_summary.json"

    if concurrency == 1:
        for t in ordered_tasks:
            status, sym, d = process_task(t)
            summary[status] = summary.get(status, 0) + 1
            line = f"{status} {sym} {d}"
            logger.info(line)
            print(line, flush=True)
            # Append manifest per completed task
            try:
                import json as _json

                with manifest_path.open("a", encoding="utf-8") as mf:
                    mf.write(
                        _json.dumps({"symbol": sym, "date": d, "status": status}) + "\n"
                    )
            except Exception:  # pragma: no cover - best effort
                pass
    else:
        from concurrent.futures import ThreadPoolExecutor, as_completed

        try:
            with ThreadPoolExecutor(max_workers=concurrency) as ex:
                fut_map = {ex.submit(process_task, t): t for t in ordered_tasks}
                for fut in as_completed(fut_map):
                    status, sym, d = fut.result()
                    summary[status] = summary.get(status, 0) + 1
                    line = f"{status} {sym} {d}"
                    logger.info(line)
                    print(line, flush=True)
                    try:
                        import json as _json

                        with manifest_path.open("a", encoding="utf-8") as mf:
                            mf.write(
                                _json.dumps(
                                    {"symbol": sym, "date": d, "status": status}
                                )
                                + "\n"
                            )
                    except Exception:  # pragma: no cover
                        pass
        except KeyboardInterrupt:  # pragma: no cover - interactive safeguard
            logger.error("INTERRUPTED - cancelling outstanding tasks")
            return 130

    # Build JSON run summary for observability
    try:
        import json as _json

        summary_json = {
            "counts": summary,
            "zero_row_tasks": zero_row_tasks,
            "errors": {f"{sym}|{d}": msg for (sym, d), msg in error_messages.items()},
            "total_tasks": sum(summary.values()),
            "concurrency": concurrency,
            "timestamp": datetime.now(tz=ZoneInfo("UTC")).isoformat(),
            "max_rows_per_task": int(os.getenv("L2_MAX_ROWS_PER_TASK", "0") or 0),
        }
        summary_json_path.write_text(_json.dumps(summary_json, indent=2))
    except Exception:  # pragma: no cover
        pass

    # Always include all status keys (even zero) so tests relying on pattern find concurrency
    summary_line = (
        "SUMMARY "
        + " ".join(f"{k}={summary.get(k, 0)}" for k in sorted(summary.keys()))
        + f" concurrency={concurrency}"
    )
    logger.info(summary_line)
    print(summary_line, flush=True)
    # Emit explicit ERROR lines derived from summary json (ensures visibility under concurrency in tests)
    try:  # pragma: no cover - simple loop
        for sym_date, msg in error_messages.items():
            # sym_date stored separately earlier; reconstruct fields
            sym, d = sym_date
            line = f"ERROR {sym} {d} {msg}"
            print(line, flush=True)
    except Exception:  # pragma: no cover
        pass
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
