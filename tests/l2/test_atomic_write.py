from pathlib import Path

import pandas as pd

from src.services.market_data.l2_paths import atomic_write_parquet


def test_atomic_write_success(tmp_path: Path):
    dest = tmp_path / "file.parquet"
    df = pd.DataFrame({"a": [1, 2, 3]})
    atomic_write_parquet(df, dest)
    assert dest.exists()
    assert not dest.with_suffix(dest.suffix + ".tmp").exists()


def test_atomic_write_failure(tmp_path: Path, monkeypatch):
    dest = tmp_path / "file2.parquet"
    df = pd.DataFrame({"a": [1]})

    def boom(*a, **k):  # pragma: no cover - simulate failure
        raise RuntimeError("fail")

    monkeypatch.setattr(type(df), "to_parquet", boom, raising=True)
    try:
        atomic_write_parquet(df, dest)
    except RuntimeError:
        pass
    else:  # pragma: no cover
        raise AssertionError("Expected failure")
    assert not dest.exists()
    assert not dest.with_suffix(dest.suffix + ".tmp").exists()
