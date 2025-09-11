from __future__ import annotations

from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURES_DIR = REPO_ROOT / "contracts" / "fixtures"
PARQUET = FIXTURES_DIR / "l2_fixture.parquet"
CSV = FIXTURES_DIR / "l2_fixture.csv"


def _load_fixture() -> pd.DataFrame:
    if PARQUET.exists():
        try:
            return pd.read_parquet(PARQUET)
        except Exception:
            # Parquet engine not installed; fall back to CSV
            pass
    assert CSV.exists(), "Expected CSV fallback when parquet is missing"
    return pd.read_csv(CSV)


def test_l2_fixture_schema_columns_and_types() -> None:
    df = _load_fixture()
    required = [
        "ts_utc",
        "symbol",
        "price",
        "size",
        "side",
        "session_et",
    ]
    for col in required:
        assert col in df.columns, (
            f"Missing required column: {col} (have: {list(df.columns)})"
        )

    # Basic dtype checks
    assert pd.api.types.is_numeric_dtype(df["price"]), "price must be numeric"

    # size should be integer-like (allow int or nullable Int64)
    is_int = pd.api.types.is_integer_dtype(df["size"]) or str(
        df["size"].dtype
    ).lower() in {"int64", "int32", "int16", "Int64"}
    assert is_int, f"size must be integer-like (got {df['size'].dtype})"

    # side expected to be categorical-like of {BID, ASK} (case-insensitive)
    side_norm = df["side"].astype(str).str.upper()
    assert side_norm.isin(["BID", "ASK"]).all(), "side must be either BID or ASK"

    # session_et is a local time string like 09:30-16:00 ET; ensure non-empty
    assert df["session_et"].astype(str).str.len().gt(0).all(), (
        "session_et must be non-empty"
    )
