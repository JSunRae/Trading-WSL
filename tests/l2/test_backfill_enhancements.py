from __future__ import annotations
# mypy: ignore-errors
# ruff: noqa
# pyright: reportUnknownParameterType=false, reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false

import importlib
import io
import json
import sys
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any

import pandas as pd

from src.services.market_data.l2_schema_adapter import CANONICAL_COLUMNS, to_ibkr_l2


def _fake_vendor_df_empty():
    return pd.DataFrame(
        {
            "ts_event": [],
            "action": [],
            "side": [],
            "price": [],
            "size": [],
            "level": [],
            "exchange": [],
            "symbol": [],
        }
    )


def _fake_vendor_df():
    return pd.DataFrame(
        {
            "ts_event": [1, 2],
            "action": ["A", "D"],
            "side": ["B", "S"],
            "price": [10.0, 10.5],
            "size": [100, 200],
            "level": [0, 1],
            "exchange": ["Q", "Q"],
            "symbol": ["AAPL", "AAPL"],
        }
    )


def _patch_warrior(monkeypatch: Any):  # type: ignore[unused-argument]
    from src.services import data_management_service as dms

    dms.WarriorList = lambda mode: pd.DataFrame(  # type: ignore
        {"SYMBOL": ["AAPL"], "DATE": ["2025-07-29"]}
    )


def test_zero_row_handling_and_manifest(monkeypatch: Any, tmp_path: Path):  # type: ignore[unused-argument]
    # Patch config data path
    from src.core import config as cfgmod

    cfg = cfgmod.get_config()
    cfg.data_paths.base_path = tmp_path

    # Patch vendor availability & fetch (empty -> EMPTY status)
    from src.services.market_data import databento_l2_service as svc

    monkeypatch.setenv("L2_BACKFILL_CONCURRENCY", "1")
    monkeypatch.setattr(
        svc.DataBentoL2Service,
        "is_available",
        staticmethod(lambda api_key: True),  # type: ignore[arg-type]
    )
    monkeypatch.setattr(
        svc.DataBentoL2Service,
        "fetch_l2",
        lambda self, req: _fake_vendor_df_empty(),  # type: ignore[override]
    )

    _patch_warrior(monkeypatch)
    mod = importlib.import_module("src.tools.auto_backfill_from_warrior")
    sys.argv = [
        "auto_backfill_from_warrior",
        "--date",
        "2025-07-29",
        "--max-tasks",
        "1",
        "--no-fetch-bars",
    ]
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = mod.main()
    assert rc == 0
    # auto cli does not emit per-task EMPTY lines; verify manifest and summary instead
    manifest = tmp_path / "backfill_l2_manifest.jsonl"
    assert manifest.exists()
    lines = manifest.read_text().strip().splitlines()
    assert len(lines) == 1
    rec = json.loads(lines[0])
    assert rec["status"] == "EMPTY"
    summary_path = tmp_path / "backfill_l2_summary.json"
    assert summary_path.exists()
    summary = json.loads(summary_path.read_text())
    assert summary["counts"]["EMPTY"] == 1
    assert [tuple(z) for z in summary["zero_row_tasks"]] == [("AAPL", "2025-07-29")]


def test_strict_mode_vendor_unavailable(monkeypatch: Any, tmp_path: Path):  # type: ignore[unused-argument]
    from src.core import config as cfgmod

    cfg = cfgmod.get_config()
    cfg.data_paths.base_path = tmp_path

    _patch_warrior(monkeypatch)
    from src.services.market_data import databento_l2_service as svc

    monkeypatch.setattr(
        svc.DataBentoL2Service,
        "is_available",
        staticmethod(lambda api_key: False),  # type: ignore[arg-type]
    )
    mod = importlib.import_module("src.tools.auto_backfill_from_warrior")
    sys.argv = [
        "auto_backfill_from_warrior",
        "--date",
        "2025-07-29",
        "--strict",
        "--no-fetch-bars",
    ]
    with redirect_stdout(io.StringIO()):
        rc = mod.main()
    assert rc != 0


