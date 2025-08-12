"""Tests for lightweight data helper functions."""

import os
import tempfile

import pandas as pd

from src.api import ensure_columns, load_excel, save_excel


def test_excel_round_trip():
    df = pd.DataFrame({"a": [1, 2], "b": ["x", "y"]})
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "test.xlsx")
        save_excel(df, path)
        loaded = load_excel(path)
        assert list(loaded.columns) == ["a", "b"]
        assert len(loaded) == 2


def test_ensure_columns_missing():
    df = pd.DataFrame({"a": [1]})
    try:
        ensure_columns(df, ["a", "b"])
    except KeyError as e:
        assert "Missing columns" in str(e)
    else:  # pragma: no cover
        assert False, "Expected KeyError"
