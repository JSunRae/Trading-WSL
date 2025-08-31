"""
Data recording and management modules for the trading project.

This package contains utilities for recording, storing, and managing
market data from Interactive Brokers, including pandas helpers
for Excel and CSV operations.
"""

from typing import Any

import pandas as pd

from .pandas_helpers import ensure_columns, to_records


# Create load_excel and save_excel functions as they're referenced in the task
def load_excel(file_path: str, **kwargs: Any) -> pd.DataFrame:
    """Load Excel file using pandas with safe defaults."""
    return pd.read_excel(file_path, engine="openpyxl", **kwargs)


def save_excel(df: pd.DataFrame, file_path: str, **kwargs: Any) -> None:
    """Save DataFrame to Excel with safe defaults."""
    df.to_excel(file_path, engine="openpyxl", index=False, **kwargs)


__all__ = [
    "load_excel",
    "save_excel",
    "to_records",
    "ensure_columns",
]
