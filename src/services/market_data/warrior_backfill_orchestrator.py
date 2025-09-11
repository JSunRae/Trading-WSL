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
import re
import time
import warnings
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any, cast

import pandas as pd

from src.core.config import get_config
from src.services import data_management_service  # type: ignore
from src.services.market_data.backfill_api import backfill_l2
from src.services.symbol_mapping import load_symbol_mapping

__all__ = [
    "find_warrior_tasks",
    "run_warrior_backfill",
]

# Keep a handle to the original deprecated shim (if present) so we can detect
# test monkeypatching reliably without relying on __module__ heuristics.
_ORIGINAL_WARRIOR_LIST = getattr(data_management_service, "WarriorList", None)


@dataclass(frozen=True)
class WarriorTask:
    symbol: str
    trading_day: date


def _load_warrior_df_modern() -> pd.DataFrame | None:
    """Preferred modern load via data service API."""
    try:
        get_svc = getattr(data_management_service, "get_data_service", None)
        if not callable(get_svc):
            return None
        svc = get_svc()
        dm = getattr(svc, "data_manager", None)
        if dm is None or not hasattr(dm, "warrior_list_operations"):
            return None
        return cast(pd.DataFrame | None, dm.warrior_list_operations("load"))  # type: ignore[attr-defined]
    except FileNotFoundError:
        return None
    except Exception:
        return None


def _load_warrior_df() -> pd.DataFrame | None:
    """Load Warrior list DataFrame using the modern API only.

    The deprecated WarriorList shim is intentionally not called to avoid
    emitting DeprecationWarning. If the modern API is unavailable or returns
    None, the caller will treat it as no tasks found.
    """
    df = _load_warrior_df_modern()
    if df is not None:
        return df

    # Optional legacy shim if tests monkeypatch WarriorList. We only invoke it
    # when the attribute has been replaced (object identity differs from the
    # original), to avoid triggering the deprecated shim in production.
    warrior_list = getattr(data_management_service, "WarriorList", None)
    if callable(warrior_list):
        # Don't invoke if it's the original deprecated shim
        if (
            _ORIGINAL_WARRIOR_LIST is not None
            and warrior_list is _ORIGINAL_WARRIOR_LIST
        ):
            return None
        wl_mod = str(getattr(warrior_list, "__module__", ""))
        if wl_mod == getattr(data_management_service, "__name__", ""):
            # Still the same module (not monkeypatched) -> don't call
            return None
        # Looks monkeypatched (e.g. tests assign a lambda) -> allow call, suppress deprecation
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", DeprecationWarning)
                return cast(pd.DataFrame | None, warrior_list("Load"))  # type: ignore[call-arg]
        except FileNotFoundError:
            return None
        except Exception:
            return None
    return None


def _looks_like_ticker(val: object) -> bool:
    """Heuristic check for US-style ticker strings."""
    try:
        import pandas as _pd  # local import to avoid global dependency in type checkers

        _isna = getattr(_pd, "isna", None)
        if callable(_isna) and _isna(val):  # type: ignore[func-returns-value]
            return False
    except Exception:
        pass
    if not isinstance(val, str):
        try:
            val = str(val)
        except Exception:
            return False
    s = val.strip().upper()
    if not s or s in {"NAN", "NAT", "NA", "NONE", "NULL"}:
        return False
    return bool(re.fullmatch(r"[A-Z][A-Z0-9\.-]{0,6}", s))


def _score_ticker(series: pd.Series) -> int:
    sample = series.dropna().head(20)
    return sum(1 for v in sample if _looks_like_ticker(v))


def _score_date(series: pd.Series) -> int:
    sample = series.dropna().head(20)
    ok = 0
    for v in sample:
        if isinstance(v, datetime | pd.Timestamp | date):
            ok += 1
        elif isinstance(v, str):
            try:
                pd.to_datetime(v, errors="raise")
                ok += 1
            except Exception:
                pass
    return ok


