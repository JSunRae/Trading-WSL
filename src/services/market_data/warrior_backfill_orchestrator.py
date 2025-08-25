"""Warrior list driven historical L2 backfill orchestrator.

Responsibilities:
    * Discover unique (symbol, trading_day) tasks from Warrior list
    * Lightweight filtering: since_days (relative to today), last (N most recent dates)
    * Optional max_tasks cap applied after ordering
    * Invoke programmatic backfill API (``backfill_l2``) per task
    * Maintain idempotent semantics (skip existing files unless ``force``)
    * Emit / append to existing manifest & summary artifacts used by legacy CLI:
          backfill_l2_manifest.jsonl  (JSON lines, one record per task)
          backfill_l2_summary.json    (aggregate run summary)
    * Classify zero-row vendor responses as EMPTY (separate from SKIP)

No external side effects beyond file writes in the configured data base path.
Safe to call multiple times; manifest appends, summary overwrites (latest run).
"""

from __future__ import annotations

import json
import logging
import os
import time
import warnings
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

import pandas as pd

from src.core.config import get_config
from src.services import data_management_service  # type: ignore
from src.services.market_data.backfill_api import backfill_l2
from src.services.symbol_mapping import load_symbol_mapping

__all__ = [
    "find_warrior_tasks",
    "run_warrior_backfill",
]


@dataclass(frozen=True)
class WarriorTask:
    symbol: str
    trading_day: date


def _load_warrior_df() -> pd.DataFrame | None:
    # Access via compatibility surface so tests / monkeypatching work
    warrior_list = getattr(data_management_service, "WarriorList", None)
    if warrior_list is None:  # pragma: no cover - defensive
        return None
    try:
        return warrior_list("Load")  # type: ignore[call-arg]
    except FileNotFoundError:
        return None
    except Exception:  # pragma: no cover - unexpected
        return None


def _extract_tasks(df: pd.DataFrame) -> list[WarriorTask]:
    if df is None or df.empty:  # type: ignore[truthy-bool]
        return []
    cols = {c.lower(): c for c in df.columns}
    sym_col = cols.get("symbol") or list(df.columns)[0]
    date_col = cols.get("date") or cols.get("trading_day") or list(df.columns)[1]
    tasks: list[WarriorTask] = []
    for _, row in df.iterrows():
        try:
            sym = str(row[sym_col]).upper().strip()
            if not sym:
                continue
            d_raw = row[date_col]
            if isinstance(d_raw, str):
                d = datetime.strptime(d_raw.split()[0], "%Y-%m-%d").date()
            elif isinstance(d_raw, datetime | pd.Timestamp):
                d = d_raw.date()
            elif isinstance(d_raw, date):  # pragma: no cover (rare path)
                d = d_raw
            else:
                continue
            tasks.append(WarriorTask(symbol=sym, trading_day=d))
        except Exception:  # pragma: no cover - row level robustness
            continue
    # Deduplicate
    uniq: dict[tuple[str, date], WarriorTask] = {
        (t.symbol, t.trading_day): t for t in tasks
    }
    return list(uniq.values())


def _apply_symbol_mapping_validator() -> None:
    cfg = get_config()
    try:
        mapping_path = cfg.get_symbol_mapping_path()
    except Exception:  # pragma: no cover
        return
    if not mapping_path or not mapping_path.exists():
        return
    try:
        mapping = load_symbol_mapping(mapping_path)
    except Exception:  # pragma: no cover
        return
    for k, v in mapping.items():
        if k == v:
            warnings.warn(
                f"Identity symbol mapping detected: {k}->{v}. Remove or adjust mapping file.",
                UserWarning,
                stacklevel=2,
            )


def find_warrior_tasks(
    *, since_days: int | None = None, last: int | None = None
) -> list[tuple[str, date]]:
    """Return ordered list of unique (symbol, trading_day) tasks.

    Parameters
    ----------
    since_days : int | None
        If provided, keep tasks with trading_day >= today - since_days.
    last : int | None
        If provided, keep only the last N distinct trading days (after other filters).
    """
    df = _load_warrior_df()
    tasks = _extract_tasks(df) if df is not None else []
    if not tasks:
        return []
    if since_days is not None and since_days >= 0:
        cutoff = date.today() - timedelta(days=since_days)
        tasks = [t for t in tasks if t.trading_day >= cutoff]
    # Sort by date then symbol for deterministic ordering
    tasks.sort(key=lambda t: (t.trading_day.toordinal(), t.symbol))
    if last is not None and last > 0:
        distinct_dates = sorted({t.trading_day for t in tasks})
        keep = set(distinct_dates[-last:])
        tasks = [t for t in tasks if t.trading_day in keep]
    # Run mapping validator (warning emission only)
    _apply_symbol_mapping_validator()
    return [(t.symbol, t.trading_day) for t in tasks]


def _manifest_paths():
    cfg = get_config()
    base = cfg.data_paths.base_path
    return (
        base / "backfill_l2_manifest.jsonl",
        base / "backfill_l2_summary.json",
    )


