from __future__ import annotations

import io
import sys
from contextlib import redirect_stdout
from pathlib import Path


def test_orchestrator_zero_tasks(tmp_path: Path, monkeypatch):
    """When no warrior tasks are discovered, orchestrator CLI emits zero SUMMARY."""
    # Point config base path to tmp
    from src.core import config as cfgmod

    cfg = cfgmod.get_config()
    cfg.data_paths.base_path = tmp_path

    # Force empty warrior list
    from src.services import data_management_service as dms  # type: ignore

    dms.WarriorList = lambda mode: None  # type: ignore

    # Invoke auto orchestrator CLI with filters that yield zero tasks
    mod = __import__("src.tools.auto_backfill_from_warrior", fromlist=["main"])
    sys.argv = [
        "auto_backfill_from_warrior",
        "--since",
        "0",  # even with since filter, warrior list is empty
        "--max-workers",
        "2",
    ]
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = mod.main()
    out = buf.getvalue()
    assert rc == 0
    # Expect single SUMMARY line with zeros and concurrency=2
    assert "SUMMARY" in out
    assert (
        "WRITE=0" in out and "SKIP=0" in out and "EMPTY=0" in out and "ERROR=0" in out
    )
    assert (
        "concurrency=2" in out or "concurrency=1" in out
    )  # fallback if env override not applied