def _select_columns(df: pd.DataFrame) -> tuple[str, str]:
    """Choose (symbol_col, date_col) preferring explicit names, then synonyms/scoring.

    Preference order:
        1) "ticker" and "date" headers if present
        2) Known synonyms (symbol/ticker synonyms, date synonyms)
        3) Heuristic scoring fallback
    """
    cols = {str(c).strip().lower(): c for c in df.columns}
    # Strong preference for CSV schema
    if "ticker" in cols and "date" in cols:
        return str(cols["ticker"]), str(cols["date"])
    sym_synonyms = [
        "symbol",
        "ticker",
        "sym",
        "stock",
        "instrument",
        "code",
        "ticker symbol",
    ]
    date_synonyms = [
        "date",
        "trading_day",
        "trading day",
        "trade_date",
        "execution_date",
        "date executed",
        "exec_date",
        "day",
    ]
    sym_col_name = next((cols[n] for n in sym_synonyms if n in cols), None)
    date_col_name = next((cols[n] for n in date_synonyms if n in cols), None)
    if sym_col_name is None or date_col_name is None:
        best_sym, best_sym_score = None, -1
        best_date, best_date_score = None, -1
        for c in df.columns:
            s_t = _score_ticker(df[c])
            if s_t > best_sym_score:
                best_sym, best_sym_score = c, s_t
            s_d = _score_date(df[c])
            if s_d > best_date_score:
                best_date, best_date_score = c, s_d
        sym_col_name = sym_col_name or best_sym or df.columns[0]
        if date_col_name is None:
            date_col_name = (
                best_date
                if best_date is not None
                else (df.columns[1] if len(df.columns) > 1 else df.columns[0])
            )
        if date_col_name == sym_col_name and len(df.columns) > 1:
            date_col_name = df.columns[1]
    return str(sym_col_name), str(date_col_name)


def _parse_date_like(v: object) -> date | None:
    if isinstance(v, datetime | pd.Timestamp):
        return v.date()  # type: ignore[return-value]
    if isinstance(v, date):  # pragma: no cover (rare path)
        return v
    d_parsed = pd.to_datetime(str(v), errors="coerce")
    if pd.isna(d_parsed):
        return None
    # At this point, d_parsed is a non-NaT Timestamp-like object; use .date()
    try:
        return d_parsed.date()  # type: ignore[union-attr]
    except Exception:  # pragma: no cover - defensive
        try:
            return datetime.fromtimestamp(d_parsed).date()  # type: ignore[arg-type]
        except Exception:
            return None


def _iter_tasks(
    df: pd.DataFrame, sym_col: str, date_col: str
) -> tuple[list[WarriorTask], list[tuple[str, str]]]:
    tasks: list[WarriorTask] = []
    debug_raw: list[tuple[str, str]] = []
    for _, row in df.iterrows():
        try:
            raw_sym = row[sym_col]
            # Normalize symbols: dots/slashes -> dashes; uppercase & trim
            sym = str(raw_sym).upper().strip().replace("/", "-").replace(".", "-")
            if not sym or not _looks_like_ticker(sym):
                continue
            d = _parse_date_like(row[date_col])
            if d is None:
                continue
            tasks.append(WarriorTask(symbol=sym, trading_day=d))
            if len(debug_raw) < 100:
                debug_raw.append((sym, d.isoformat()))
        except Exception:  # pragma: no cover - row level robustness
            continue
    return tasks, debug_raw


def _write_debug(
    df: pd.DataFrame,
    sym_col: str,
    date_col: str,
    debug_raw: list[tuple[str, str]],
    tasks: list[WarriorTask],
    result: list[WarriorTask],
) -> None:
    try:
        cfg = get_config()
        base = cfg.data_paths.base_path
    except Exception:  # pragma: no cover - defensive
        base = None
    try:
        debug_payload = {
            "timestamp": datetime.now(UTC).isoformat(),
            "columns": list(df.columns),
            "symbol_column": str(sym_col),
            "date_column": str(date_col),
            "sample_symbol_values": [
                str(v) for v in df[sym_col].dropna().astype(str).head(10).tolist()
            ]
            if sym_col in df.columns
            else [],
            "sample_date_values": [
                (
                    str(v)
                    if not isinstance(v, pd.Timestamp | datetime)
                    else v.date().isoformat()
                )
                for v in df[date_col].dropna().head(10).tolist()
            ]
            if date_col in df.columns
            else [],
            "raw_pairs_sample": debug_raw[:20],
            "pre_dedupe_count": len(tasks),
            "post_dedupe_count": len(result),
        }
        if base is not None:
            out_path = base / "warrior_task_debug.json"
        else:
            out_path = Path("~/warrior_task_debug.json").expanduser()
        with out_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(debug_payload) + "\n")
    except Exception:  # pragma: no cover - best effort
        pass