def run_warrior_backfill(
    tasks: Iterable[tuple[str, date]],
    *,
    force: bool = False,
    strict: bool = False,
    max_tasks: int | None = None,
    max_workers: int | None = None,
) -> dict[str, Any]:
    """Execute programmatic backfill over provided tasks.

    Returns a summary dict with keys:
        counts -> {WRITE, SKIP, EMPTY, ERROR}
        zero_row_tasks -> list[[symbol, date_str]]
        errors -> list[str] (human readable)
        total_tasks -> int (processed)
        duration_sec -> float
        strict -> bool
    """
    # Configure logging (idempotent) honoring LOG_LEVEL (default INFO)
    log_level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, log_level_name, logging.INFO)
    logger = logging.getLogger("warrior_backfill_orchestrator")
    if not logger.handlers:
        logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(message)s")
    else:
        logger.setLevel(level)

    start = time.time()
    ordered: list[tuple[str, date]] = list(tasks)
    ordered.sort(key=lambda x: (x[1].toordinal(), x[0]))
    if max_tasks is not None and max_tasks > 0:
        ordered = ordered[:max_tasks]
    counts = {k: 0 for k in ["WRITE", "SKIP", "EMPTY", "ERROR"]}
    zero_row_tasks: list[tuple[str, str]] = []
    errors: list[str] = []
    manifest_path, summary_path = _manifest_paths()
    if ordered:
        manifest_path.parent.mkdir(parents=True, exist_ok=True)

    def _append_manifest(record: dict[str, Any]) -> None:
        """Append a single JSON record to manifest (best-effort)."""
        try:
            with manifest_path.open("a", encoding="utf-8") as mf:
                mf.write(json.dumps(record) + "\n")
        except Exception:  # pragma: no cover - best effort
            pass

    # Decide concurrency: if explicit max_workers is None or 1 -> sequential (preserve old semantics)
    used_workers = 1
    if max_workers is not None and max_workers > 1:
        used_workers = max_workers

    logger.info(
        "Starting warrior backfill: tasks=%d force=%s strict=%s concurrency=%d",
        len(ordered),
        force,
        strict,
        used_workers,
    )

    # Buffer to ensure deterministic manifest order: (index, sym, date, result_dict)
    buffered: list[tuple[int, str, date, dict[str, Any]]] = []

    if used_workers == 1:
        for idx, (sym, day) in enumerate(ordered):
            date_str = day.strftime("%Y-%m-%d")
            logger.info("START %s %s", sym, date_str)
            result = backfill_l2(sym, day, force=force, strict=strict)
            logger.info("END %s %s status=%s", sym, date_str, result.get("status"))
            buffered.append((idx, sym, day, result))
    else:
        # Threaded execution; each worker returns its index & result
        def worker(idx_sym_day: tuple[int, tuple[str, date]]):
            idx, (sym, day) = idx_sym_day
            date_str = day.strftime("%Y-%m-%d")
            logger.info("START %s %s", sym, date_str)
            res = backfill_l2(sym, day, force=force, strict=strict)
            logger.info("END %s %s status=%s", sym, date_str, res.get("status"))
            return idx, sym, day, res

        with ThreadPoolExecutor(max_workers=used_workers) as ex:
            futures = [ex.submit(worker, (i, t)) for i, t in enumerate(ordered)]
            for fut in as_completed(futures):
                try:
                    buffered.append(fut.result())
                except Exception as e:  # pragma: no cover - unexpected
                    # Attach synthetic error result
                    idx = len(buffered)
                    buffered.append(
                        (
                            idx,
                            "UNKNOWN",
                            date.today(),
                            {"status": "error", "error": str(e), "zero_rows": False},
                        )
                    )

    # Sort buffered by original index to maintain order
    buffered.sort(key=lambda x: x[0])

    # Build manifest lines after classification to ensure deterministic order
    manifest_lines: list[str] = []
    for _idx, sym, day, result in buffered:
        status = result.get("status", "error").lower()
        zero = bool(result.get("zero_rows"))
        date_str = day.strftime("%Y-%m-%d")
        if status == "written":
            counts["WRITE"] += 1
        elif status == "skipped" and zero:
            counts["EMPTY"] += 1
            zero_row_tasks.append((sym, date_str))
            logger.warning("ZERO_ROWS %s %s", sym, date_str)
        elif status == "skipped":
            counts["SKIP"] += 1
        else:
            counts["ERROR"] += 1
            err = result.get("error") or f"unspecified error {sym} {date_str}"
            errors.append(f"{sym} {date_str} {err}")
            logger.error("ERROR %s %s %s", sym, date_str, err)
        manifest_lines.append(
            json.dumps(
                {
                    "symbol": sym,
                    "date": date_str,
                    "status": "EMPTY"
                    if zero and status == "skipped"
                    else status.upper(),
                }
            )
        )

    # Write manifest in one pass (append) preserving order
    if manifest_lines:
        for line in manifest_lines:
            _append_manifest(json.loads(line))
    duration = round(time.time() - start, 3)
    summary = {
        "counts": counts,
        "zero_row_tasks": zero_row_tasks,
        "errors": errors,
        "total_tasks": sum(counts.values()),
        "duration_sec": duration,
        "strict": strict,
        "force": force,
        "max_tasks": max_tasks,
        "concurrency": used_workers,
    }
    try:
        summary_path.write_text(json.dumps(summary, indent=2))
    except Exception:  # pragma: no cover
        pass
    logger.info(
        "SUMMARY WRITE=%d SKIP=%d EMPTY=%d ERROR=%d total=%d concurrency=%d duration=%.3fs",
        counts["WRITE"],
        counts["SKIP"],
        counts["EMPTY"],
        counts["ERROR"],
        summary["total_tasks"],
        used_workers,
        duration,
    )
    return summary
