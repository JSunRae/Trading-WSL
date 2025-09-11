"""Programmatic Level 2 (order book) historical backfill API.

Extracted from the CLI tool ``src/tools/backfill_l2_from_warrior.py`` to enable
direct library usage without shell orchestration. Behaviour intentionally
matches the CLI implementation (idempotent writes, suffixing, mapping, window
handling, truncation guard) and reuses the same helpers so on‑disk schema and
layout remain unchanged.

Only a *single* (symbol, trading_day) is processed per call; batching,
concurrency, manifest & summary aggregation remain responsibilities of the
caller (CLI or higher‑level orchestrators).
"""

from __future__ import annotations

import os
import time as _time
from datetime import date
from typing import Any

import pandas as pd

from src.core.config import get_config
from src.services.market_data.databento_l2_service import (
    DATABENTO_AVAILABLE,
    DataBentoL2Service,
    VendorL2Request,
    VendorUnavailable,
)
from src.services.market_data.l2_paths import atomic_write_parquet, with_source_suffix
from src.services.market_data.l2_schema_adapter import to_ibkr_l2
from src.services.symbol_mapping import resolve_vendor_params

__all__ = ["backfill_l2"]


def _now_ns() -> int:
    return int(_time.time() * 1_000_000_000)


def backfill_l2(  # noqa: C901 - orchestration style kept intentionally simple
    symbol: str,
    trading_day: date,
    *,
    force: bool = False,
    strict: bool = False,
    max_rows_per_task: int | None = None,
    summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Programmatic L2 backfill for a single (symbol, trading_day).

    Parameters mirror CLI flags where relevant. The function is *idempotent*:
    if the destination file already exists it returns a skipped result unless
    ``force=True``.

    Returns
    -------
    dict
        { 'symbol', 'date', 'status', 'rows', 'path', 'duration_ms',
          'zero_rows', 'error' }
        where status in {'written','skipped','error'}.

    Side Effects
    ------------
    Writes a parquet file suffixed with ``_databento`` (atomic temp rename) in
    the same location used by the CLI tool.
    """

    cfg = get_config()
    start_ns = _now_ns()
    date_str = trading_day.strftime("%Y-%m-%d")

    # Resolve vendor mapping + window + dataset/schema
    api_key = cfg.databento_api_key()
    dataset = cfg.get_env("DATABENTO_DATASET")
    schema = cfg.get_env("DATABENTO_SCHEMA")
    vendor_symbol, dataset, schema = resolve_vendor_params(
        symbol, "databento", cfg.get_symbol_mapping_path(), dataset, schema
    )
    start_et_str, end_et_str = cfg.get_l2_backfill_window()
    from datetime import time as _time_cls

    start_et = _time_cls.fromisoformat(start_et_str)
    end_et = _time_cls.fromisoformat(end_et_str)

    # Enforce trading window for Level 2 via config clamp (default 09:00–11:00 ET)
    if cfg.get_env_bool("L2_ENFORCE_TRADING_WINDOW", True):
        tw_start, tw_end = cfg.get_env("L2_TRADING_WINDOW_ET", "09:00-11:00").split(
            "-", 1
        )
        tw_s = _time_cls.fromisoformat(tw_start.strip())
        tw_e = _time_cls.fromisoformat(tw_end.strip())
        # clamp
        start_et = max(start_et, tw_s)
        end_et = min(end_et, tw_e)

    # Destination path (shared with CLI)
    base_path = cfg.get_data_file_path("level2", symbol=symbol, date_str=date_str)
    dest = with_source_suffix(base_path, "databento")

    def _final(
        status: str, *, rows: int = 0, zero: bool = False, error: str | None = None
    ) -> dict[str, Any]:  # local helper to collapse branches
        duration_ms = (_now_ns() - start_ns) // 1_000_000
        res = {
            "symbol": symbol,
            "date": date_str,
            "status": status,
            "rows": rows,
            "path": str(dest),
            "duration_ms": duration_ms,
            "zero_rows": zero,
            "error": error,
        }
        if summary is not None:
            key_map = {"written": "written", "skipped": "skipped", "error": "error"}
            if status in key_map:
                summary.setdefault(key_map[status], 0)
                summary[key_map[status]] += 1
            if zero:
                summary.setdefault("zero_rows", 0)
                summary["zero_rows"] += 1
            if status == "written":
                summary.setdefault("total_rows", 0)
                summary["total_rows"] += rows
        return res

    if dest.exists() and not force:
        return _final("skipped")

    # Vendor availability guard (matches CLI semantics)
    vendor_service = DataBentoL2Service(api_key)
    # Provide a more actionable error message for availability failures
    if not vendor_service.is_available(api_key):
        if not DATABENTO_AVAILABLE:
            return _final(
                "error",
                error=(
                    "DataBento package not installed. Install optional extra: "
                    "pip install -e .[databento]"
                ),
            )
        if not api_key:
            return _final(
                "error",
                error=(
                    "DATABENTO_API_KEY missing. Add it to your .env at project root "
                    "or export it in the environment."
                ),
            )
        # Fallback generic message (should be rare)
        return _final(
            "error", error="DataBento unavailable (unknown availability failure)."
        )

    # Build vendor request & fetch (isolated for complexity reduction)
    def _fetch_vendor() -> dict[str, Any] | pd.DataFrame:
        try:
            vreq = VendorL2Request(
                dataset=dataset,
                schema=schema,
                symbol=vendor_symbol,
                start_et=start_et,
                end_et=end_et,
                trading_day=trading_day,
            )
            return vendor_service.fetch_l2(vreq)
        except VendorUnavailable as e:  # pragma: no cover - defensive
            return _final("error", error=f"VendorUnavailable: {e}")
        except Exception as e:  # pragma: no cover - network variability
            return _final("error", error=repr(e))

    df_vendor = _fetch_vendor()
    if isinstance(df_vendor, dict):  # early error result
        return df_vendor

    # Zero row handling (no file write, treat as skipped variant with flag)
    if df_vendor.empty:
        return _final("skipped", zero=True)

    # Adapt to internal schema
    df_ib = to_ibkr_l2(df_vendor, source="databento", symbol=symbol)

    # Row cap (same env var as CLI)
    if max_rows_per_task is None:
        try:
            max_rows_env = int(os.getenv("L2_MAX_ROWS_PER_TASK", "0") or 0)
        except ValueError:
            max_rows_env = 0
    else:
        max_rows_env = max_rows_per_task
    if max_rows_env > 0 and len(df_ib) > max_rows_env:
        df_ib = df_ib.iloc[:max_rows_env].copy()

    # Atomic write
    atomic_write_parquet(df_ib, dest, overwrite=force)
    rows = len(df_ib)

    return _final("written", rows=rows)
