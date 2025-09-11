from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.services.market_data.l2_schema_adapter import CANONICAL_COLUMNS, to_ibkr_l2
from src.services.market_data.l2_schema_checker import is_canonical_l2


def test_canonical_l2_parquet_round_trip(tmp_path: Path) -> None:
    # Construct a tiny vendor-like frame
    vendor = pd.DataFrame(
        {
            "ts_event": ["2025-07-30T13:35:00.000000Z", "2025-07-30T13:35:00.100000Z"],
            "action": ["A", "C"],
            "side": ["BID", "ASK"],
            "price": [123.45, 123.46],
            "size": [100, 200],
            "level": [0, 1],
            "exchange": ["XNAS", "XNAS"],
        }
    )

    # Adapt to canonical schema
    df = to_ibkr_l2(vendor, source="databento", symbol="AAPL")
    assert list(df.columns) == CANONICAL_COLUMNS
    ok, errs = is_canonical_l2(df)
    assert ok, f"schema check failed: {errs}"

    # Write parquet and read back to ensure dtypes survive
    p = tmp_path / "l2_piece.parquet"
    df.to_parquet(p)
    back = pd.read_parquet(p)
    assert list(back.columns) == CANONICAL_COLUMNS
    ok2, errs2 = is_canonical_l2(back)
    assert ok2, f"round-trip schema check failed: {errs2}"
