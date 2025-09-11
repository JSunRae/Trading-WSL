#!/usr/bin/env python3
"""Modern lightweight data update CLI.

Refactored from legacy verbose implementation. This tool now:
 - Uses DataManager + HistoricalDataService only.
 - Provides focused operations: bulk symbol update over bar sizes.
 - Avoids legacy request/download tracker APIs directly (DataManager abstraction).

It intentionally keeps similar argument names to minimize external change.
"""

from __future__ import annotations

import argparse
import json
import logging
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from time import perf_counter

from src.core.config import get_config
from src.data.data_manager import DataManager
from src.services.historical_data_service import (
    BarSize,
    DataType,
    DownloadRequest,
    HistoricalDataService,
)

logger = logging.getLogger("update_data")


def _coerce_date(d: str | None) -> date | None:
    if not d:
        return None
    try:
        return datetime.strptime(d, "%Y-%m-%d").date()
    except Exception:  # pragma: no cover
        return None


def _iter_recent_trade_days(days: int, end: date | None = None) -> list[date]:
    end_dt = end or datetime.today().date()
    return [end_dt - timedelta(days=offset) for offset in range(days - 1, -1, -1)]


def _expand_timeframe_dates(tf: str, base: date | None) -> list[date]:
    from src.core.config import get_config as _gc

    days = _gc().get_bar_lookback_days(tf)
    return _iter_recent_trade_days(days, base or datetime.today().date())


def _map_bar(tf: str) -> BarSize:
    mapping = {
        "tick": "TICK",
        "ticks": "TICK",
        "1 sec": "SEC_1",
        "1 secs": "SEC_1",
        "30 sec": "SEC_30",
        "30 secs": "SEC_30",
        "1 min": "MIN_1",
        "5 mins": "MIN_5",
        "15 mins": "MIN_15",
        "30 mins": "MIN_30",
        "1 hour": "HOUR_1",
        "1 day": "DAY_1",
    }
    key = tf.lower()
    try:
        return BarSize(mapping.get(key, "MIN_1"))  # type: ignore[arg-type]
    except Exception:  # pragma: no cover
        return BarSize.MIN_1


@dataclass
class SymbolDownloadResult:
    symbol: str
    timeframe: str
    attempted: int = 0
    downloaded: int = 0
    skipped: int = 0
    failed: int = 0
    error: str | None = None


def download_symbol(
    dm: DataManager,
    h: HistoricalDataService,
    symbol: str,
    timeframes: Sequence[str],
    base_date: date | None,
    dry_run: bool,
) -> list[SymbolDownloadResult]:
    results: list[SymbolDownloadResult] = []
    for tf in timeframes:
        sd = SymbolDownloadResult(symbol=symbol, timeframe=tf)
        dates = _expand_timeframe_dates(tf, base_date)
        for d in dates:
            sd.attempted += 1
            date_str = d.strftime("%Y-%m-%d")
            if dm.data_exists(symbol, tf, date_str):
                sd.skipped += 1
                continue
            if dry_run:
                continue
            try:
                req = DownloadRequest(
                    symbol=symbol,
                    bar_size=_map_bar(tf),
                    what_to_show=DataType.TRADES,
                    end_date=d,
                )
                r = h.download_historical_data(None, req)
                if getattr(r, "data", None) is not None:
                    sd.downloaded += 1
                else:
                    sd.failed += 1
            except Exception as e:  # pragma: no cover
                sd.failed += 1
                sd.error = str(e)
        results.append(sd)
    return results


def collect_symbols(
    dm: DataManager, explicit: Iterable[str], use_warrior: bool
) -> list[str]:
    symbols: list[str] = []
    if use_warrior:
        wl = dm.warrior_list()  # type: ignore[attr-defined]
        if wl is not None:
            try:
                # Prefer Warrior CSV schema with 'Ticker' column
                cols = {str(c).strip().lower(): c for c in wl.columns}  # type: ignore[attr-defined]
                ticker_col = (
                    cols.get("ticker") or cols.get("symbol") or cols.get("stock")
                )
                if ticker_col:
                    for val in wl[ticker_col].dropna().astype(str):  # type: ignore[attr-defined]
                        s = val.strip().upper()
                        if s and s not in symbols:
                            symbols.append(s)
            except Exception:
                # Keep symbols empty if Warrior list not in expected CSV format
                pass
    symbols.extend([s for s in explicit if s and s not in symbols])
    return symbols


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Modern data updater")
    p.add_argument("--symbols", type=str, default="", help="Comma list of symbols")
    p.add_argument(
        "--timeframes",
        type=str,
        default="30 mins,1 min",
        help="Comma list e.g. '30 mins,1 min'",
    )
    p.add_argument("--date", type=str, default="", help="Base date YYYY-MM-DD")
    p.add_argument("--use-warrior-list", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--log-level", type=str, default="INFO")
    p.add_argument(
        "--describe", action="store_true", help="Show JSON tool description and exit"
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    logging.basicConfig(level=getattr(logging, args.log_level.upper(), logging.INFO))
    if args.describe:
        meta = {
            "name": "update_data",
            "description": "Bulk download historical data for symbols using DataManager + HistoricalDataService.",
            "inputs": [
                {
                    "name": "--symbols",
                    "type": "csv",
                    "description": "Comma separated symbols (optional when --use-warrior-list)",
                },
                {"name": "--timeframes", "type": "csv", "default": "30 mins,1 min"},
                {"name": "--date", "type": "YYYY-MM-DD", "optional": True},
                {"name": "--use-warrior-list", "type": "flag"},
                {"name": "--dry-run", "type": "flag"},
                {"name": "--log-level", "type": "str", "default": "INFO"},
            ],
            "outputs": {
                "files": "Historical parquet/ftr files stored under ML_BASE_PATH/IBDownloads"
            },
            "env_keys": [
                "ML_BASE_PATH",
                "IB_PAPER_PORT",
                "IB_LIVE_PORT",
                "DEFAULT_DATA_FORMAT",
            ],
            "examples": [
                "python -m src.tools.maintenance.update_data --symbols AAPL,MSFT",
                "python -m src.tools.maintenance.update_data --use-warrior-list --timeframes '30 mins,1 min,1 secs'",
            ],
            "version": 1,
        }
        print(json.dumps(meta, indent=2))
        return 0
    cfg = get_config()
    dm = DataManager(cfg)
    h = HistoricalDataService()
    symbols = collect_symbols(
        dm,
        [s.strip() for s in args.symbols.split(",") if s.strip()],
        args.use_warrior_list,
    )
    if not symbols:
        logger.warning("No symbols to process")
        return 0
    timeframes = [t.strip() for t in args.timeframes.split(",") if t.strip()]
    base_date = _coerce_date(args.date)
    started = perf_counter()
    total_attempt = total_downloaded = total_failed = total_skipped = 0
    for sym in symbols:
        res = download_symbol(dm, h, sym, timeframes, base_date, args.dry_run)
        for r in res:
            total_attempt += r.attempted
            total_downloaded += r.downloaded
            total_failed += r.failed
            total_skipped += r.skipped
    elapsed = perf_counter() - started
    logger.info(
        "Completed symbols=%d attempts=%d downloaded=%d skipped=%d failed=%d in %.2fs",
        len(symbols),
        total_attempt,
        total_downloaded,
        total_skipped,
        total_failed,
        elapsed,
    )
    return 0 if total_failed == 0 else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