def _extract_tasks(df: pd.DataFrame) -> list[WarriorTask]:
    """Extract unique (symbol, trading_day) pairs from a Warrior list DataFrame."""
    if df is None or df.empty:  # type: ignore[truthy-bool]
        return []
    sym_col_name, date_col_name = _select_columns(df)
    tasks, debug_raw = _iter_tasks(df, sym_col_name, date_col_name)
    uniq: dict[tuple[str, date], WarriorTask] = {
        (t.symbol, t.trading_day): t for t in tasks
    }
    result = list(uniq.values())
    _write_debug(df, sym_col_name, date_col_name, debug_raw, tasks, result)
    return result


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

    # Optionally skip weekend dates at discovery time (disabled by default to keep tests deterministic)
    skip_weekends = get_config().get_env_bool("L2_SKIP_WEEKENDS", False)
    weekend_skipped = 0
    if skip_weekends:

        def _is_weekend(d: date) -> bool:
            # Monday=0 ... Sunday=6
            return d.weekday() >= 5

        weekend_skipped = sum(1 for t in tasks if _is_weekend(t.trading_day))
        tasks = [t for t in tasks if not _is_weekend(t.trading_day)]
    # Sort by date then symbol for deterministic ordering
    tasks.sort(key=lambda t: (t.trading_day.toordinal(), t.symbol))
    if last is not None and last > 0:
        distinct_dates = sorted({t.trading_day for t in tasks})
        keep = set(distinct_dates[-last:])
        tasks = [t for t in tasks if t.trading_day in keep]
    # Run mapping validator (warning emission only)
    _apply_symbol_mapping_validator()
    # Emit a brief summary debug file with counts and source path to Warrior sheet
    try:
        cfg = get_config()
        base = cfg.data_paths.base_path
        try:
            warrior_path = cfg.get_data_file_path("warrior_trading_trades")
        except Exception:
            warrior_path = None
        summary_debug = {
            "timestamp": datetime.now(UTC).isoformat(),
            "total_tasks_after_filters": len(tasks),
            "weekend_skipped": int(weekend_skipped),
            "since_days": since_days,
            "last": last,
            "warrior_sheet_path": str(warrior_path) if warrior_path else None,
            "first_tasks": [(t.symbol, t.trading_day.isoformat()) for t in tasks[:10]],
        }
        (base / "warrior_task_summary.json").write_text(
            json.dumps(summary_debug, indent=2)
        )
    except Exception:  # pragma: no cover - best effort
        pass
    return [(t.symbol, t.trading_day) for t in tasks]


def _manifest_paths():
    cfg = get_config()
    base = cfg.data_paths.base_path
    return (
        base / "backfill_l2_manifest.jsonl",
        base / "backfill_l2_summary.json",
    )


def _init_logger() -> logging.Logger:
    """Initialize module logger honoring LOG_LEVEL env."""
    log_level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, log_level_name, logging.INFO)
    logger = logging.getLogger("warrior_backfill_orchestrator")
    if not logger.handlers:
        logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(message)s")
    else:
        logger.setLevel(level)
    return logger


def _decide_workers(max_workers: int | None) -> int:
    if max_workers is not None and max_workers > 1:
        return max_workers
    return 1


def _prepare_order(
    tasks: Iterable[tuple[str, date]], max_tasks: int | None
) -> list[tuple[str, date]]:
    ordered = list(tasks)
    ordered.sort(key=lambda x: (x[1].toordinal(), x[0]))
    if max_tasks is not None and max_tasks > 0:
        ordered = ordered[:max_tasks]
    return ordered


