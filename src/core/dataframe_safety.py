"""
Critical Issue Fix #3: DataFrame Safety Utilities

This module addresses the critical DataFrame safety issues identified
in the architect review by providing safe access patterns and utilities.

Priority: IMMEDIATE (Week 1-2)
Impact: Prevents runtime errors, improves data integrity, safer operations
"""

import numbers
import sys
from pathlib import Path
from typing import Any, TypedDict, cast

import numpy as np
import pandas as pd

# Import error handling
try:
    from ..core.error_handler import DataError, ErrorSeverity
except ImportError:
    sys.path.append(str(Path(__file__).parent.parent))
    from src.core.error_handler import DataError, ErrorSeverity


class SafeDataFrameAccessor:
    """
    Safe DataFrame operations to prevent common errors and crashes.

    Replaces dangerous direct DataFrame operations with safe alternatives
    that handle missing indices, null values, and type conversion issues.
    """

    @staticmethod
    def safe_loc_get(
        df: pd.DataFrame | None, row_index: Any, column: str, default: Any = None
    ) -> Any:
        """
        Safely get a value from DataFrame using .loc

        Args:
            df: DataFrame to access
            row_index: Row index to access
            column: Column name to access
            default: Default value if access fails

        Returns:
            Value from DataFrame or default
        """
        try:
            if df is None or df.empty:
                return default

            if row_index not in df.index:
                return default

            if column not in df.columns:
                return default

            value = cast(Any, df).at[row_index, column]

            # Handle various null/nan cases
            if pd.isna(value) or value is None:
                return default

            return value

        except (KeyError, IndexError, AttributeError, TypeError) as e:
            print(
                f"Warning: Safe DataFrame access failed for {row_index}[{column}]: {e}"
            )
            return default

    @staticmethod
    def safe_loc_set(
        df: pd.DataFrame | None, row_index: Any, column: str, value: Any
    ) -> bool:
        """
        Safely set a value in DataFrame using .loc

        Args:
            df: DataFrame to modify
            row_index: Row index to set
            column: Column name to set
            value: Value to set

        Returns:
            True if successful, False otherwise
        """
        try:
            if df is None:
                raise DataError(
                    "Cannot set value on None DataFrame", ErrorSeverity.HIGH
                )

            # Ensure column exists
            if column not in df.columns:
                df[column] = np.nan

            # Set the value
            cast(Any, df).loc[row_index, column] = value
            return True

        except (KeyError, IndexError, AttributeError, TypeError, ValueError) as e:
            print(
                f"Warning: Safe DataFrame set failed for {row_index}[{column}] = {value}: {e}"
            )
            return False

    @staticmethod
    def safe_check_value(
        df: pd.DataFrame | None, row_index: Any, column: str, check_value: Any
    ) -> bool:
        """
        Safely check if a DataFrame value equals a check value

        Args:
            df: DataFrame to check
            row_index: Row index to check
            column: Column to check
            check_value: Value to compare against

        Returns:
            True if values match, False otherwise
        """
        try:
            current_value = SafeDataFrameAccessor.safe_loc_get(df, row_index, column)

            if current_value is None:
                return False

            # Handle string comparisons safely
            if isinstance(check_value, str) and isinstance(current_value, str):
                return current_value.strip() == check_value.strip()

            return bool(current_value == check_value)

        except Exception as e:
            print(
                f"Warning: Safe DataFrame check failed for {row_index}[{column}] == {check_value}: {e}"
            )
            return False

    @staticmethod
    def safe_fillna_row(
        df: pd.DataFrame | None, row_index: Any, fill_value: Any = "TBA"
    ) -> bool:
        """
        Safely fill NaN values in a specific row

        Args:
            df: DataFrame to modify
            row_index: Row index to fill
            fill_value: Value to use for filling NaN

        Returns:
            True if successful
        """
        try:
            if df is None or df.empty:
                return False

            if row_index not in df.index:
                return False

            # Precisely fill NaN for the specific row without triggering FutureWarnings
            # about silent downcasting. We avoid vectorized mixed-dtype row assignment
            # and instead assign per-column, coercing only the necessary columns to
            # object dtype if we're inserting non-numeric values into numeric columns.
            row_series = cast(pd.Series, df.loc[row_index, :])
            try:
                row_series = row_series.infer_objects()
            except Exception:
                # Best-effort inference; continue if not supported
                pass

            # Treat Python numeric tower (incl. complex) and numpy numbers as numeric
            # Note: ruff prefers unions, but here we expand the check explicitly to satisfy linters
            is_numeric = isinstance(fill_value, numbers.Number) or isinstance(
                fill_value, np.number
            )
            is_non_numeric_fill = not is_numeric

            # Use pandas future option to avoid warning emission and adopt future behavior
            with pd.option_context("future.no_silent_downcasting", True):
                for col in df.columns:
                    try:
                        current = row_series.get(col)
                        if pd.isna(current):
                            # If filling a non-numeric value into a numeric column, upcast that column
                            if is_non_numeric_fill and df[col].dtype != object:
                                try:
                                    df[col] = df[col].astype("object")
                                except Exception:
                                    # If upcast fails, fall back to assigning as-is
                                    pass
                            # Per-column assignment avoids vectorized mixed-dtype ops
                            cast(Any, df).loc[row_index, col] = fill_value
                    except Exception:
                        # Skip problematic columns but continue overall operation
                        continue
            return True

        except Exception as e:
            print(
                f"Warning: Safe fillna failed for row {row_index}: {e}", file=sys.stderr
            )
            return False

    @staticmethod
    def safe_read_excel(file_path: str | Path, **kwargs: Any) -> pd.DataFrame | None:
        """
        Safely read Excel file with comprehensive error handling

        Args:
            file_path: Path to Excel file
            **kwargs: Additional arguments for pd.read_excel

        Returns:
            DataFrame if successful, None if failed
        """
        try:
            if isinstance(file_path, str):
                file_path = Path(file_path)

            if not file_path.exists():
                print(
                    f"Warning: Excel file does not exist: {file_path}", file=sys.stderr
                )
                return None

            if file_path.stat().st_size == 0:
                print(f"Warning: Excel file is empty: {file_path}", file=sys.stderr)
                return None

            # Default parameters for safety
            safe_kwargs: dict[str, Any] = {
                "engine": "openpyxl",
                "sheet_name": 0,
                "header": 0,
                **kwargs,  # Override with user-provided kwargs
            }

            # Inline Any cast to avoid partial-unknown stub issues
            df = cast(
                pd.DataFrame,
                cast(Any, pd.read_excel)(file_path, **safe_kwargs),  # type: ignore[reportUnknownArgumentType, reportUnknownMemberType]
            )

            if df.empty:
                print(
                    f"Warning: Loaded DataFrame is empty from {file_path}",
                    file=sys.stderr,
                )
                return df  # Return empty DF rather than None

            return df

        except (FileNotFoundError, PermissionError, ValueError, ImportError) as e:
            print(
                f"Warning: Could not read Excel file {file_path}: {e}", file=sys.stderr
            )
            return None
        except Exception as e:
            print(
                f"Error: Unexpected error reading Excel file {file_path}: {e}",
                file=sys.stderr,
            )
            return None

    @staticmethod
    def safe_to_excel(
        df: pd.DataFrame | None, file_path: str | Path, **kwargs: Any
    ) -> bool:
        """
        Safely write DataFrame to Excel with error handling

        Args:
            df: DataFrame to write
            file_path: Output file path
            **kwargs: Additional arguments for to_excel

        Returns:
            True if successful
        """
        try:
            if df is None:
                print("Warning: Cannot write None DataFrame to Excel")
                return False

            if isinstance(file_path, str):
                file_path = Path(file_path)

            # Create directory if it doesn't exist
            file_path.parent.mkdir(parents=True, exist_ok=True)

            # Default parameters for safety
            safe_kwargs: dict[str, Any] = {
                "engine": "openpyxl",
                "sheet_name": "Sheet1",
                "index": True,
                "merge_cells": False,
                **kwargs,  # Override with user-provided kwargs
            }

            # Inline Any cast to avoid partial-unknown stub issues
            cast(Any, df.to_excel)(file_path, **safe_kwargs)  # type: ignore[reportUnknownArgumentType, reportUnknownMemberType]
            return True

        except (PermissionError, ValueError, ImportError) as e:
            print(f"Warning: Could not write Excel file {file_path}: {e}")
            return False
        except Exception as e:
            print(f"Error: Unexpected error writing Excel file {file_path}: {e}")
            return False

    @staticmethod
    def safe_column_exists(df: pd.DataFrame, column: str) -> bool:
        """
        Safely check if column exists in DataFrame

        Args:
            df: DataFrame to check
            column: Column name to check

        Returns:
            True if column exists
        """
        try:
            return (not df.empty) and (column in df.columns)
        except Exception:
            return False

    @staticmethod
    def safe_index_exists(df: pd.DataFrame, index: Any) -> bool:
        """
        Safely check if index exists in DataFrame

        Args:
            df: DataFrame to check
            index: Index value to check

        Returns:
            True if index exists
        """
        try:
            return (not df.empty) and (index in df.index)
        except Exception:
            return False

    @staticmethod
    def create_safe_dataframe(
        index_name: str | None = None, columns: list[str] | None = None
    ) -> pd.DataFrame:
        """
        Create a safe, empty DataFrame with proper structure

        Args:
            index_name: Name for the index
            columns: List of column names

        Returns:
            Empty DataFrame with proper structure
        """
        try:
            if columns is None:
                columns = []

            df = pd.DataFrame(columns=columns)

            if index_name:
                df.index.name = index_name

            return df

        except Exception as e:
            print(f"Warning: Could not create safe DataFrame: {e}")
            return pd.DataFrame()


