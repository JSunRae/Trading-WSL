"""
Data Utilities

This module contains utility functions for safe data access and manipulation,
extracted from the monolithic MasterPy_Trading.py file.
Provides safe DataFrame operations and data type handling.
"""

import numbers
from datetime import date, datetime
from typing import Any

import pandas as pd


def safe_date_to_string(date_obj: datetime | date | str | None) -> str:
    """Safely convert date object to string format"""
    if date_obj is None:
        return ""

    try:
        if isinstance(date_obj, str):
            return date_obj
        elif isinstance(date_obj, (datetime, date)):  # noqa: UP038
            return date_obj.strftime("%Y-%m-%d")
        else:
            return str(date_obj)
    except (ValueError, AttributeError) as e:
        print(f"Warning: Error converting date to string: {e}")
        return str(date_obj)


def safe_datetime_to_string(datetime_obj: datetime | date | str | None) -> str:
    """Safely convert datetime object to string format"""
    if datetime_obj is None:
        return ""

    try:
        if isinstance(datetime_obj, str):
            return datetime_obj
        elif isinstance(datetime_obj, datetime):
            return datetime_obj.strftime("%Y-%m-%d %H:%M:%S")
        elif isinstance(datetime_obj, date):
            return datetime_obj.strftime("%Y-%m-%d")
        else:
            return str(datetime_obj)
    except (ValueError, AttributeError) as e:
        print(f"Warning: Error converting datetime to string: {e}")
        return str(datetime_obj)


def safe_df_scalar_access(  # noqa: C901
    df: pd.DataFrame, row: int | str, col: int | str, default: Any = None
) -> Any:
    """Safely access scalar value from DataFrame"""
    try:
        if df.empty:
            return default

        # Handle different indexing methods
        if isinstance(row, int) and isinstance(col, int):
            if row < len(df) and col < len(df.columns):
                return df.iloc[row, col]
        elif isinstance(row, str) and isinstance(col, str):
            if row in df.index and col in df.columns:
                return df.loc[row, col]
        elif isinstance(row, int) and isinstance(col, str):
            if row < len(df) and col in df.columns:
                return df.iloc[row][col]
        elif isinstance(row, str) and isinstance(col, int):
            if row in df.index and col < len(df.columns):
                return df.loc[row].iloc[col]

        return default

    except (KeyError, IndexError, ValueError, AttributeError) as e:
        print(f"Warning: Error accessing DataFrame scalar [{row}, {col}]: {e}")
        return default


def safe_df_scalar_check(
    df: pd.DataFrame, row: int | str, col: int | str, check_value: Any
) -> bool:
    """Safely check if DataFrame scalar equals a value"""
    try:
        actual_value = safe_df_scalar_access(df, row, col)
        return actual_value == check_value
    except Exception as e:
        print(f"Warning: Error checking DataFrame scalar [{row}, {col}]: {e}")
        return False


def safe_series_access(series: pd.Series, index: int | str, default: Any = None) -> Any:
    """Safely access value from pandas Series"""
    try:
        if series.empty:
            return default

        if isinstance(index, int):
            if 0 <= index < len(series):
                return series.iloc[index]
        elif isinstance(index, str):
            if index in series.index:
                return series.loc[index]

        return default

    except (KeyError, IndexError, ValueError, AttributeError) as e:
        print(f"Warning: Error accessing Series value [{index}]: {e}")
        return default


def safe_numeric_conversion(value: Any, default: float = 0.0) -> float:
    """Safely convert value to numeric"""
    try:
        if pd.isna(value) or value is None:
            return default

        if isinstance(value, numbers.Real):
            return float(value)
        elif isinstance(value, str):
            # Handle common string representations
            cleaned = value.strip().replace(",", "").replace("$", "")
            if cleaned == "" or cleaned.lower() in ["na", "nan", "null", "none"]:
                return default
            return float(cleaned)
        else:
            return float(value)

    except (ValueError, TypeError, AttributeError) as e:
        print(f"Warning: Error converting to numeric [{value}]: {e}")
        return default


def safe_string_conversion(value: Any, default: str = "") -> str:
    """Safely convert value to string"""
    try:
        if pd.isna(value) or value is None:
            return default

        if isinstance(value, str):
            return value
        elif isinstance(value, (datetime, date)):  # noqa: UP038
            return safe_datetime_to_string(value)
        else:
            return str(value)

    except (ValueError, AttributeError) as e:
        print(f"Warning: Error converting to string [{value}]: {e}")
        return str(value) if value is not None else default


def safe_boolean_conversion(value: Any, default: bool = False) -> bool:
    """Safely convert value to boolean"""
    try:
        if pd.isna(value) or value is None:
            return default

        if isinstance(value, bool):
            return value
        elif isinstance(value, numbers.Real):
            return bool(value)
        elif isinstance(value, str):
            cleaned = value.strip().lower()
            if cleaned in ["true", "1", "yes", "y", "on"]:
                return True
            elif cleaned in ["false", "0", "no", "n", "off"]:
                return False
            else:
                return default
        else:
            return bool(value)

    except (ValueError, TypeError, AttributeError) as e:
        print(f"Warning: Error converting to boolean [{value}]: {e}")
        return default


def validate_dataframe_structure(
    df: pd.DataFrame, required_columns: list, min_rows: int = 0
) -> tuple[bool, list]:
    """Validate DataFrame has required structure"""
    issues = []

    if df.empty and min_rows > 0:
        issues.append("DataFrame is empty")

    if len(df) < min_rows:
        issues.append(f"DataFrame has {len(df)} rows, minimum required: {min_rows}")

    missing_columns = [col for col in required_columns if col not in df.columns]
    if missing_columns:
        issues.append(f"Missing required columns: {missing_columns}")

    return len(issues) == 0, issues