def _execute_ordered_tasks(
    ordered: list[tuple[str, date]],
    used_workers: int,
    *,
    force: bool,
    strict: bool,
    logger: logging.Logger,
) -> list[tuple[int, str, date, dict[str, Any]]]:
    """Execute backfill over ordered tasks; preserve index for ordering."""
    buffered: list[tuple[int, str, date, dict[str, Any]]] = []

    def _run_sequential() -> None:
        for idx, (sym, day) in enumerate(ordered):
            date_str = day.strftime("%Y-%m-%d")
            logger.info("START %s %s", sym, date_str)
            result = backfill_l2(sym, day, force=force, strict=strict)
            logger.info("END %s %s status=%s", sym, date_str, result.get("status"))
            buffered.append((idx, sym, day, result))

    def _run_threaded(workers: int) -> None:
        def worker(idx_sym_day: tuple[int, tuple[str, date]]):
            idx, (sym, day) = idx_sym_day
            date_str = day.strftime("%Y-%m-%d")
            logger.info("START %s %s", sym, date_str)
            res = backfill_l2(sym, day, force=force, strict=strict)
            logger.info("END %s %s status=%s", sym, date_str, res.get("status"))
            return idx, sym, day, res

        with ThreadPoolExecutor(max_workers=workers) as ex:
            futures = [ex.submit(worker, (i, t)) for i, t in enumerate(ordered)]
            for fut in as_completed(futures):
                try:
                    buffered.append(fut.result())
                except Exception as e:  # pragma: no cover - unexpected
                    idx = len(buffered)
                    buffered.append(
                        (
                            idx,
                            "UNKNOWN",
                            date.today(),
                            {"status": "error", "error": str(e), "zero_rows": False},
                        )
                    )

    if used_workers == 1:
        _run_sequential()
    else:
        _run_threaded(used_workers)

    buffered.sort(key=lambda x: x[0])
    return buffered


def _classify_results(
    entries: list[tuple[int, str, date, dict[str, Any]]],
    logger: logging.Logger,
) -> tuple[dict[str, int], list[tuple[str, str]], list[str], list[dict[str, str]]]:
    counts = {k: 0 for k in ["WRITE", "SKIP", "EMPTY", "ERROR"]}
    zero_row_tasks: list[tuple[str, str]] = []
    errors: list[str] = []
    records: list[dict[str, str]] = []
    for _idx, sym, day, result in entries:
        status = str(result.get("status", "error")).lower()
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
        records.append(
            {
                "symbol": sym,
                "date": date_str,
                "status": "EMPTY" if zero and status == "skipped" else status.upper(),
            }
        )
    return counts, zero_row_tasks, errors, records


def _write_manifest(manifest_path: Path, records: list[dict[str, str]]) -> None:
    if not records:
        return
    try:
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
    except Exception:  # pragma: no cover - best effort
        pass
    try:
        with manifest_path.open("a", encoding="utf-8") as mf:
            for rec in records:
                mf.write(json.dumps(rec) + "\n")
    except Exception:  # pragma: no cover - best effort
        pass


def _write_summary(
    summary_path: Path,
    *,
    counts: dict[str, int],
    zero_row_tasks: list[tuple[str, str]],
    errors: list[str],
    duration: float,
    strict: bool,
    force: bool,
    max_tasks: int | None,
    used_workers: int,
    run_id: str,
) -> dict[str, Any]:
    try:
        win_start, win_end = get_config().get_l2_backfill_window()
    except Exception:
        win_start, win_end = None, None
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
        "run_id": run_id,
        "requested_window_et": {"start": win_start, "end": win_end},
    }
    try:
        summary_path.write_text(json.dumps(summary, indent=2))
    except Exception:  # pragma: no cover
        pass
    return summary


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
    logger = _init_logger()
    start = time.time()
    run_id = datetime.now(UTC).strftime("%Y%m%d-%H%M%S-%f")
    ordered = _prepare_order(tasks, max_tasks)
    used_workers = _decide_workers(max_workers)
    manifest_path, summary_path = _manifest_paths()

    logger.info(
        "Starting warrior backfill: tasks=%d force=%s strict=%s concurrency=%d",
        len(ordered),
        force,
        strict,
        used_workers,
    )

    buffered = _execute_ordered_tasks(
        ordered, used_workers, force=force, strict=strict, logger=logger
    )
    counts, zero_row_tasks, errors, manifest_records = _classify_results(
        buffered, logger
    )
    _write_manifest(manifest_path, manifest_records)
    duration = round(time.time() - start, 3)

    summary = _write_summary(
        summary_path,
        counts=counts,
        zero_row_tasks=zero_row_tasks,
        errors=errors,
        duration=duration,
        strict=strict,
        force=force,
        max_tasks=max_tasks,
        used_workers=used_workers,
        run_id=run_id,
    )
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