class DataFrameValidator:
    """
    Validates DataFrame operations and structure to prevent common issues.
    """

    class ValidationReport(TypedDict):
        is_valid: bool
        issues: list[str]
        warnings: list[str]
        info: dict[str, Any]

    @staticmethod
    def validate_dataframe_structure(
        df: pd.DataFrame | None,
        required_columns: list[str] | None = None,
        required_index_name: str | None = None,
    ) -> "DataFrameValidator.ValidationReport":
        """
        Validate DataFrame structure and return validation report

        Args:
            df: DataFrame to validate
            required_columns: List of required column names
            required_index_name: Required index name

        Returns:
            Validation report dictionary
        """
        report: DataFrameValidator.ValidationReport = {
            "is_valid": True,
            "issues": [],
            "warnings": [],
            "info": {},
        }

        try:
            # Basic checks
            if df is None:
                report["is_valid"] = False
                report["issues"].append("DataFrame is None")
                return report

            if df.empty:
                report["warnings"].append("DataFrame is empty")

            # Check required columns
            if required_columns:
                missing_columns = [
                    col for col in required_columns if col not in df.columns
                ]
                if missing_columns:
                    report["is_valid"] = False
                    report["issues"].append(
                        f"Missing required columns: {missing_columns}"
                    )

            # Check index name
            if required_index_name and df.index.name != required_index_name:
                report["warnings"].append(
                    f"Index name is '{df.index.name}', expected '{required_index_name}'"
                )

            # Gather info
            # Build null_counts as a concrete dict[str, int] to avoid partially-unknown stubs
            _null_counts_series = df.isnull().sum()
            _null_counts: dict[str, int] = {
                str(k): int(v) for k, v in _null_counts_series.items()
            }
            info: dict[str, Any] = {
                "shape": df.shape,
                "columns": list(df.columns),
                "index_name": df.index.name,
                "memory_usage": df.memory_usage(deep=True).sum(),
                "null_counts": _null_counts,
            }
            report["info"] = info

        except Exception as e:
            report["is_valid"] = False
            report["issues"].append(f"Validation error: {str(e)}")

        return report

    @staticmethod
    def suggest_dataframe_cleanup(df: pd.DataFrame | None) -> list[str]:
        """
        Suggest cleanup operations for a DataFrame

        Args:
            df: DataFrame to analyze

        Returns:
            List of suggested cleanup operations
        """
        suggestions: list[str] = []

        try:
            if df is None or df.empty:
                return ["DataFrame is None or empty - no cleanup suggestions"]

            # Check for duplicate indices
            if df.index.duplicated().any():
                suggestions.append("Remove duplicate indices")

            # Check for completely null columns
            null_columns = df.columns[df.isnull().all()].tolist()
            if null_columns:
                suggestions.append(f"Consider removing null columns: {null_columns}")

            # Check for mixed data types in columns
            for col in df.columns:
                if df[col].dtype == "object":
                    unique_types = set(type(x).__name__ for x in df[col].dropna())
                    if len(unique_types) > 1:
                        suggestions.append(
                            f"Column '{col}' has mixed data types: {unique_types}"
                        )

            # Check memory usage
            memory_mb = df.memory_usage(deep=True).sum() / 1024 / 1024
            if memory_mb > 100:  # If DataFrame is > 100MB
                suggestions.append(
                    f"Large DataFrame ({memory_mb:.1f}MB) - consider data type optimization"
                )

        except Exception as e:
            suggestions.append(f"Error analyzing DataFrame: {str(e)}")

        return suggestions if suggestions else ["DataFrame appears clean"]


