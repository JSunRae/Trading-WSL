from __future__ import annotations

import io
import json
import sys
from contextlib import redirect_stdout
from datetime import date
from pathlib import Path
from threading import Lock
from typing import Any

import pandas as pd
import pytest

from src.services.market_data.warrior_backfill_orchestrator import run_warrior_backfill

# Simple helper vendor df


def _vendor_df():
    return pd.DataFrame(
        {
            "ts_event": [1],
            "action": ["A"],
            "side": ["B"],
            "price": [10.0],
            "size": [100],
            "level": [0],
            "exchange": ["Q"],
            "symbol": ["AAPL"],
        }
    )


def test_concurrency_respects_max_workers(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    from src.core import config as cfgmod
    from src.services.market_data import databento_l2_service as svc

    cfg = cfgmod.get_config()
    cfg.data_paths.base_path = tmp_path

    # Build tasks across potential month boundary safely using ordinal arithmetic
    start_day = date(2025, 7, 29)
    tasks = [("AAPL", date.fromordinal(start_day.toordinal() + i)) for i in range(6)]

    active = 0
    max_seen = 0
    lock = Lock()

    def fetch_l2(self: Any, req: Any):  # noqa: D401
        nonlocal active, max_seen
        with lock:
            active += 1
            max_seen = max(max_seen, active)
        try:
            return _vendor_df()
        finally:
            with lock:
                active -= 1

    monkeypatch.setattr(
        svc.DataBentoL2Service,
        "is_available",
        staticmethod(lambda api_key: True),  # type: ignore[arg-type]
    )
    monkeypatch.setattr(svc.DataBentoL2Service, "fetch_l2", fetch_l2)  # type: ignore[arg-type]

    summary = run_warrior_backfill(tasks, max_workers=3)
    assert summary["concurrency"] == 3
    # Allow slight race: observed concurrency should not exceed requested
    assert max_seen <= 3


def test_manifest_is_deterministic_with_concurrency(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    from src.core import config as cfgmod
    from src.services.market_data import databento_l2_service as svc

    cfg = cfgmod.get_config()
    cfg.data_paths.base_path = tmp_path

    tasks = [
        ("AAPL", date(2025, 7, 29)),
        ("MSFT", date(2025, 7, 30)),
        ("GOOG", date(2025, 7, 31)),
        ("TSLA", date(2025, 8, 1)),
    ]

    monkeypatch.setattr(
        svc.DataBentoL2Service,
        "is_available",
        staticmethod(lambda api_key: True),  # type: ignore[arg-type]
    )
    monkeypatch.setattr(
        svc.DataBentoL2Service,
        "fetch_l2",
        lambda self, req: _vendor_df(),  # type: ignore[arg-type]
    )

    run_warrior_backfill(tasks, max_workers=4)
    manifest = (
        (cfg.data_paths.base_path / "backfill_l2_manifest.jsonl")
        .read_text()
        .strip()
        .splitlines()
    )
    symbols_order = [json.loads(line)["symbol"] for line in manifest]
    assert symbols_order == [t[0] for t in tasks]


def test_summary_includes_concurrency_flag(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    from src.core import config as cfgmod
    from src.services.market_data import databento_l2_service as svc

    cfg = cfgmod.get_config()
    cfg.data_paths.base_path = tmp_path

    monkeypatch.setattr(
        svc.DataBentoL2Service,
        "is_available",
        staticmethod(lambda api_key: True),  # type: ignore[arg-type]
    )
    monkeypatch.setattr(
        svc.DataBentoL2Service,
        "fetch_l2",
        lambda self, req: _vendor_df(),  # type: ignore[arg-type]
    )

    mod = __import__("src.tools.auto_backfill_from_warrior", fromlist=["main"])
    sys.argv = [
        "auto_backfill_from_warrior",
        "--since",
        "0",
        "--max-workers",
        "3",
        "--max-tasks",
        "2",
    ]
    # Provide warrior list
    from src.services import data_management_service as dms

    dms.WarriorList = lambda mode: pd.DataFrame(
        {"SYMBOL": ["AAPL", "MSFT"], "DATE": ["2025-07-29", "2025-07-30"]}
    )

    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = mod.main()
    out = buf.getvalue()
    assert rc == 0
    assert "SUMMARY" in out and "concurrency=3" in out


def test_zero_row_and_error_paths_still_counted_under_concurrency(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    from src.core import config as cfgmod
    from src.services.market_data import databento_l2_service as svc

    cfg = cfgmod.get_config()
    cfg.data_paths.base_path = tmp_path

    tasks = [
        ("AAPL", date(2025, 7, 29)),  # write
        ("MSFT", date(2025, 7, 30)),  # zero row -> empty
        ("GOOG", date(2025, 7, 31)),  # error
    ]

    monkeypatch.setattr(
        svc.DataBentoL2Service, "is_available", staticmethod(lambda api_key: True)
    )

    def fetch_l2(self: Any, req: Any):  # noqa: D401
        sym = req.symbol if hasattr(req, "symbol") else "AAPL"
        if sym == "MSFT":
            return pd.DataFrame(
                columns=[
                    "ts_event",
                    "action",
                    "side",
                    "price",
                    "size",
                    "level",
                    "exchange",
                    "symbol",
                ]
            )  # zero rows
        if sym == "GOOG":
            raise RuntimeError("boom")
        return _vendor_df()

    monkeypatch.setattr(svc.DataBentoL2Service, "fetch_l2", fetch_l2)  # type: ignore[arg-type]

    summary = run_warrior_backfill(tasks, max_workers=3)
    assert summary["counts"]["WRITE"] == 1
    assert summary["counts"]["EMPTY"] == 1
    assert summary["counts"]["ERROR"] == 1
    assert summary["counts"]["SKIP"] == 0
