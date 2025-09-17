from __future__ import annotations

import io
import json
import sys
from contextlib import redirect_stdout
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from src.services.market_data.warrior_backfill_orchestrator import (
    find_warrior_tasks,
    run_warrior_backfill,
)


def _patch_warrior(monkeypatch: Any, df: pd.DataFrame) -> None:
    from src.services import data_management_service as dms

    dms.WarriorList = lambda mode: df  # type: ignore


def _fake_vendor_df():
    return pd.DataFrame(
        {
            "ts_event": [1, 2],
            "action": ["A", "D"],
            "side": ["B", "S"],
            "price": [10.0, 10.1],
            "size": [100, 200],
            "level": [0, 1],
            "exchange": ["Q", "Q"],
            "symbol": ["AAPL", "AAPL"],
        }
    )


def test_find_tasks_dedupes_and_filters(monkeypatch: pytest.MonkeyPatch):
    today = date.today()
    recent = today - timedelta(days=1)
    older = today - timedelta(days=5)
    df = pd.DataFrame(
        {
            "SYMBOL": ["AAPL", "AAPL", "MSFT"],
            "DATE": [
                recent.strftime("%Y-%m-%d"),
                recent.strftime("%Y-%m-%d"),
                older.strftime("%Y-%m-%d"),
            ],
        }
    )
    _patch_warrior(monkeypatch, df)
    # since_days=3 should drop the older date, last=1 should keep only the recent date
    tasks = find_warrior_tasks(since_days=3, last=1)
    assert all(d >= today - timedelta(days=3) for _, d in tasks)
    # Deduped symbols for recent date (AAPL once)
    assert any(sym == "AAPL" for sym, _ in tasks)
    # Older MSFT excluded by since_days filter
    assert not any(sym == "MSFT" and d == older for sym, d in tasks)


def test_run_backfill_writes_summary_and_manifest(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):  # type: ignore[unused-argument]
    from src.core import config as cfgmod
    from src.services.market_data import databento_l2_service as svc

    cfg = cfgmod.get_config()
    cfg.data_paths.base_path = tmp_path
    monkeypatch.setattr(
        svc.DataBentoL2Service,
        "is_available",
        staticmethod(lambda api_key: True),
    )
    monkeypatch.setattr(
        svc.DataBentoL2Service,
        "fetch_l2",
        lambda self, req: _fake_vendor_df(),
    )
    _patch_warrior(
        monkeypatch,
        pd.DataFrame({"SYMBOL": ["AAPL"], "DATE": ["2025-07-29"]}),
    )
    tasks = find_warrior_tasks()
    summary = run_warrior_backfill(tasks)
    assert summary["counts"]["WRITE"] == 1
    manifest = tmp_path / "backfill_l2_manifest.jsonl"
    assert manifest.exists()
    summary_json = tmp_path / "backfill_l2_summary.json"
    data = json.loads(summary_json.read_text())
    assert data["counts"]["WRITE"] == 1


def test_dry_run_outputs_preview(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    from src.core import config as cfgmod

    cfg = cfgmod.get_config()
    cfg.data_paths.base_path = tmp_path
    _patch_warrior(
        monkeypatch,
        pd.DataFrame(
            {
                "SYMBOL": ["AAPL", "AAPL"],
                "DATE": ["2025-07-29", "2025-07-30"],
            }
        ),
    )
    mod = __import__("src.tools.auto_backfill_from_warrior", fromlist=["main"])
    sys.argv = [
        "auto_backfill_from_warrior",
        "--last",
        "2",
        "--dry-run",
    ]
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = mod.main()
    out = buf.getvalue()
    assert rc == 0
    preview = json.loads(out)
    assert preview["task_count"] >= 1
    # first_tasks removed; ensure summary fields exist
    assert "symbol_count" in preview
    assert "date_range" in preview
    assert "completed_tasks_count" in preview


def test_strict_mode_nonzero_exit_on_errors(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    from src.core import config as cfgmod
    from src.services.market_data import databento_l2_service as svc

    cfg = cfgmod.get_config()
    cfg.data_paths.base_path = tmp_path
    _patch_warrior(
        monkeypatch,
        pd.DataFrame({"SYMBOL": ["AAPL"], "DATE": ["2025-07-29"]}),
    )
    monkeypatch.setattr(
        svc.DataBentoL2Service,
        "is_available",
        staticmethod(lambda api_key: True),
    )

    def boom(self: Any, req: Any):  # noqa: D401
        raise RuntimeError("boom")

    monkeypatch.setattr(svc.DataBentoL2Service, "fetch_l2", boom)
    mod = __import__("src.tools.auto_backfill_from_warrior", fromlist=["main"])
    sys.argv = [
        "auto_backfill_from_warrior",
        "--last",
        "1",
        "--strict",
    ]
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = mod.main()
    assert rc != 0
