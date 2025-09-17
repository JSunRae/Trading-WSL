"""Automatic Warrior historical L2 backfill CLI.

Builds a task list from the Warrior list (unique (symbol, trading_day)) and
invokes the programmatic orchestrator. Designed for cron / CI usage where
idempotence and a single SUMMARY line are sufficient for guardrails.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from collections.abc import Callable
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

# Ultra‑early --describe guard (must run before heavy/optional imports)
from src.tools._cli_helpers import emit_describe_early


def tool_describe() -> dict[str, Any]:
    """Return standardized CLI metadata for this tool.

    Kept free of heavy imports; used by tests and by --describe.
    """
    return {
        "name": "auto_backfill_from_warrior",
        "description": (
            "Discover Warrior tasks (symbol, day) and run L2 backfill. "
            "Optionally prefetch IB bars (hourly/1-min/1-sec) and emit a compact coverage manifest."
        ),
        "dependencies": [],
        "inputs": {
            "--date": {"type": "str", "required": False},
            "--start": {"type": "str", "required": False},
            "--end": {"type": "str", "required": False},
            "--symbol": {"type": "str", "required": False},
            "--since": {"type": "int", "required": False},
            "--last": {"type": "int", "required": False},
            "--max-tasks": {"type": "int", "required": False},
            "--force": {"type": "flag"},
            "--strict": {"type": "flag"},
            "--dry-run": {"type": "flag"},
            "--verbose": {"type": "flag"},
            "--max-workers": {"type": "int", "required": False},
            "--fetch-bars": {"type": "flag"},
            "--no-fetch-bars": {"type": "flag"},
            "--force-bars": {"type": "flag"},
            "--ib-host": {"type": "str", "required": False},
            "--ib-port": {"type": "int", "required": False},
            "--use-tws": {"type": "flag"},
        },
        "outputs": {
            "stdout": {
                "type": "json",
                "description": (
                    "On success prints either a JSON preview (when --dry-run) or a SUMMARY line and may log progress."
                ),
            }
        },
        "examples": [
            {
                "description": "Preview next tasks (dry run)",
                "command": "python src/tools/auto_backfill_from_warrior.py --since 3 --dry-run",
            },
            {
                "description": "Run with 4 workers and prefetch bars",
                "command": "python src/tools/auto_backfill_from_warrior.py --since 3 --max-workers 4",
            },
            {
                "description": "Describe this tool (metadata)",
                "command": "python src/tools/auto_backfill_from_warrior.py --describe",
            },
        ],
    }


if emit_describe_early(
    tool_describe
):  # pragma: no cover - return immediately for --describe
    raise SystemExit(0)


# Heavy/optional imports placed after early-guard to keep --describe fast and resilient
from src.services.market_data.artifact_check import (  # noqa: E402
    compute_bars_gaps,
    compute_needs,
)
from src.services.market_data.warrior_backfill_orchestrator import (  # noqa: E402
    find_warrior_tasks,
    run_warrior_backfill,
)


def _fetch_ib_bars_for_task(  # noqa: C901
    symbol: str,
    day: date,
    *,
    force_bars: bool = False,
    ib_host: str | None = None,
    ib_port: int | None = None,
    use_tws: bool = False,
    progress_update: Callable[[str], None] | None = None,
    metrics: dict[str, float | int] | None = None,
) -> None:
    """Download hourly, 1-min, and 1-sec bars for a single (symbol, day) via IB.

    Best-effort: swallows exceptions to not block L2 backfill.
    Uses lazy imports to avoid hard deps during --describe.
    """
    log = logging.getLogger("auto_backfill.fetch_bars")

    class _DropSendingFilter(logging.Filter):
        def filter(self, record: logging.LogRecord) -> bool:  # type: ignore[override]
            try:
                msg = record.getMessage()
            except Exception:
                return True
            return "SENDING " not in msg

    try:
        logging.getLogger("ibapi.client").addFilter(_DropSendingFilter())
    except Exception:
        pass

    try:
        import asyncio as _asyncio  # type: ignore
        from datetime import datetime as _dt
        from datetime import time as _time_cls
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
        log.debug("Skipping IB bars fetch due to missing deps", exc_info=True)
        return

    cfg = _getcfg()
    ds = day.strftime("%Y-%m-%d")
    # Prefer fine-grained gap computation (coverage manifest) when available
    g_hour = compute_bars_gaps(symbol, ds, "1 hour")
    g_sec = compute_bars_gaps(symbol, ds, "1 sec")
    need_hourly = bool(g_hour.get("needed"))
    need_seconds = bool(g_sec.get("needed"))

    hourly_path = cfg.get_data_file_path(
        "ib_download", symbol=symbol, timeframe="1 hour", date_str=ds
    )
    sec_path = cfg.get_data_file_path(
        "ib_download", symbol=symbol, timeframe="1 sec", date_str=ds
    )
    min_path = cfg.get_data_file_path(
        "ib_download", symbol=symbol, timeframe="1 min", date_str=ds
    )
    g_min = compute_bars_gaps(symbol, ds, "1 min")
    need_minutes = bool(force_bars) or bool(g_min.get("needed"))
    if not force_bars and not (need_hourly or need_seconds or need_minutes):
        log.info("Bars up-to-date for %s %s; skipping fetch", symbol, ds)
        return

    async def _run() -> None:  # noqa: C901
        ib = _IBAsync()
        plan = _plan()
        if ib_host:
            plan["host"] = ib_host
        if ib_port is not None:
            chosen_port = int(ib_port)
            plan["candidates"] = [chosen_port] + [
                p for p in plan["candidates"] if p != chosen_port
            ]
        if use_tws and 7497 not in plan["candidates"]:
            plan["candidates"].insert(0, 7497)
        host = plan["host"]
        client_id = int(plan["client_id"])
        candidates = [int(p) for p in plan["candidates"]]

        async def _connect_cb(h: str, p: int, c: int) -> bool:
            return await ib.connect(h, p, c, fallback=False)

        log.info(
            "Connecting IB for bars %s %s host=%s candidates=%s",
            symbol,
            ds,
            plan["host"],
            plan["candidates"],
        )
        if progress_update:
            progress_update(f"{symbol} {ds}: connecting…")
        _t_conn0 = time.monotonic()
        ok, connected_port = await _try_connect(
            _connect_cb, host, candidates, client_id, autostart=True, events=[]
        )
        _conn_dur = time.monotonic() - _t_conn0
        if metrics is not None:
            metrics["connect_total_s"] = float(
                metrics.get("connect_total_s", 0.0)
            ) + float(_conn_dur)
            metrics["connect_count"] = int(metrics.get("connect_count", 0)) + 1
        if not ok:
            await ib.disconnect()
            log.warning("IB connect failed; cannot fetch bars for %s %s", symbol, ds)
            if progress_update:
                progress_update(f"{symbol} {ds}: connection failed")
            return
        try:
            contract = ib.create_stock_contract(symbol)
            end_ts_eod = _dt.combine(day + _td(days=1), _dt.min.time()).strftime(
                "%Y%m%d %H:%M:%S"
            )
            if progress_update:
                progress_update(
                    f"{symbol} {ds}: connected on {connected_port}; fetching…"
                )
            if force_bars or need_hourly:
                _t_h0 = time.monotonic()
                df_h = await ib.req_historical_data(
                    contract,
                    duration="365 D",
                    bar_size="1 hour",
                    end_datetime=end_ts_eod,
                    use_rth=True,
                )
                _h_dur = time.monotonic() - _t_h0
                if df_h is not None and not df_h.empty:
                    try:
                        start_day_0930 = _dt.combine(day, _time_cls(hour=9, minute=30))
                        end_day_1600 = _dt.combine(day, _time_cls(hour=16, minute=0))
                        df_hf = df_h.loc[
                            (df_h.index >= start_day_0930)
                            & (df_h.index <= end_day_1600)
                        ]
                    except Exception:
                        df_hf = df_h
                    hourly_path.parent.mkdir(parents=True, exist_ok=True)
                    df_hf.to_parquet(hourly_path)
                    try:
                        _append_bars_manifest(hourly_path, symbol, "1 hour", df_hf)
                    except Exception:
                        log.debug("bars manifest write failed (hour)", exc_info=True)
                    log.info(
                        "Saved hourly bars %s (RTH filtered to current day)",
                        hourly_path,
                    )
                    if progress_update:
                        progress_update(f"{symbol} {ds}: hourly ✓")
                else:
                    log.warning(
                        "No hourly bars returned for %s %s (port=%s)",
                        symbol,
                        ds,
                        str(connected_port),
                    )
                    if progress_update:
                        progress_update(f"{symbol} {ds}: hourly –")
                if metrics is not None:
                    metrics["hourly_total_s"] = float(
                        metrics.get("hourly_total_s", 0.0)
                    ) + float(_h_dur)
                    metrics["hourly_count"] = int(metrics.get("hourly_count", 0)) + 1
            try:
                need_minutes = bool(force_bars) or not min_path.exists()
                if need_minutes:
                    end_1100 = _dt.combine(day, _time_cls(hour=11, minute=0)).strftime(
                        "%Y%m%d %H:%M:%S"
                    )
                    _t_m0 = time.monotonic()
                    df_m = await ib.req_historical_data(
                        contract,
                        duration="2 D",
                        bar_size="1 min",
                        end_datetime=end_1100,
                        use_rth=True,
                    )
                    _m_dur = time.monotonic() - _t_m0
                    if df_m is not None and not df_m.empty:
                        try:
                            start_prev_0930 = _dt.combine(
                                day - _td(days=1), _time_cls(hour=9, minute=30)
                            )
                            end_cur_1100 = _dt.combine(
                                day, _time_cls(hour=11, minute=0)
                            )
                            df_mf = df_m.loc[
                                (df_m.index >= start_prev_0930)
                                & (df_m.index <= end_cur_1100)
                            ]
                            filtered_range = f"{start_prev_0930}→{end_cur_1100}"
                        except Exception:
                            df_mf = df_m
                            filtered_range = "(unfiltered)"
                        min_path.parent.mkdir(parents=True, exist_ok=True)
                        df_mf.to_parquet(min_path)
                        try:
                            _append_bars_manifest(min_path, symbol, "1 min", df_mf)
                        except Exception:
                            log.debug("bars manifest write failed (min)", exc_info=True)
                        log.info("Saved 1-min bars %s %s", min_path, filtered_range)
                        if progress_update:
                            progress_update(f"{symbol} {ds}: hourly ✓ minutes ✓")
                        if metrics is not None:
                            metrics["minutes_total_s"] = float(
                                metrics.get("minutes_total_s", 0.0)
                            ) + float(_m_dur)
                            metrics["minutes_count"] = (
                                int(metrics.get("minutes_count", 0)) + 1
                            )
                    else:
                        log.warning(
                            "No 1-min bars returned for %s %s (port=%s)",
                            symbol,
                            ds,
                            str(connected_port),
                        )
                        if progress_update:
                            progress_update(f"{symbol} {ds}: hourly ✓ minutes –")
            except Exception as _e_min:  # pragma: no cover - non-fatal
                log.warning("1-min bars fetch error for %s %s: %s", symbol, ds, _e_min)
            if force_bars or need_seconds:
                _t_s0 = time.monotonic()
                df_s = await ib.req_historical_data(
                    contract,
                    duration="1 D",
                    bar_size="1 sec",
                    end_datetime=end_ts_eod,
                    use_rth=False,
                )
                _s_dur = time.monotonic() - _t_s0
                if df_s is not None and not df_s.empty:
                    try:
                        start_0900 = _dt.combine(day, _time_cls(hour=9, minute=0))
                        end_1100_dt = _dt.combine(day, _time_cls(hour=11, minute=0))
                        df_sf = df_s.loc[
                            (df_s.index >= start_0900) & (df_s.index <= end_1100_dt)
                        ]
                    except Exception:
                        df_sf = df_s
                    sec_path.parent.mkdir(parents=True, exist_ok=True)
                    df_sf.to_parquet(sec_path)
                    try:
                        _append_bars_manifest(sec_path, symbol, "1 sec", df_sf)
                    except Exception:
                        log.debug("bars manifest write failed (sec)", exc_info=True)
                    log.info("Saved 1-sec bars %s (filtered 09:00–11:00)", sec_path)
                    if progress_update:
                        progress_update(f"{symbol} {ds}: hourly ✓ minutes ✓ seconds ✓")
                else:
                    log.warning(
                        "No seconds bars returned for %s %s (port=%s)",
                        symbol,
                        ds,
                        str(connected_port),
                    )
                    if progress_update:
                        progress_update(f"{symbol} {ds}: hourly ✓ minutes ✓ seconds –")
                if metrics is not None:
                    metrics["seconds_total_s"] = float(
                        metrics.get("seconds_total_s", 0.0)
                    ) + float(_s_dur)
                    metrics["seconds_count"] = int(metrics.get("seconds_count", 0)) + 1
        finally:
            await ib.disconnect()

    try:
        _asyncio.run(_run())
    except Exception as e:
        log.error("Bars fetch error for %s %s: %s", symbol, ds, e)
        return


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument(
        "--describe", action="store_true", help="Print tool metadata as JSON and exit"
    )
    # Optional explicit filters (parity with legacy CLI)
    p.add_argument("--date")
    p.add_argument("--start")
    p.add_argument("--end")
    p.add_argument("--symbol")
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
        dest="fetch_bars",
        action="store_true",
        default=True,
        help="Download IB hourly and 1-sec bars for all tasks before L2 backfill (default)",
    )
    p.add_argument(
        "--no-fetch-bars",
        dest="fetch_bars",
        action="store_false",
        help="Disable downloading IB hourly and 1-sec bars before L2 backfill",
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


def _append_bars_manifest(path: Path, symbol: str, bar_size: str, df: Any) -> None:
    """Append a JSONL entry describing a saved bars file for fast discovery.

    Fields include: file location, file name, symbol, bar size, time range, columns, rows.
    """
    from src.core.config import (
        get_config,  # local import to avoid heavy import at module load
    )

    cfg = get_config()
    manifest_path = cfg.data_paths.base_path / "bars_download_manifest.jsonl"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)

    # derive time coverage from index if possible
    time_start: str | None = None
    time_end: str | None = None
    try:
        import pandas as _pd  # local to avoid import weight on --describe

        if (
            hasattr(df, "index")
            and isinstance(df.index, _pd.DatetimeIndex)
            and len(df.index) > 0
        ):  # type: ignore[attr-defined]
            t_start = df.index[0].to_pydatetime()  # type: ignore[index]
            t_end = df.index[-1].to_pydatetime()  # type: ignore[index]
            time_start = t_start.isoformat()
            time_end = t_end.isoformat()
    except Exception:
        time_start = None
        time_end = None

    record = {
        "schema_version": "bars_manifest.v1",
        "written_at": datetime.now().isoformat(),
        "vendor": "IBKR",
        "file_format": "parquet",
        "symbol": symbol,
        "bar_size": bar_size,
        "path": str(path),
        "filename": path.name,
        "rows": int(len(df)) if hasattr(df, "__len__") else 0,
        "columns": list(df.columns) if hasattr(df, "columns") else [],
        "time_start": time_start,
        "time_end": time_end,
    }

    with manifest_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


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
    if getattr(args, "describe", False):
        # Allow describe via direct script execution as well
        sys.stdout.write(json.dumps(tool_describe(), indent=2) + "\n")
        sys.stdout.flush()
        return 0
    # Ensure readable defaults for logging
    if not logging.getLogger().handlers:
        logging.basicConfig(
            level=getattr(
                logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO
            ),
            format="%(levelname)s:%(name)s:%(message)s",
        )

    # Drop very noisy wire logs (keep requests/answers)
    class _DropSendingFilter(logging.Filter):
        def filter(self, record: logging.LogRecord) -> bool:  # type: ignore[override]
            try:
                return "SENDING " not in record.getMessage()
            except Exception:
                return True

    try:
        logging.getLogger("ibapi.client").addFilter(_DropSendingFilter())
    except Exception:
        pass

    run_id = datetime.now(UTC).strftime("%Y%m%d-%H%M%S-%f")
    t0 = datetime.now(UTC).timestamp()
    tasks = find_warrior_tasks(since_days=args.since, last=args.last)
    # Apply optional explicit filters (date range + symbol) with ad-hoc fallback
    from datetime import datetime as _dt_cls

    requested_dates: list[date] = []
    try:
        if args.date:
            requested_dates = [_dt_cls.strptime(str(args.date), "%Y-%m-%d").date()]
        elif args.start and args.end:
            s = _dt_cls.strptime(str(args.start), "%Y-%m-%d").date()
            e = _dt_cls.strptime(str(args.end), "%Y-%m-%d").date()
            if e < s:
                raise ValueError("--end before --start")
            cur = s
            while cur <= e:
                requested_dates.append(cur)
                cur = date.fromordinal(cur.toordinal() + 1)
    except Exception:
        # Invalid date inputs are ignored here to keep automation resilient; legacy CLI surfaced warnings.
        requested_dates = []

    if args.symbol:
        symu = str(args.symbol).upper()
        tasks = [(s, d) for (s, d) in tasks if s == symu]
    if requested_dates:
        keep = set(requested_dates)
        filtered = [(s, d) for (s, d) in tasks if d in keep]
        if filtered:
            tasks = filtered
        else:
            # Ad-hoc fallback: allow explicit date runs even if Warrior list empty
            fallback_symbol = str(args.symbol).upper() if args.symbol else "AAPL"
            tasks = [(fallback_symbol, d) for d in requested_dates]
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
    # Fetch IB bars (hourly + 1-sec) for each task prior to L2 (default: enabled)
    if args.fetch_bars and tasks:
        logging.getLogger("auto_backfill").info(
            "Fetching IB hourly and 1-sec bars for %d tasks (force_bars=%s)",
            len(tasks),
            bool(args.force_bars),
        )
        # Progress with ETA using per-segment pace (connect/hourly/seconds/skip)
        total = len(tasks)
        start_ts = time.time()
        # Running metrics updated as we go
        metrics: dict[str, float | int] = {
            "connect_total_s": 0.0,
            "connect_count": 0,
            "hourly_total_s": 0.0,
            "hourly_count": 0,
            "seconds_total_s": 0.0,
            "seconds_count": 0,
            "skip_total_s": 0.0,
            "skip_count": 0,
        }

        # Pre-compute needs per task to avoid repeated filesystem checks during ETA updates
        pre_needs: list[tuple[bool, bool]] = []
        for sym_i, day_i in tasks:
            ds_ = day_i.strftime("%Y-%m-%d")
            gh = compute_bars_gaps(sym_i, ds_, "1 hour")
            gs = compute_bars_gaps(sym_i, ds_, "1 sec")
            need_h_ = bool(gh.get("needed")) or bool(args.force_bars)
            need_s_ = bool(gs.get("needed")) or bool(args.force_bars)
            pre_needs.append((need_h_, need_s_))

        # Estimate remaining duration from measured averages and remaining mix
        def _avg(name: str) -> float:
            total_s = float(metrics.get(f"{name}_total_s", 0.0) or 0.0)
            count = int(metrics.get(f"{name}_count", 0) or 0)
            return total_s / count if count > 0 else 0.0

        def _estimate_remaining_seconds(cur_index: int) -> float:
            # Look ahead at remaining tasks and sum expected durations based on current averages
            remaining = 0.0
            for j in range(cur_index, total):
                need_h, need_s = pre_needs[j]
                if not (need_h or need_s):
                    remaining += max(_avg("skip"), 0.05)
                    continue
                # connection cost amortized: assume 1 connect per task (fast if already up)
                remaining += max(_avg("connect"), 0.2)
                if need_h:
                    remaining += max(_avg("hourly"), 1.0)
                if need_s:
                    remaining += max(_avg("seconds"), 2.0)
            return remaining

        def _fmt_eta(done: int, cur_index: int) -> str:
            elapsed = max(0.0, time.time() - start_ts)
            remain = _estimate_remaining_seconds(cur_index)
            end = time.localtime(start_ts + elapsed + remain)
            today = time.localtime().tm_yday
            end_str = time.strftime("%H:%M:%S", end)
            if end.tm_yday != today:
                end_str += time.strftime(" (%Y-%m-%d)", end)
            return f"ETA {end_str}"

        width = 30
        for idx, (sym, d) in enumerate(tasks, start=1):
            ds = d.strftime("%Y-%m-%d")

            def _render_line(
                done_count: int, status: str, *, _sym: str = sym, _ds: str = ds
            ) -> None:
                cur_index = min(done_count + 1, total)
                progress = cur_index / total
                bar = "#" * int(width * progress) + "-" * (
                    width - int(width * progress)
                )
                prefix = f"[{bar}] {cur_index}/{total} {int(100 * progress):3d}%"
                eta = (
                    _fmt_eta(done_count, cur_index)
                    if done_count > 0
                    else "ETA --:--:--"
                )
                line = f"\r{prefix} {eta}  current={_sym} {_ds} | {status:<24}"
                try:
                    sys.stdout.write(line)
                    sys.stdout.flush()
                except Exception:
                    pass

            # Initial render for this task
            _render_line(idx - 1, "starting")

            def _per_task_update(msg: str, *, _done: int = idx - 1) -> None:
                # Update inline status without creating new lines
                _render_line(_done, msg)

            try:
                t_task0 = time.time()
                # Use precomputed needs to categorize skip vs fetch for metric baselines
                need_h_now, need_s_now = pre_needs[idx - 1]
                if not (need_h_now or need_s_now):
                    # Simulate minimal work and record skip metric
                    time.sleep(0.01)  # keep things smooth; effectively zero-cost
                    metrics["skip_total_s"] = float(
                        metrics.get("skip_total_s", 0.0)
                    ) + float(time.time() - t_task0)
                    metrics["skip_count"] = int(metrics.get("skip_count", 0)) + 1
                _fetch_ib_bars_for_task(
                    sym,
                    d,
                    force_bars=bool(args.force_bars),
                    ib_host=args.ib_host,
                    ib_port=args.ib_port,
                    use_tws=bool(args.use_tws),
                    progress_update=_per_task_update,
                    metrics=metrics,
                )
            except Exception:
                # Keep going on errors; details already logged
                pass
            # Finalize line for this task as completed
            _render_line(idx, "completed")
        # Finish progress line
        sys.stdout.write("\n")
        sys.stdout.flush()
    elif not args.fetch_bars and tasks:
        # Explicit opt-out
        logging.getLogger("auto_backfill").info(
            "IB bar download disabled (--no-fetch-bars); proceeding with L2 only"
        )
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
    # Rebuild compact bars coverage manifest for incremental planning
    try:
        import importlib

        _get_cfg = importlib.import_module("src.core.config").get_config  # type: ignore[attr-defined]
        _build_cov = (
            importlib.import_module(
                "src.tools.analysis.build_bars_coverage"
            ).build_coverage  # type: ignore[attr-defined]
        )

        _cfg = _get_cfg()
        _base = _cfg.data_paths.base_path
        _manifest = _base / "bars_download_manifest.jsonl"
        _out = _base / "bars_coverage_manifest.json"
        _build_cov(_manifest, _out)
    except Exception:
        # Non-fatal: keep backfill result as the primary outcome
        pass
    if args.strict and summary["counts"].get("ERROR", 0) > 0:
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
