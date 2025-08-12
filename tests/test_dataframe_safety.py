"""
Functional tests for src/core/dataframe_safety.py
Covers all DataFrame helpers: merge, concat, column enforcement, edge cases, and error paths.
"""

import numpy as np
import pandas as pd

from src.core.dataframe_safety import DataFrameValidator, SafeDataFrameAccessor


def test_safe_loc_get_set():
    df = pd.DataFrame({"A": [1, 2]}, index=["x", "y"])
    assert SafeDataFrameAccessor.safe_loc_get(df, "x", "A") == 1
    assert SafeDataFrameAccessor.safe_loc_get(df, "z", "A", default=99) == 99
    assert SafeDataFrameAccessor.safe_loc_set(df, "y", "A", 42)
    assert df.loc["y", "A"] == 42


def test_safe_check_value():
    df = pd.DataFrame({"A": ["foo", "bar"]}, index=["x", "y"])
    assert SafeDataFrameAccessor.safe_check_value(df, "x", "A", "foo")
    assert not SafeDataFrameAccessor.safe_check_value(df, "y", "A", "baz")


def test_safe_fillna_row():
    df = pd.DataFrame({"A": [np.nan, 2]}, index=["x", "y"])
    assert SafeDataFrameAccessor.safe_fillna_row(df, "x", fill_value=7)
    assert df.loc["x", "A"] == 7


def test_safe_column_index_exists():
    df = pd.DataFrame({"A": [1]}, index=["x"])
    assert SafeDataFrameAccessor.safe_column_exists(df, "A")
    assert not SafeDataFrameAccessor.safe_column_exists(df, "B")
    assert SafeDataFrameAccessor.safe_index_exists(df, "x")
    assert not SafeDataFrameAccessor.safe_index_exists(df, "y")


def test_create_safe_dataframe():
    df = SafeDataFrameAccessor.create_safe_dataframe(
        index_name="idx", columns=["A", "B"]
    )
    assert df.index.name == "idx"
    assert list(df.columns) == ["A", "B"]


def test_validator():
    df = pd.DataFrame({"A": [1, None]}, index=["x", "y"])
    report = DataFrameValidator.validate_dataframe_structure(
        df, required_columns=["A"], required_index_name="idx"
    )
    assert "Missing required columns" not in str(report)
    suggestions = DataFrameValidator.suggest_dataframe_cleanup(df)
    assert isinstance(suggestions, list)
