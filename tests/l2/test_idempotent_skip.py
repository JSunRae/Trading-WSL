import time
from pathlib import Path

import pandas as pd

from src.core.config import get_config
from src.services.market_data.l2_paths import atomic_write_parquet, with_source_suffix


def test_idempotent_skip_and_force(tmp_path: Path, monkeypatch):
    cfg = get_config()
    # Create a fake base path in tmp
    base = tmp_path / "Level2" / "AAPL"
    base.mkdir(parents=True, exist_ok=True)
    base_file = base / "2025-07-29_snapshots.parquet"
    # target with suffix
    target = with_source_suffix(base_file, "databento")
    df = pd.DataFrame(
        {
            "timestamp_ns": [1],
            "action": ["add"],
            "side": ["B"],
            "price": [1.0],
            "size": [1.0],
            "level": [0],
            "exchange": ["Q"],
            "symbol": ["AAPL"],
            "source": ["databento"],
        }
    )
    # First write
    atomic_write_parquet(df, target)
    mtime1 = target.stat().st_mtime
    time.sleep(0.01)
    # Write again without force path (simulate tool behaviour)
    atomic_write_parquet(df, target)  # idempotent (no overwrite)
    mtime2 = target.stat().st_mtime
    assert mtime2 == mtime1
    # Force overwrite simulation
    time.sleep(0.01)
    atomic_write_parquet(df, target, overwrite=True)
    mtime3 = target.stat().st_mtime
    assert mtime3 >= mtime2
