"""Modern Warrior data update tool.

Replaces legacy ib_Warror_dl.py functionality with a clean CLI that
uses modern services only (DataManager, HistoricalDataService).

Modes:
  main           - iterate warrior list rows downloading multiple bar sizes
  recent         - 30 mins only latest day
  mark-downloaded- reconcile existing files into tracker
  trainlist      - produce warrior training list (1 secs + 1 min present)

Example:
  python -m src.tools.warrior_update --mode main --bar-sizes "30 mins,1 min" --start-row 0
"""

from __future__ import annotations

import argparse
import json
import logging
from collections.abc import Iterator
from datetime import date, datetime, timedelta
from time import perf_counter
from typing import Any

from src.core.config import get_config
from src.data.data_manager import DataManager
from src.services.historical_data_service import (
    BarSize,
    DataType,
    DownloadRequest,
    HistoricalDataService,
)

logger = logging.getLogger("warrior_update")


def _parse_bar_sizes(raw: str | None) -> list[str]:
    if not raw:
        return ["30 mins", "1 min"]
    return [s.strip() for s in raw.split(",") if s.strip()]


def _iter_warrior_rows(
    dm: DataManager, start_row: int = 0
) -> Iterator[tuple[int, Any, list[str]]]:  # noqa: ANN401
    wl: Any = dm.warrior_list()  # type: ignore[attr-defined]
    try:
        if wl is None or getattr(wl, "empty", True):
            return iter(())
    except Exception:  # pragma: no cover
        return iter(())
    for idx in range(start_row, len(wl)):
        try:
            row = wl.iloc[idx]
            raw = row.get("ROSS", "")  # type: ignore[attr-defined]
            if not raw:
                continue
            symbols = [s.strip() for s in str(raw).split(";") if s.strip()]
            yield idx, row.get("Date"), symbols  # type: ignore[attr-defined]
        except Exception:  # pragma: no cover
            continue


def _coerce_date(d: object) -> date:
    if isinstance(d, datetime):
        return d.date()
    if isinstance(d, date):
        return d
    try:
        return datetime.fromisoformat(str(d)[:10]).date()
    except Exception:
        return datetime.today().date()


def _download_symbol_day(
    h: HistoricalDataService, symbol: str, bar: str, end_dt: date
) -> bool:
    try:
        req = DownloadRequest(
            symbol=symbol,
            bar_size=BarSize(bar),
            what_to_show=DataType.TRADES,
            end_date=end_dt,
        )
        res = h.download_historical_data(None, req)
        return bool(getattr(res, "data", None) is not None)
    except Exception as e:  # pragma: no cover - best effort
        logger.warning("Download failed %s %s %s: %s", symbol, bar, end_dt, e)
        return False


def mode_main(
    dm: DataManager,
    h: HistoricalDataService,
    start_row: int,
    bar_sizes: list[str],
    only_symbol: str | None,
):
    t0 = perf_counter()
    total = 0
    for _row_idx, date_val, symbols in _iter_warrior_rows(dm, start_row):
        trade_date = _coerce_date(date_val)
        for sym in symbols:
            if only_symbol and sym != only_symbol:
                continue
            for bar in list(bar_sizes):
                # For 1 min replicate legacy multi-day (5 days) else single day
                days = 5 if bar == "1 min" else 1
                for d in range(days):
                    end_dt = trade_date + timedelta(days=d)
                    if dm.data_exists(sym, bar, end_dt.strftime("%Y-%m-%d")):
                        continue
                    _download_symbol_day(h, sym, bar, end_dt)
                    total += 1
    logger.info("Mode main complete in %.2fs; %d requests", perf_counter() - t0, total)


def mode_recent(dm: DataManager, h: HistoricalDataService, start_row: int):
    # 30 mins only for yesterday
    yday = datetime.today().date() - timedelta(days=1)
    count = 0
    for _, _, symbols in _iter_warrior_rows(dm, start_row):
        for sym in symbols:
            if dm.data_exists(sym, "30 mins", yday.strftime("%Y-%m-%d")):
                continue
            _download_symbol_day(h, sym, "30 mins", yday)
            count += 1
    logger.info("Mode recent complete; %d downloads", count)


