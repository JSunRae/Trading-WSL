from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.services.market_data.l2_schema_checker import is_canonical_l2


def test_l2_fixture_schema_round_trip() -> None:
    p = Path(__file__).resolve().parents[2] / "tests" / "data" / "l2_fixture.parquet"
    df = pd.read_parquet(p)
    ok, problems = is_canonical_l2(df)
    assert ok, f"Fixture must satisfy canonical L2 schema: {problems}"
