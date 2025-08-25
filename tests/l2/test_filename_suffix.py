from pathlib import Path

from src.services.market_data.l2_paths import with_source_suffix


def test_with_source_suffix_basic():
    base = Path("/tmp/2025-07-29_snapshots.parquet")
    out = with_source_suffix(base, "databento")
    assert out.name == "2025-07-29_snapshots_databento.parquet"