def mode_mark_downloaded(dm: DataManager, start_row: int):
    # Reconcile existing files with tracker (best effort)
    wl: Any = dm.warrior_list()  # type: ignore[attr-defined]
    if wl is None:
        return
    reconciled = 0
    for idx in range(start_row, len(wl)):
        row = wl.iloc[idx]
        date_str = _coerce_date(row.get("Date")).strftime("%Y-%m-%d")
        symbols = [s.strip() for s in str(row.get("ROSS", "")).split(";") if s.strip()]
        for sym in symbols:
            for bar in ("30 mins", "1 min", "1 secs", "ticks"):
                if dm.data_exists(sym, bar, date_str):
                    reconciled += 1
    logger.info("Mark-downloaded scan complete; %d files present", reconciled)


def mode_trainlist(dm: DataManager, start_row: int):
    wl: Any = dm.warrior_list()  # type: ignore[attr-defined]
    if wl is None:
        logger.warning("No warrior list available")
        return
    train: list[dict[str, str]] = []
    for idx in range(start_row, len(wl)):
        row = wl.iloc[idx]
        date_str = _coerce_date(row.get("Date")).strftime("%Y-%m-%d")
        symbols = [s.strip() for s in str(row.get("ROSS", "")).split(";") if s.strip()]
        for sym in symbols:
            if dm.data_exists(sym, "1 secs", date_str) and dm.data_exists(
                sym, "1 min", date_str
            ):
                train.append({"Stock": sym, "DateStr": date_str})
    if train:
        dm.train_list_loadsave(mode="Save", kind="Warrior", records=train)
    logger.info("Trainlist build complete; %d entries", len(train))


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Modern Warrior data update tool")
    p.add_argument(
        "--mode",
        choices=["main", "recent", "mark-downloaded", "trainlist"],
        default="main",
    )
    p.add_argument("--start-row", type=int, default=0)
    p.add_argument("--only-stock", type=str, default=None)
    p.add_argument(
        "--bar-sizes",
        type=str,
        default=None,
        help="Comma separated list e.g. '30 mins,1 min'",
    )
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
            "name": "warrior_update",
            "summary": "Download recent historical data for Warrior Trading symbols across bar sizes.",
            "modes": {
                "main": "Iterate warrior list rows; 1 min (5 days) + other bars (1 day).",
                "recent": "30 mins only for yesterday for listed symbols.",
                "mark-downloaded": "Reconcile existing downloaded files with tracking (no downloads).",
                "trainlist": "Generate training list entries where 1 secs + 1 min exist for a date.",
            },
            "arguments": [
                {
                    "name": "--mode",
                    "choices": ["main", "recent", "mark-downloaded", "trainlist"],
                    "default": "main",
                },
                {"name": "--start-row", "type": "int", "default": 0},
                {"name": "--only-stock", "type": "str", "default": None},
                {"name": "--bar-sizes", "type": "str", "example": "30 mins,1 min"},
                {"name": "--log-level", "type": "str", "default": "INFO"},
            ],
            "env_keys": [
                "ML_BASE_PATH",
                "ML_BACKUP_PATH",
                "IB_HOST",
                "IB_PAPER_PORT",
                "IB_LIVE_PORT",
                "IB_GATEWAY_PAPER_PORT",
                "IB_GATEWAY_LIVE_PORT",
            ],
            "outputs": {
                "logs": "INFO level progress",
                "side_effects": "Downloaded parquet/ftr files into ML base path",
            },
            "version": 1,
        }
        print(json.dumps(meta, indent=2))
        return 0

    config = get_config()
    dm = DataManager(config)
    hservice = HistoricalDataService()

    if args.mode == "main":
        mode_main(
            dm,
            hservice,
            args.start_row,
            _parse_bar_sizes(args.bar_sizes),
            args.only_stock,
        )
    elif args.mode == "recent":
        mode_recent(dm, hservice, args.start_row)
    elif args.mode == "mark-downloaded":
        mode_mark_downloaded(dm, args.start_row)
    elif args.mode == "trainlist":
        mode_trainlist(dm, args.start_row)
    else:  # pragma: no cover
        logger.error("Unknown mode %s", args.mode)
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