def clean_column_names(df: pd.DataFrame) -> pd.DataFrame:
    """Clean DataFrame column names"""
    cleaned_df = df.copy()

    # Remove leading/trailing whitespace
    cleaned_df.columns = cleaned_df.columns.str.strip()

    # Replace spaces with underscores
    cleaned_df.columns = cleaned_df.columns.str.replace(" ", "_")

    # Remove special characters
    cleaned_df.columns = cleaned_df.columns.str.replace(r"[^\w\s]", "", regex=True)

    # Convert to lowercase
    cleaned_df.columns = cleaned_df.columns.str.lower()

    return cleaned_df


def detect_and_convert_dtypes(df: pd.DataFrame) -> pd.DataFrame:
    """Automatically detect and convert appropriate data types"""
    converted_df = df.copy()

    for col in converted_df.columns:
        # Skip if column is already datetime
        if pd.api.types.is_datetime64_any_dtype(converted_df[col]):
            continue

        # Try to convert to datetime if it looks like dates
        if converted_df[col].dtype == "object":
            try:
                # Sample a few values to see if they look like dates
                sample = converted_df[col].dropna().head(5)
                if len(sample) > 0:
                    # Try parsing as datetime
                    pd.to_datetime(sample, errors="raise")
                    converted_df[col] = pd.to_datetime(
                        converted_df[col], errors="coerce"
                    )
                    continue
            except Exception:
                pass

            # Try to convert to numeric
            try:
                numeric_series = pd.to_numeric(converted_df[col], errors="coerce")
                # If most values converted successfully, use numeric
                if numeric_series.notna().sum() / len(converted_df[col]) > 0.8:
                    converted_df[col] = numeric_series
                    continue
            except Exception:
                pass

    return converted_df


def memory_usage_summary(df: pd.DataFrame) -> dict:
    """Get detailed memory usage summary for DataFrame"""
    memory_usage = df.memory_usage(deep=True)

    return {
        "total_memory_mb": memory_usage.sum() / (1024 * 1024),
        "memory_by_column": {
            col: {
                "memory_mb": memory_usage[col] / (1024 * 1024),
                "dtype": str(df[col].dtype),
                "null_count": df[col].isnull().sum(),
                "unique_count": df[col].nunique(),
            }
            for col in df.columns
        },
        "shape": df.shape,
        "total_cells": df.shape[0] * df.shape[1],
        "memory_per_cell_bytes": memory_usage.sum() / (df.shape[0] * df.shape[1]),
    }


def find_duplicate_rows(df: pd.DataFrame, subset: list | None = None) -> pd.DataFrame:
    """Find and return duplicate rows in DataFrame"""
    try:
        if subset:
            duplicates = df[df.duplicated(subset=subset, keep=False)]
        else:
            duplicates = df[df.duplicated(keep=False)]

        return duplicates.sort_values(by=subset if subset else df.columns.tolist())
    except Exception as e:
        print(f"Warning: Error finding duplicates: {e}")
        return pd.DataFrame()


def remove_outliers_iqr(
    df: pd.DataFrame, column: str, multiplier: float = 1.5
) -> pd.DataFrame:
    """Remove outliers using IQR method"""
    try:
        if column not in df.columns:
            print(f"Warning: Column '{column}' not found in DataFrame")
            return df

        q1 = df[column].quantile(0.25)
        q3 = df[column].quantile(0.75)
        iqr = q3 - q1

        lower_bound = q1 - multiplier * iqr
        upper_bound = q3 + multiplier * iqr

        return df[(df[column] >= lower_bound) & (df[column] <= upper_bound)]

    except Exception as e:
        print(f"Warning: Error removing outliers: {e}")
        return df


class DataFrameValidator:
    """Class for validating DataFrame integrity and quality"""

    def __init__(self, df: pd.DataFrame):
        self.df = df
        self.issues = []

    def check_null_values(
        self, max_null_percentage: float = 0.1
    ) -> "DataFrameValidator":
        """Check for excessive null values"""
        for col in self.df.columns:
            null_percentage = self.df[col].isnull().sum() / len(self.df)
            if null_percentage > max_null_percentage:
                self.issues.append(
                    f"Column '{col}' has {null_percentage:.2%} null values "
                    f"(threshold: {max_null_percentage:.2%})"
                )
        return self

    def check_data_types(self, expected_types: dict) -> "DataFrameValidator":
        """Check if columns have expected data types"""
        for col, expected_type in expected_types.items():
            if col in self.df.columns:
                actual_type = str(self.df[col].dtype)
                if expected_type not in actual_type:
                    self.issues.append(
                        f"Column '{col}' has type '{actual_type}', "
                        f"expected '{expected_type}'"
                    )
        return self

    def check_value_ranges(self, ranges: dict) -> "DataFrameValidator":
        """Check if numeric columns are within expected ranges"""
        for col, (min_val, max_val) in ranges.items():
            if col in self.df.columns and pd.api.types.is_numeric_dtype(self.df[col]):
                actual_min = self.df[col].min()
                actual_max = self.df[col].max()

                if actual_min < min_val:
                    self.issues.append(
                        f"Column '{col}' minimum value {actual_min} "
                        f"is below expected {min_val}"
                    )

                if actual_max > max_val:
                    self.issues.append(
                        f"Column '{col}' maximum value {actual_max} "
                        f"is above expected {max_val}"
                    )
        return self

    def get_validation_report(self) -> dict:
        """Get comprehensive validation report"""
        return {
            "is_valid": len(self.issues) == 0,
            "issues": self.issues,
            "shape": self.df.shape,
            "memory_usage_mb": self.df.memory_usage(deep=True).sum() / (1024 * 1024),
            "columns": list(self.df.columns),
            "dtypes": self.df.dtypes.to_dict(),
        }