def test_summary_shape_and_last_filter(monkeypatch: Any, tmp_path: Path):  # type: ignore[unused-argument]
    from src.core import config as cfgmod

    cfg = cfgmod.get_config()
    cfg.data_paths.base_path = tmp_path

    # Provide 3 dates, keep last 2
    from src.services import data_management_service as dms

    dms.WarriorList = lambda mode: pd.DataFrame(  # type: ignore
        {
            "SYMBOL": ["AAPL", "AAPL", "AAPL"],
            "DATE": ["2025-07-27", "2025-07-28", "2025-07-29"],
        }
    )
    from src.services.market_data import databento_l2_service as svc

    monkeypatch.setattr(
        svc.DataBentoL2Service,
        "is_available",
        staticmethod(lambda api_key: True),  # type: ignore[arg-type]
    )
    monkeypatch.setattr(
        svc.DataBentoL2Service,
        "fetch_l2",
        lambda self, req: _fake_vendor_df(),  # type: ignore[override]
    )
    mod = importlib.import_module("src.tools.auto_backfill_from_warrior")
    sys.argv = [
        "auto_backfill_from_warrior",
        "--last",
        "2",
        "--since",
        "365",  # auto CLI uses days; keep sufficiently large for test
        "--no-fetch-bars",
    ]
    with redirect_stdout(io.StringIO()):
        rc = mod.main()
    assert rc == 0
    summary_path = tmp_path / "backfill_l2_summary.json"
    summary = json.loads(summary_path.read_text())
    assert summary["counts"]["WRITE"] == 2  # only last 2 dates processed
    assert summary["total_tasks"] >= 2


def test_retry_stop(monkeypatch: Any, tmp_path: Path):  # type: ignore[unused-argument]
    """Validate vendor fetch retries max 3 then surfaces ERROR without crash."""
    from src.core import config as cfgmod

    cfg = cfgmod.get_config()
    cfg.data_paths.base_path = tmp_path
    _patch_warrior(monkeypatch)
    from src.services.market_data import databento_l2_service as svc

    attempts = {"n": 0}

    class FakeHistorical:  # type: ignore[too-many-ancestors]
        def __init__(self, api_key: str | None = None) -> None:  # noqa: D401
            self.api_key = api_key

        class timeseries:  # noqa: D401
            @staticmethod
            def get_range(**kwargs: object) -> None:  # noqa: D401
                attempts["n"] += 1
                raise RuntimeError("boom")

    monkeypatch.setattr(svc, "Historical", FakeHistorical)
    monkeypatch.setattr(
        svc.DataBentoL2Service,
        "is_available",
        staticmethod(lambda api_key: True),  # type: ignore[arg-type]
    )
    mod = importlib.import_module("src.tools.auto_backfill_from_warrior")
    sys.argv = [
        "auto_backfill_from_warrior",
        "--date",
        "2025-07-29",
        "--no-fetch-bars",
    ]
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = mod.main()
    assert rc == 0
    assert attempts["n"] == 3  # 3 retry attempts
    # auto cli surfaces errors via summary; ensure manifest/summary reflect error
    summary_path = tmp_path / "backfill_l2_summary.json"
    summary = json.loads(summary_path.read_text())
    assert (
        summary["counts"].get("ERROR", 0) >= 1
        or summary["counts"].get("UNAVAIL", 0) >= 1
    )


def test_contract_schema_parity(monkeypatch: Any, tmp_path: Path):  # type: ignore[unused-argument]
    # Build a reference IBKR live-like file (synthetic)
    live_df = pd.DataFrame(
        {
            "timestamp_ns": pd.Series([1], dtype="int64"),
            "action": pd.Series(["add"], dtype="string"),
            "side": pd.Series(["B"], dtype="string"),
            "price": pd.Series([10.0], dtype="float64"),
            "size": pd.Series([1.0], dtype="float64"),
            "level": pd.Series([0], dtype="int16"),
            "exchange": pd.Series(["Q"], dtype="string"),
            "symbol": pd.Series(["AAPL"], dtype="string"),
            "source": pd.Series(["ibkr"], dtype="string"),
        }
    )
    ref_path = tmp_path / "ref_live.parquet"
    live_df.to_parquet(ref_path)

    vendor_df = _fake_vendor_df()
    ib_df = to_ibkr_l2(vendor_df, source="databento", symbol="AAPL")
    backfill_path = tmp_path / "backfill.parquet"
    ib_df.to_parquet(backfill_path)

    r1 = pd.read_parquet(ref_path)
    r2 = pd.read_parquet(backfill_path)
    assert list(r1.columns) == list(r2.columns) == CANONICAL_COLUMNS
    # Normalize object dtypes to string for parity (some parquet writers may coerce)
    norm1 = ["string" if str(t) == "object" else str(t) for t in r1.dtypes]
    norm2 = ["string" if str(t) == "object" else str(t) for t in r2.dtypes]
    assert norm1 == norm2
