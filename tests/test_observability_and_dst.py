from __future__ import annotations

import io
import json
import sys
from contextlib import redirect_stdout
from datetime import date

import pandas as pd
import pytest

from src.utils.timezones import et_session_window_utc


def test_auto_backfill_dry_run_emits_observability(monkeypatch: pytest.MonkeyPatch):
    # Patch warrior tasks discovery
    from src.services import data_management_service as dms

    dms.WarriorList = lambda mode: pd.DataFrame(
        {
            "SYMBOL": ["AAPL"],
            "DATE": ["2025-03-07"],
        }
    )  # type: ignore

    mod = __import__("src.tools.auto_backfill_from_warrior", fromlist=["main"])
    sys.argv = ["auto_backfill_from_warrior", "--dry-run", "--last", "1"]
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = mod.main()
    assert rc == 0
    out = json.loads(buf.getvalue())
    assert {"run_id", "stage_latency_ms", "requested_window_et"}.issubset(out)
    assert "discovery" in out["stage_latency_ms"]


def test_et_dst_conversion_across_change() -> None:
    # US 2025 DST starts on 2025-03-09; verify 09:30 converts differently on 03-07 vs 03-10.
    s1, _ = et_session_window_utc(date(2025, 3, 7), "09:30", "16:00")
    s2, _ = et_session_window_utc(date(2025, 3, 10), "09:30", "16:00")
    # 09:30 ET should map to different UTC wall-clock hours across DST change:
    # Before DST: 09:30 ET == 14:30 UTC; After DST: 09:30 ET == 13:30 UTC
    assert (s1.hour, s1.minute) == (14, 30)
    assert (s2.hour, s2.minute) == (13, 30)
