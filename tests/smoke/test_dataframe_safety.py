"""
Smoke test for dataframe_safety.py
Tests instantiation and public methods of SafeDataFrameAccessor and DataFrameValidator.
"""

from src.core.dataframe_safety import DataFrameValidator, SafeDataFrameAccessor


def test_smoke_dataframe_safety():
    # SafeDataFrameAccessor static methods
    assert callable(SafeDataFrameAccessor.safe_loc_get)
    assert callable(SafeDataFrameAccessor.safe_loc_set)
    assert callable(SafeDataFrameAccessor.safe_check_value)
    assert callable(SafeDataFrameAccessor.safe_fillna_row)
    assert callable(SafeDataFrameAccessor.safe_read_excel)
    assert callable(SafeDataFrameAccessor.safe_to_excel)
    assert callable(SafeDataFrameAccessor.safe_column_exists)
    assert callable(SafeDataFrameAccessor.safe_index_exists)
    assert callable(SafeDataFrameAccessor.create_safe_dataframe)
    # DataFrameValidator static methods
    assert callable(DataFrameValidator.validate_dataframe_structure)
    assert callable(DataFrameValidator.suggest_dataframe_cleanup)
