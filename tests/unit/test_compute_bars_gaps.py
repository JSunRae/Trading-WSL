import json
from pathlib import Path
from typing import Any

from src.services.market_data.artifact_check import compute_bars_gaps


class DummyCfg:
    class DataPaths:
        def __init__(self, base: Path) -> None:
            self.base_path = base

    def __init__(self, base: Path) -> None:
        self.data_paths = DummyCfg.DataPaths(base)


def write_cov(base: Path, entries: list[dict[str, Any]]) -> None:
    base.mkdir(parents=True, exist_ok=True)
    (base / "bars_coverage_manifest.json").write_text(
        json.dumps({"schema_version": "bars_coverage.v1", "entries": entries}, indent=2)
    )


def test_compute_bars_gaps_full_and_missing(monkeypatch: Any, tmp_path: Path):
    # Build a minimal coverage manifest: AAPL has full seconds; MSFT has none
    entries = [
        {
            "symbol": "AAPL",
            "bar_size": "1 sec",
            "total": {"date_start": "2025-01-01", "date_end": "2025-01-01"},
            "days": [
                {
                    "date": "2025-01-01",
                    "time_start": "2025-01-01T09:00:00",
                    "time_end": "2025-01-01T11:00:00",
                    "path": str(tmp_path / "dummy.parquet"),
                    "filename": "dummy.parquet",
                    "rows": 7200,
                }
            ],
        }
    ]
    write_cov(tmp_path, entries)

    # Monkeypatch get_config to point base path to tmp_path
    import src.services.market_data.artifact_check as ac

    dummy = DummyCfg(tmp_path)
    monkeypatch.setattr(ac, "get_config", lambda: dummy, raising=True)

    # Full coverage for AAPL seconds: no gaps
    res = compute_bars_gaps("AAPL", "2025-01-01", "1 sec")
    assert res.get("basis") == "coverage"
    assert res.get("needed") is False
    assert res.get("gaps") == []

    # Missing coverage for MSFT seconds: full day window gap
    res2 = compute_bars_gaps("MSFT", "2025-01-01", "1 sec")
    assert res2.get("basis") == "coverage"
    assert res2.get("needed") is True
    assert res2.get("gaps") == [
        {
            "start": "2025-01-01T09:00:00",
            "end": "2025-01-01T11:00:00",
        }
    ]


def test_compute_bars_gaps_partial(monkeypatch: Any, tmp_path: Path):
    # Partial 1-min coverage 09:45–10:30; policy window is 09:30–11:00
    entries = [
        {
            "symbol": "AAPL",
            "bar_size": "1 min",
            "total": {"date_start": "2025-01-01", "date_end": "2025-01-01"},
            "days": [
                {
                    "date": "2025-01-01",
                    "time_start": "2025-01-01T09:45:00",
                    "time_end": "2025-01-01T10:30:00",
                    "path": str(tmp_path / "mins.parquet"),
                    "filename": "mins.parquet",
                    "rows": 46,
                }
            ],
        }
    ]
    write_cov(tmp_path, entries)

    import src.services.market_data.artifact_check as ac

    dummy = DummyCfg(tmp_path)
    monkeypatch.setattr(ac, "get_config", lambda: dummy, raising=True)

    res = compute_bars_gaps("AAPL", "2025-01-01", "1 min")
    assert res.get("basis") == "coverage"
    assert res.get("needed") is True
    # Expect two gaps: 09:30–09:45 and 10:30–11:00
    assert res.get("gaps") == [
        {"start": "2025-01-01T09:30:00", "end": "2025-01-01T09:45:00"},
        {"start": "2025-01-01T10:30:00", "end": "2025-01-01T11:00:00"},
    ]
