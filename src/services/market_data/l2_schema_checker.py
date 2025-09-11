from __future__ import annotations

import pandas as pd

from .l2_schema_adapter import CANONICAL_COLUMNS


def is_canonical_l2(df: pd.DataFrame) -> tuple[bool, list[str]]:
    """Check canonical L2 schema: required columns and coarse dtypes."""
    errors: list[str] = []
    missing = [c for c in CANONICAL_COLUMNS if c not in df.columns]
    if missing:
        return False, [f"missing columns: {missing}"]
    checks = [
        (
            pd.api.types.is_integer_dtype(df["timestamp_ns"]),
            "timestamp_ns must be integer ns",
        ),
        (pd.api.types.is_string_dtype(df["action"]), "action must be string-like"),
        (pd.api.types.is_string_dtype(df["side"]), "side must be string-like"),
        (pd.api.types.is_float_dtype(df["price"]), "price must be float"),
        (pd.api.types.is_float_dtype(df["size"]), "size must be float"),
        (pd.api.types.is_integer_dtype(df["level"]), "level must be integer"),
        (pd.api.types.is_string_dtype(df["exchange"]), "exchange must be string-like"),
        (pd.api.types.is_string_dtype(df["symbol"]), "symbol must be string-like"),
        (pd.api.types.is_string_dtype(df["source"]), "source must be string-like"),
    ]
    for ok, msg in checks:
        if not ok:
            errors.append(msg)
    return (not errors), errors
