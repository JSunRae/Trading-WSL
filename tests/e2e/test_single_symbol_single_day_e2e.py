import json
import logging
import os
import subprocess
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import TypedDict

import pytest

from src.core.config import get_config
from src.lib.ib_async_wrapper import IBAsync
from src.services.market_data.artifact_check import (
    compute_needs,
    has_hourly,
    has_l2,
    has_seconds,
)
from src.services.market_data.backfill_api import backfill_l2
from src.services.market_data.warrior_backfill_orchestrator import find_warrior_tasks

pytestmark = pytest.mark.integration


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


@pytest.mark.requires_ib
@pytest.mark.slow
async def test_single_symbol_single_day_e2e():  # noqa: C901 - orchestration test, acceptable complexity
    """
    End-to-end smoke: pick one (symbol, day) from Warrior CSV and run:
      - IB hourly bars
      - IB seconds bars
      - DataBento L2 backfill
    Capture full log + list of artifact file paths written/used.

    Preconditions: IB Gateway/TWS reachable with API enabled; DataBento configured
    if L2 backfill is expected to write. The test is forgiving: it records
    statuses for each step and does not assert vendor availability.
    """
    cfg = get_config()

    # Pick the first Warrior (symbol, day) that is actually missing something
    # Setup dedicated e2e log file to capture detailed steps across modules
    logs_dir = cfg.data_paths.logs_path
    logs_dir.mkdir(parents=True, exist_ok=True)
    _ensure_e2e_logger(logs_dir)
    tasks = find_warrior_tasks(since_days=None, last=None)
    if not tasks:
        pytest.skip(
            "No Warrior tasks discovered; ensure WarriorTrading_Trades.csv exists"
        )

    symbol: str | None = None
    day: date | None = None
    for s, d in tasks:
        needs = compute_needs(s, d.strftime("%Y-%m-%d"))
        if needs.get("hourly") or needs.get("seconds") or needs.get("l2"):
            symbol, day = s, d
            break

    if symbol is None or day is None:
        pytest.skip(
            "All Warrior tasks already have hourly/seconds/L2 present; nothing to download"
        )
    day_str = day.strftime("%Y-%m-%d")

    # Where artifacts live
    hourly_path = cfg.get_data_file_path(
        "ib_download", symbol=symbol, timeframe="1 hour", date_str=day_str
    )
    sec_path = cfg.get_data_file_path(
        "ib_download", symbol=symbol, timeframe="1 sec", date_str=day_str
    )
    # L2 path base is computable but not needed directly because backfill_api decides suffix

    # Summarize needs before (and capture resolved paths)
    before = compute_needs(symbol, day_str)

    # Step 1/2: Connect to IB and fetch hourly + seconds
    ib = IBAsync()

    # Resolve IB host/port with env overrides and optional TWS mode
    ib_host = os.environ.get("IB_HOST", cfg.ib_connection.host)
    use_tws = os.environ.get("IB_USE_TWS", "0") in ("1", "true", "TRUE", "yes", "YES")
    ib_port = (
        cfg.ib_connection.paper_port
        if use_tws
        else cfg.ib_connection.gateway_paper_port
    )
    ib_port = int(os.environ.get("IB_PORT", ib_port))

    class IBEvent(TypedDict, total=False):
        event: str
        symbol: str
        end_datetime: str
        paths: dict[str, str]
        rows: int
        script: str
        start_cmd: str
        error: str

    async def connect_with_autostart(ib: IBAsync) -> bool:
        ok = await ib.connect(
            ib_host,
            ib_port,
            cfg.ib_connection.client_id,
        )
        if ok:
            return True
        # Auto-start attempt: run start_gateway.sh if present or generate it, then retry once
        try:
            script = Path("start_gateway.sh")
            if not script.exists():
                try:
                    from src.tools.setup.setup_ib_gateway import IBGatewaySetup

                    IBGatewaySetup().create_startup_script()
                except Exception:
                    pass
            if script.exists():
                ib_events.append(
                    {"event": "gateway_autostart_attempt", "script": str(script)}
                )
                subprocess.run(["bash", str(script)], check=False, timeout=60)
                time.sleep(3)
                ok = await ib.connect(ib_host, ib_port, cfg.ib_connection.client_id)
                return ok
            # Environment-provided start command (user-configurable)
            start_cmd = os.environ.get("IB_GATEWAY_START_CMD")
            if start_cmd:
                ib_events.append(
                    {"event": "gateway_autostart_env_cmd", "start_cmd": start_cmd}
                )
                try:
                    subprocess.Popen(start_cmd, shell=True)
                except Exception as e:
                    ib_events.append(
                        {"event": "gateway_autostart_env_cmd_error", "error": str(e)}
                    )
                time.sleep(5)
                ok = await ib.connect(ib_host, ib_port, cfg.ib_connection.client_id)
                return ok
        except subprocess.TimeoutExpired:
            ib_events.append({"event": "gateway_autostart_timeout"})
        except Exception as e:
            ib_events.append({"event": "gateway_autostart_error", "error": str(e)})
        return False

    ib_events: list[IBEvent] = []
    connected = await connect_with_autostart(ib)
    if not connected:
        pytest.skip("IB not reachable; Gateway/TWS is not running on configured port")
    try:
        contract = ib.create_stock_contract(symbol)
        # hourly for that day: duration 1 D, end at start of next day (IB format yyyymmdd HH:MM:SS)
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

        if before.get("hourly"):
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
        if before.get("seconds"):
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

    # Step 3: DataBento L2 backfill for the same (symbol, day)
    l2_result = (
        backfill_l2(symbol, day, force=True)
        if before.get("l2")
        else {"status": "skipped_preexisting"}
    )

    # Build a comprehensive run log
    run_log = {
        "symbol": symbol,
        "day": day_str,
        "ib": {
            "host": ib_host,
            "port": ib_port,
            "client_id": cfg.ib_connection.client_id,
            "hourly_path": str(hourly_path),
            "hourly_exists": hourly_path.exists(),
            "seconds_path": str(sec_path),
            "seconds_exists": sec_path.exists(),
            "events": ib_events,
        },
        "databento": {
            "enabled": bool(cfg.databento_api_key()),
            "result": l2_result,
        },
        "after_needs": {
            "hourly": has_hourly(symbol, day_str),
            "seconds": has_seconds(symbol, day_str),
            "l2": has_l2(symbol, day_str),
        },
        "paths": {
            "warrior_csv": str(cfg.get_data_file_path("warrior_trading_trades")),
            "level2_dir": str(
                cfg.data_paths.base_path / cfg.get_env("LEVEL2_DIRNAME") / symbol
            ),
            "ib_downloads_dir": str(
                cfg.data_paths.base_path / cfg.get_env("IB_DOWNLOADS_DIRNAME")
            ),
            "logs_dir": str(cfg.data_paths.logs_path),
        },
        "env": {
            "L2_BACKFILL_WINDOW_ET": cfg.get_env("L2_BACKFILL_WINDOW_ET"),
            "DATABENTO_DATASET": cfg.get_env("DATABENTO_DATASET"),
            "DATABENTO_SCHEMA": cfg.get_env("DATABENTO_SCHEMA"),
        },
        "before_needs": before,
    }

    # Emit to stdout for easy capture and to logs directory as json
    print(json.dumps(run_log, indent=2))
    out = cfg.data_paths.logs_path / f"e2e_single_{symbol}_{day_str}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(run_log, indent=2))

    # Minimal assertions: we at least connected to IB and attempted L2 when needed
    assert (not before.get("l2")) or ("status" in l2_result)
    # At least one of the artifacts should exist after run (don’t hard-fail when vendors unavailable)
    assert (
        hourly_path.exists()
        or sec_path.exists()
        or Path(l2_result.get("path", "")).exists()
    )
