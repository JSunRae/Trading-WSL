from __future__ import annotations

from pathlib import Path
from typing import Any, Literal, TypedDict, cast

import pandas as pd
from pandas import DataFrame

# Common orientations
Records = list[dict[str, Any]]


# Example schema (add/adjust per table you use)
class OHLCRow(TypedDict, total=False):
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: float


class StockDataRow(TypedDict, total=False):
    Stock: str
    Date: str
    EarliestAvailBar: str
    NonExistant: str


class DownloadedRow(TypedDict, total=False):
    Stock: str
    Date: str


class FailedRow(TypedDict, total=False):
    Stock: str
    NonExistant: str
    EarliestAvailBar: str


def load_excel(
    path: str,
    *,
    sheet: str | int | None = None,
    dtype: dict[str, Any] | None = None,
    index_col: int | str | None = None,
) -> DataFrame:
    """Load Excel file with proper typing."""
    result = pd.read_excel(path, sheet_name=sheet, dtype=dtype, index_col=index_col)
    # Ensure we get a DataFrame, not a dict of DataFrames
    if isinstance(result, dict):
        # If multiple sheets, take the first one or raise error
        if len(result) == 1:
            return next(iter(result.values()))
        else:
            raise ValueError("Multiple sheets returned, specify a single sheet")
    return cast(DataFrame, result)


def save_excel(
    df: DataFrame, path: str, *, index: bool = False, sheet_name: str = "Sheet1"
) -> None:
    """Save DataFrame to Excel with proper typing."""
    df.to_excel(path, index=index, sheet_name=sheet_name)  # type: ignore[misc]


def to_records(df: DataFrame) -> Records:
    """Convert DataFrame to typed records list."""
    # Typed outer container; inner values remain Any unless schema-narrowed
    return df.to_dict("records")  # type: ignore[no-any-return]


def to_dict_orient(
    df: DataFrame,
    orient: Literal[
        "dict", "list", "series", "split", "tight", "records", "index"
    ] = "dict",
) -> Any:
    """Convert DataFrame to dict with specified orientation."""
    return df.to_dict(orient)  # type: ignore[no-any-return]


def ensure_columns(df: DataFrame, cols: list[str]) -> DataFrame:
    """Ensure DataFrame has required columns."""
    missing = [c for c in cols if c not in df.columns]
    if missing:
        raise KeyError(f"Missing columns: {missing}")
    return df


def read_csv_typed(
    path: str,
    *,
    dtype: dict[str, Any] | None = None,
    index_col: int | str | None = None,
) -> DataFrame:
    """Read CSV file with proper typing."""
    result = pd.read_csv(path, dtype=dtype, index_col=index_col)
    return cast(DataFrame, result)


def save_csv(df: DataFrame, path: str, *, index: bool = False) -> None:
    """Save DataFrame to CSV with proper typing."""
    df.to_csv(path, index=index)


def sort_values_typed(
    df: DataFrame, by: str | list[str], *, ascending: bool = True
) -> DataFrame:
    """Sort DataFrame values with proper typing."""
    result = df.sort_values(by, ascending=ascending, inplace=False)
    return cast(DataFrame, result)


def sort_index_typed(df: DataFrame, *, ascending: bool = True) -> DataFrame:
    """Sort DataFrame index with proper typing."""
    result = df.sort_index(ascending=ascending, inplace=False)
    return cast(DataFrame, result)


def fillna_typed(df: DataFrame, value: Any = "TBA") -> DataFrame:
    """Fill NaN values with proper typing."""
    result = df.fillna(value, inplace=False)
    return cast(DataFrame, result)


def save_excel_for_review(df: DataFrame, str_name: str = "") -> str:
    """
    Save DataFrame to Excel for review/debugging purposes.

    Replaces legacy SaveExcel_ForReview from the old monolith.
    Handles timezone conversion and generates unique filenames.

    Args:
        df: DataFrame to save
        str_name: Optional name suffix for the file

    Returns:
        str: Path to the saved file
    """

    # Set default name if not provided
    if str_name == "":
        str_name = "For Review"

    # Get base path from config, with fallback
    try:
        from ..core.config import get_config

        # Use configured ML base path directly (it already points to the ML root)
        base = get_config().data_paths.base_path
    except Exception:
        # Last-resort fallback mirrors default for ML_BASE_PATH
        base = Path.home() / "Machine Learning"

    base.mkdir(parents=True, exist_ok=True)

    # Generate unique filename
    count = 1
    path = base / f"Temp-{str_name}.xlsx"
    while path.exists():
        count += 1
        path = base / f"Temp-{str_name}-{count}.xlsx"

    # Copy DataFrame to avoid modifying original
    df_copy = df.copy()

    # Handle timezone conversion for datetime columns
    for col in df_copy.columns:
        if "datetime64[ns," in df_copy[col].dtype.name:
            # Check if timezone info exists (comma indicates timezone)
            if df_copy[col].dtype.tz is not None:
                df_copy[col] = df_copy[col].dt.tz_convert("America/New_York")
                df_copy[col] = df_copy[col].dt.tz_localize(None)

    # Save to Excel
    df_copy.to_excel(path, sheet_name="Sheet1", index=False, engine="openpyxl")

    return str(path)
