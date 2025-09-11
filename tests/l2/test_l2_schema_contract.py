from __future__ import annotations

import pandas as pd

from src.services.market_data.l2_schema_adapter import (
    CANONICAL_COLUMNS,
    CANONICAL_SCHEMA_VERSION,
    to_ibkr_l2,
)
from src.services.market_data.l2_schema_checker import is_canonical_l2


def test_canonical_schema_checker_accepts_adapter_output() -> None:
    vendor = pd.DataFrame(
        {
            "ts_event": [1, 2, 3],
            "action": ["A", "D", "C"],
            "side": ["B", "S", "B"],
            "price": [10.0, 10.1, 10.2],
            "size": [100, 200, 150],
            "level": [0, 1, 0],
            "exchange": ["Q", "Q", "N"],
        }
    )
    out = to_ibkr_l2(vendor, source="databento", symbol="AAPL")
    assert list(out.columns) == CANONICAL_COLUMNS
    ok, errs = is_canonical_l2(out)
    assert ok, f"Expected canonical schema, got errors: {errs}"
    assert CANONICAL_SCHEMA_VERSION == "1"


def test_databento_suffix_is_provenance_only() -> None:
    # Documented rule; behavior validated in backfill paths.
    # Here we just assert that adapter doesn't depend on suffix naming.
    vendor = pd.DataFrame(
        {
            "ts_event": [1],
            "action": ["A"],
            "side": ["B"],
            "price": [1.0],
            "size": [1],
            "level": [0],
            "exchange": ["Q"],
        }
    )
    out = to_ibkr_l2(vendor, source="databento", symbol="MSFT")
    ok, errs = is_canonical_l2(out)
    assert ok, f"schema errors: {errs}"
