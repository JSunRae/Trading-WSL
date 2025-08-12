from __future__ import annotations

import pandas as pd

from src.core.dataframe_safety import SafeDataFrameAccessor


def test_safe_loc_get_set_on_empty_and_missing():
    df = pd.DataFrame(columns=["a", "b"]).set_index(pd.Index([], name="idx"))
    # get on empty returns default
    assert SafeDataFrameAccessor.safe_loc_get(df, "x", "a", default=42) == 42
    # set should create row and column
    tmp = pd.DataFrame(index=["r1"], columns=["a"])
    assert SafeDataFrameAccessor.safe_loc_set(tmp, "r1", "b", 1) is True
    assert "b" in tmp.columns
    # safe_check_value returns a truthy numpy.bool_ in some pandas versions; use bool()
    assert bool(SafeDataFrameAccessor.safe_check_value(tmp, "r1", "b", 1)) is True


def test_safe_fillna_row_mixed_types(recwarn):
    df = pd.DataFrame(
        {
            "name": ["n1", None],
            "qty": [1, None],
        }
    )
    # Ensure no warnings are raised during fill (FutureWarning previously)
    assert SafeDataFrameAccessor.safe_fillna_row(df, 1, fill_value="TBA") is True
    # pytest records warnings in recwarn fixture; ensure none captured
    assert len(recwarn) == 0
    assert df.loc[1, "name"] == "TBA"
    # qty column can be converted to string due to mixed dtypes; ensure filled
    assert pd.notna(df.loc[1, "qty"]) is True
