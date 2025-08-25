from __future__ import annotations
# mypy: ignore-errors
# ruff: noqa

from datetime import date
from pathlib import Path

import pandas as pd

from src.services.market_data.backfill_api import backfill_l2


def _fake_vendor_df():
    return pd.DataFrame(
        {
            "ts_event": [1, 2, 3],
            "action": ["A", "C", "D"],
            "side": ["B", "S", "B"],
            "price": [10.0, 10.1, 10.2],
            "size": [100, 200, 150],
            "level": [0, 1, 0],
            "exchange": ["Q", "Q", "Q"],
            "symbol": ["AAPL", "AAPL", "AAPL"],
        }
    )


def test_happy_path_write(monkeypatch, tmp_path: Path):
    from src.core import config as cfgmod
    from src.services.market_data import databento_l2_service as svc

    cfg = cfgmod.get_config()
    cfg.data_paths.base_path = tmp_path

    monkeypatch.setattr(
        svc.DataBentoL2Service, "is_available", staticmethod(lambda api_key: True)
    )
    monkeypatch.setattr(
        svc.DataBentoL2Service, "fetch_l2", lambda self, req: _fake_vendor_df()
    )

    res = backfill_l2("AAPL", date(2025, 7, 29))
    assert res["status"] == "written"
    assert res["rows"] == 3
    assert Path(res["path"]).exists()


def test_idempotent_skip_and_force(monkeypatch, tmp_path: Path):
    from src.core import config as cfgmod
    from src.services.market_data import databento_l2_service as svc

    cfg = cfgmod.get_config()
    cfg.data_paths.base_path = tmp_path

    monkeypatch.setattr(
        svc.DataBentoL2Service, "is_available", staticmethod(lambda api_key: True)
    )
    calls = {"n": 0}

    def _fetch(self, req):  # noqa: D401
        calls["n"] += 1
        return _fake_vendor_df()

    monkeypatch.setattr(svc.DataBentoL2Service, "fetch_l2", _fetch)

    first = backfill_l2("AAPL", date(2025, 7, 29))
    second = backfill_l2("AAPL", date(2025, 7, 29))
    forced = backfill_l2("AAPL", date(2025, 7, 29), force=True)
    assert first["status"] == "written"
    assert second["status"] == "skipped"
    assert forced["status"] == "written"
    # fetch invoked twice (first + force)
    assert calls["n"] == 2


def test_zero_rows(monkeypatch, tmp_path: Path):
    from src.core import config as cfgmod
    from src.services.market_data import databento_l2_service as svc

    cfg = cfgmod.get_config()
    cfg.data_paths.base_path = tmp_path

    monkeypatch.setattr(
        svc.DataBentoL2Service, "is_available", staticmethod(lambda api_key: True)
    )
    monkeypatch.setattr(
        svc.DataBentoL2Service,
        "fetch_l2",
        lambda self, req: pd.DataFrame(
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
        ),
    )
    res = backfill_l2("AAPL", date(2025, 7, 29))
    assert res["status"] == "skipped"
    assert res["zero_rows"] is True


def test_vendor_unavailable(monkeypatch, tmp_path: Path):
    from src.core import config as cfgmod
    from src.services.market_data import databento_l2_service as svc

    cfg = cfgmod.get_config()
    cfg.data_paths.base_path = tmp_path
    monkeypatch.setattr(
        svc.DataBentoL2Service, "is_available", staticmethod(lambda api_key: False)
    )
    res = backfill_l2("AAPL", date(2025, 7, 29))
    assert res["status"] == "error"
    assert "unavailable" in (res["error"] or "").lower()
