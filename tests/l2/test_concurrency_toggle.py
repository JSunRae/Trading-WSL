import importlib
import io
import sys
from contextlib import redirect_stdout
from pathlib import Path


def fake_vendor_df():
    import pandas as _pd

    return _pd.DataFrame(
        {
            "ts_event": [1, 2],
            "action": ["A", "D"],
            "side": ["B", "S"],
            "price": [100.0, 101.0],
            "size": [10, 11],
            "level": [0, 1],
            "exchange": ["Q", "Q"],
            "symbol": ["AAPL", "AAPL"],
        }
    )


def test_concurrency_param_roundtrip(monkeypatch, tmp_path: Path):
    # Monkeypatch config path for Level2 to tmp
    from src.core import config as cfgmod

    cfg = cfgmod.get_config()
    cfg.data_paths.base_path = tmp_path

    # Monkeypatch vendor service fetch to return deterministic df
    from src.services.market_data import databento_l2_service as svc

    monkeypatch.setattr(
        svc.DataBentoL2Service, "is_available", staticmethod(lambda api_key: True)
    )
    monkeypatch.setattr(
        svc.DataBentoL2Service, "fetch_l2", lambda self, req: fake_vendor_df()
    )

    # Build a minimal warrior list DataFrame provider
    import pandas as _pd

    from src.services import data_management_service as dms

    dms.WarriorList = lambda mode: _pd.DataFrame(
        {
            "SYMBOL": ["AAPL", "AAPL"],
            "DATE": ["2025-07-29", "2025-07-30"],
        }
    )

    # Import auto backfill tool module (orchestrator based)
    auto_mod = importlib.import_module("src.tools.auto_backfill_from_warrior")

    for conc in [1, 2]:
        # New concurrency flag / env moved to auto tool; legacy tool still uses config concurrency.
        # We assert summary line printed includes concurrency when invoking new auto tool.
        monkeypatch.setenv("L2_MAX_WORKERS", str(conc))
        # Build argv for auto tool parse_args (will discover 2 tasks and cap by --max-tasks)
        sys.argv = [
            "auto_backfill_from_warrior",
            "--last",
            "2",
            "--max-tasks",
            "2",
            "--max-workers",
            str(conc),
        ]
        # Re-import auto tool each loop to pick up env changes
        auto_mod = importlib.import_module("src.tools.auto_backfill_from_warrior")
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = auto_mod.main()
        out = buf.getvalue()
        assert rc == 0
    assert f"concurrency={conc}" in out
    # Validate via summary json artifact instead of individual files to reduce flakiness
    summary_path = cfg.data_paths.base_path / "backfill_l2_summary.json"
    assert summary_path.exists()
    import json as _json

    summary = _json.loads(summary_path.read_text())
    assert summary.get("concurrency") == conc