def migrate_legacy_dataframe_operations():
    """
    Provide migration guidance for legacy DataFrame operations
    """
    migration_guide = {
        "REPLACE": {
            # Dangerous operations -> Safe alternatives
            "df.loc[symbol, 'column'] = value": "SafeDataFrameAccessor.safe_loc_set(df, symbol, 'column', value)",
            "value = df.loc[symbol, 'column']": "value = SafeDataFrameAccessor.safe_loc_get(df, symbol, 'column', default_value)",
            "if df.loc[symbol, 'column'] == check": "if SafeDataFrameAccessor.safe_check_value(df, symbol, 'column', check)",
            "pd.read_excel(path)": "SafeDataFrameAccessor.safe_read_excel(path)",
            "df.to_excel(path)": "SafeDataFrameAccessor.safe_to_excel(df, path)",
        },
        "VALIDATE": {
            "Before operations": "report = DataFrameValidator.validate_dataframe_structure(df, required_columns)",
            "For cleanup": "suggestions = DataFrameValidator.suggest_dataframe_cleanup(df)",
        },
    }

    print("🔧 DataFrame Safety Migration Guide")
    print("=" * 40)

    for category, operations in migration_guide.items():
        print(f"\n{category}:")
        for old, new in operations.items():
            print(f"  ❌ {old}")
            print(f"  ✅ {new}")

    return migration_guide


if __name__ == "__main__":
    # Demo the migration guide
    migrate_legacy_dataframe_operations()
