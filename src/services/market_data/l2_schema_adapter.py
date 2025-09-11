"""Adapt vendor L2 (DataBento) to internal IBKR-compatible schema.

Canonical schema order:
["timestamp_ns","action","side","price","size","level","exchange","symbol","source"]
"""

from __future__ import annotations

from typing import Literal

import numpy as np
import pandas as pd

CANONICAL_SCHEMA_VERSION = "1"

CANONICAL_COLUMNS = [
    "timestamp_ns",
    "action",
    "side",
    "price",
    "size",
    "level",
    "exchange",
    "symbol",
    "source",
]


def to_ibkr_l2(
    df_vendor: pd.DataFrame, *, source: Literal["databento"], symbol: str
) -> pd.DataFrame:
    df = df_vendor.copy()

    # Timestamp conversion -> int64 ns
    ts_col = df.get("ts_event", pd.Series([0] * len(df)))
    try:
        ts_parsed = pd.to_datetime(ts_col, utc=True, errors="coerce")
        # astype('int64') works for tz-aware pandas datetime64[ns, tz]
        ts_ns = ts_parsed.astype("int64")
        # Replace NaT sentinel (-2**63) with 0
        min_i64 = np.iinfo(np.int64).min
        ts_ns = ts_ns.where(ts_ns != min_i64, 0).astype("int64")
    except Exception:
        ts_ns = pd.to_numeric(ts_col, errors="coerce").fillna(0).astype("int64")

    action_map: dict[object, str] = {
        "A": "add",
        "C": "change",
        "D": "delete",
        "U": "unknown",
        1: "add",
        2: "change",
        3: "delete",
    }
    action_raw = df.get("action", pd.Series(["U"] * len(df)))
    action_std = (
        action_raw.map(action_map).fillna(action_raw.astype(str)).astype("string")
    )

    side_raw = df.get("side", pd.Series(["U"] * len(df)))
    side_candidate = side_raw.astype(str).str.upper().str[0]
    side_std = side_candidate.where(side_candidate.isin(["B", "S"]), "U").astype(
        "string"
    )

    out = pd.DataFrame(
        {
            "timestamp_ns": ts_ns,
            "action": action_std,
            "side": side_std,
            "price": pd.to_numeric(
                df.get("price", pd.Series([0] * len(df))), errors="coerce"
            )
            .fillna(0)
            .astype("float64"),
            "size": pd.to_numeric(
                df.get("size", pd.Series([0] * len(df))), errors="coerce"
            )
            .fillna(0)
            .astype("float64"),
            "level": pd.to_numeric(
                df.get("level", pd.Series([0] * len(df))), errors="coerce"
            )
            .fillna(0)
            .astype("int16"),
            "exchange": df.get("exchange", pd.Series([""] * len(df))).astype("string"),
            "symbol": symbol,
            "source": source,
        }
    )
    return out[CANONICAL_COLUMNS]
