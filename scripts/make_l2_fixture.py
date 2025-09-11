#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.services.market_data.l2_schema_adapter import CANONICAL_COLUMNS


def main() -> int:
    # Construct a tiny canonical L2 frame with 2 rows
    df = pd.DataFrame(
        {
            "timestamp_ns": [0, 1],
            "action": ["add", "delete"],
            "side": ["B", "S"],
            "price": [100.0, 101.5],
            "size": [10.0, 5.0],
            "level": [1, 1],
            "exchange": ["NQ", "NQ"],
            "symbol": ["TEST", "TEST"],
            "source": ["databento", "databento"],
        }
    )[CANONICAL_COLUMNS]
    out = Path(__file__).resolve().parents[1] / "tests" / "data" / "l2_fixture.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out, index=False)
    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
