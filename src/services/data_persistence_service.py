"""
Data Persistence Service - Extracted from MasterPy_Trading.py

This service handles DataFrame operations for tracking failed, downloadable,
and downloaded stock data. Replaces the data persistence functionality from requestCheckerCLS.

Author: Interactive Brokers Trading System
Created: December 2024 (Phase 2 Monolithic Decomposition)
"""

import os
import sys
from datetime import datetime
from typing import Any

import pandas as pd

# Add src to path for imports
sys.path.append(os.path.join(os.path.dirname(__file__), "..", ".."))

try:
    from src.core.config import get_config
    from src.core.error_handler import DataError, handle_error
except ImportError:
    # Fallback for when running as standalone script
    print("Warning: Could not import core modules, using fallback implementations")

    def get_config():
        """Fallback config function"""

        class FallbackConfig:
            def __init__(self):
                self.ib_download_location = "./data/ib_downloads"
                # Use config-compatible fallback paths
                from pathlib import Path

                data_dir = Path("./data")
                self.failed_stocks_location = str(data_dir / "failed_stocks.csv")
                self.downloadable_stocks_location = str(
                    data_dir / "downloadable_stocks.csv"
                )
                self.downloaded_stocks_location = str(
                    data_dir / "downloaded_stocks.csv"
                )

            def get_csv_file_path(self, csv_type: str):
                """Fallback method compatible with main config"""
                paths = {
                    "failed_stocks": self.failed_stocks_location,
                    "downloadable_stocks": self.downloadable_stocks_location,
                    "downloaded_stocks": self.downloaded_stocks_location,
                }
                return Path(paths.get(csv_type, f"./data/{csv_type}.csv"))

        return FallbackConfig()

    def handle_error(error, context=None, module="", function=""):
        """Fallback error handler"""
        print(f"Error in {module}.{function}: {error}")
        from dataclasses import dataclass
        from datetime import datetime

        @dataclass
        class ErrorReport:
            error_id: str = "fallback_error"
            timestamp: datetime = datetime.now()
            message: str = str(error)

        return ErrorReport()

    class DataError(Exception):
        """Fallback exception class"""

        pass


def safe_df_scalar_access(df: pd.DataFrame, row: str, col: str, default=None) -> Any:
    """
    Safely access a DataFrame scalar value with fallback.

    Args:
        df: DataFrame to access
        row: Row index
        col: Column name
        default: Default value if access fails

    Returns:
        Scalar value or default
    """
    try:
        if row in df.index and col in df.columns:
            value = df.loc[row, col]
            return value if not pd.isnull(value) else default
        return default
    except (KeyError, IndexError, ValueError):
        return default


def safe_df_scalar_check(
    df: pd.DataFrame, row: str, col: str, check_value: Any
) -> bool:
    """
    Safely check if a DataFrame scalar matches a value.

    Args:
        df: DataFrame to check
        row: Row index
        col: Column name
        check_value: Value to compare against

    Returns:
        True if values match, False otherwise
    """
    try:
        if row in df.index and col in df.columns:
            value = df.loc[row, col]
            return not pd.isnull(value) and value == check_value
        return False
    except (KeyError, IndexError, ValueError):
        return False


class DataPersistenceService:
    """
    Manages persistent DataFrame storage for trading system data.

    Handles:
    - Failed stock tracking
    - Downloadable stock tracking
    - Downloaded stock tracking
    - Automatic persistence and backup
    """

    def __init__(self):
        """Initialize the Data Persistence Service."""
        self.config = None
        self.df_failed: pd.DataFrame | None = None
        self.df_downloadable: pd.DataFrame | None = None
        self.df_downloaded: pd.DataFrame | None = None

        # Change counters for batch saves
        self.fail_changes = 0
        self.downloadable_changes = 0
        self.downloaded_changes = 0

        # Save thresholds
        self.save_threshold = 20

        self._load_config()
        self._initialize_dataframes()

    def _load_config(self) -> None:
        """Load configuration and set up file paths."""
        try:
            self.config = get_config()
        except Exception as e:
            handle_error(e, module="DataPersistence", function="_load_config")
            self.config = None

        # Set up file paths
        try:
            self.failed_stocks_path = str(
                self.config.get_data_file_path("ib_failed_stocks")
                if self.config
                else get_config().get_data_file_path("ib_failed_stocks")
            )
            self.downloadable_stocks_path = str(
                self.config.get_data_file_path("ib_downloadable_stocks")
                if self.config
                else get_config().get_data_file_path("ib_downloadable_stocks")
            )
            self.downloaded_stocks_path = str(
                self.config.get_data_file_path("ib_downloaded_stocks")
                if self.config
                else get_config().get_data_file_path("ib_downloaded_stocks")
            )
        except Exception:
            # Last resort minimal fallback (should rarely happen)
            base_path = os.path.expanduser("~/Machine Learning/")
            os.makedirs(base_path, exist_ok=True)
            self.failed_stocks_path = os.path.join(base_path, "IB Failed Stocks.xlsx")
            self.downloadable_stocks_path = os.path.join(
                base_path, "IB Downloadable Stocks.xlsx"
            )
            self.downloaded_stocks_path = os.path.join(
                base_path, "IB Downloaded Stocks.xlsx"
            )

    def _initialize_dataframes(self) -> None:
        """Initialize DataFrames from files or create empty ones."""
        # Initialize Failed Stocks DataFrame
        try:
            self.df_failed = pd.read_excel(
                self.failed_stocks_path,
                sheet_name=0,
                header=0,
                engine="openpyxl",
                index_col="Stock",
            )
        except (FileNotFoundError, PermissionError, ValueError) as e:
            print(f"Warning: Could not load Failed Stocks file: {e}")
            self.df_failed = pd.DataFrame(index=pd.Index([], name="Stock"))

        # Initialize Downloadable Stocks DataFrame
        try:
            self.df_downloadable = pd.read_excel(
                self.downloadable_stocks_path,
                sheet_name=0,
                header=0,
                engine="openpyxl",
                index_col="Stock",
            )
        except (FileNotFoundError, PermissionError, ValueError) as e:
            print(f"Warning: Could not load Downloadable Stocks file: {e}")
            self.df_downloadable = pd.DataFrame(index=pd.Index([], name="Stock"))

        # Initialize Downloaded Stocks DataFrame
        try:
            self.df_downloaded = pd.read_excel(
                self.downloaded_stocks_path,
                sheet_name=0,
                header=0,
                engine="openpyxl",
                index_col="DateStock",
            )
        except (FileNotFoundError, PermissionError, ValueError) as e:
            print(f"Warning: Could not load Downloaded Stocks file: {e}")
            self.df_downloaded = pd.DataFrame(index=pd.Index([], name="DateStock"))

    def append_failed(
        self,
        symbol: str,
        non_existent: bool = True,
        earliest_avail_bar: str = "",
        bar_size: str = "",
        for_date: str = "",
        comment: str = "",
    ) -> bool:
        """
        Add a failed stock record to the failed stocks DataFrame.

        Args:
            symbol: Stock symbol
            non_existent: Whether the stock doesn't exist
            earliest_avail_bar: Earliest available bar datetime
            bar_size: Bar size that failed
            for_date: Date of failure
            comment: Additional comment

        Returns:
            True if record was added/updated, False otherwise
        """
        if not symbol:
            handle_error(
                ValueError("Symbol cannot be blank for failed list"),
                module="DataPersistence",
                function="append_failed",
            )
            return False

        if self.df_failed is None:
            handle_error(
                DataError("Failed DataFrame not initialized"),
                module="DataPersistence",
                function="append_failed",
            )
            return False

        save_me = False

        # Convert timestamp objects to strings
        earliest_avail_bar = self._convert_to_string(earliest_avail_bar)
        for_date = self._convert_to_string(for_date)

        if not bar_size and comment:
            # This is an error capture - only add comment
            for i in range(10):
                comment_col = f"Comment{i}"
                date_col = f"Date{i}"

                if comment_col not in self.df_failed.columns or pd.isnull(
                    safe_df_scalar_access(self.df_failed, symbol, comment_col)
                ):
                    self.df_failed.loc[symbol, date_col] = for_date
                    self.df_failed.loc[symbol, comment_col] = comment
                    save_me = True
                    break
                elif (
                    safe_df_scalar_access(self.df_failed, symbol, comment_col)
                    == f"{for_date}::{comment}"
                ):
                    # Already noted
                    break

            # Set NonExistent to Maybe if not set
            if pd.isnull(safe_df_scalar_access(self.df_failed, symbol, "NonExistant")):
                self.df_failed.loc[symbol, "NonExistant"] = "Maybe"
        else:
            save_me = True

            if non_existent:
                self.df_failed.loc[symbol, "NonExistant"] = "Yes"
            else:
                self.df_failed.loc[symbol, "NonExistant"] = "No"

                # Set earliest available bar if not already set
                if pd.isnull(
                    safe_df_scalar_access(self.df_failed, symbol, "EarliestAvailBar")
                ):
                    if earliest_avail_bar:
                        self.df_failed.loc[symbol, "EarliestAvailBar"] = (
                            earliest_avail_bar
                        )

                # Track latest failed date for this bar size
                if bar_size:
                    latest_failed_col = f"{bar_size}-LatestFailed"
                    current_latest = safe_df_scalar_access(
                        self.df_failed, symbol, latest_failed_col
                    )

                    if current_latest is None or (
                        for_date and current_latest > for_date
                    ):
                        self.df_failed.loc[symbol, latest_failed_col] = for_date

        if save_me:
            self.fail_changes += 1

            # Auto-save when threshold reached
            if self.fail_changes >= self.save_threshold:
                self._save_failed_stocks()

        return save_me

    def is_failed(self, symbol: str, bar_size: str, for_date: str = "") -> bool:
        """
        Check if a stock/bar size combination has failed before.

        Args:
            symbol: Stock symbol
            bar_size: Bar size to check
            for_date: Date to check against

        Returns:
            True if failed, False otherwise
        """
        if self.df_failed is None or symbol not in self.df_failed.index:
            return False

        # Check if marked as non-existent
        if safe_df_scalar_check(self.df_failed, symbol, "NonExistant", "Yes"):
            return True

        # Check if latest failure date is >= requested date
        if bar_size:
            latest_failed = safe_df_scalar_access(
                self.df_failed, symbol, f"{bar_size}-LatestFailed"
            )
            if latest_failed and for_date and latest_failed >= for_date:
                return True

        return False

    def append_downloadable(
        self,
        symbol: str,
        bar_size: str,
        earliest_avail_bar: str,
        start_date: str = "",
        end_date: str = "",
    ) -> bool:
        """
        Add a downloadable stock record.

        Args:
            symbol: Stock symbol
            bar_size: Bar size available for download
            earliest_avail_bar: Earliest available bar datetime
            start_date: Start date for availability
            end_date: End date for availability

        Returns:
            True if record was added/updated, False otherwise
        """
        if not symbol:
            return False

        if self.df_downloadable is None:
            handle_error(
                DataError("Downloadable DataFrame not initialized"),
                module="DataPersistence",
                function="append_downloadable",
            )
            return False

        # Convert timestamps to strings
        earliest_avail_bar = self._convert_to_string(earliest_avail_bar)
        start_date = self._convert_to_string(start_date)
        end_date = self._convert_to_string(end_date)

        # Update the record
        if earliest_avail_bar:
            self.df_downloadable.loc[symbol, "EarliestAvailBar"] = earliest_avail_bar
        if bar_size:
            self.df_downloadable.loc[symbol, f"{bar_size}-Available"] = "Yes"
        if start_date:
            self.df_downloadable.loc[symbol, f"{bar_size}-StartDate"] = start_date
        if end_date:
            self.df_downloadable.loc[symbol, f"{bar_size}-EndDate"] = end_date

        self.downloadable_changes += 1

        # Auto-save when threshold reached
        if self.downloadable_changes >= self.save_threshold:
            self._save_downloadable_stocks()

        return True

    def append_downloaded(self, symbol: str, bar_size: str, for_date: str) -> bool:
        """
        Add a downloaded stock record.

        Args:
            symbol: Stock symbol
            bar_size: Bar size that was downloaded
            for_date: Date that was downloaded

        Returns:
            True if record was added, False otherwise
        """
        if not symbol or not bar_size or not for_date:
            return False

        if self.df_downloaded is None:
            handle_error(
                DataError("Downloaded DataFrame not initialized"),
                module="DataPersistence",
                function="append_downloaded",
            )
            return False

        # Create composite key
        date_stock_key = f"{self._convert_to_string(for_date)}_{symbol}"

        # Add the record
        self.df_downloaded.loc[date_stock_key, "Symbol"] = symbol
        self.df_downloaded.loc[date_stock_key, "BarSize"] = bar_size
        self.df_downloaded.loc[date_stock_key, "Date"] = self._convert_to_string(
            for_date
        )
        self.df_downloaded.loc[date_stock_key, "Downloaded"] = datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        )

        self.downloaded_changes += 1

        # Auto-save when threshold reached
        if self.downloaded_changes >= self.save_threshold:
            self._save_downloaded_stocks()

        return True

    def download_exists(self, symbol: str, bar_size: str, for_date: str = "") -> bool:
        """
        Check if a download already exists.

        Args:
            symbol: Stock symbol
            bar_size: Bar size
            for_date: Date to check

        Returns:
            True if download exists, False otherwise
        """
        if self.df_downloaded is None:
            return False

        if for_date:
            date_stock_key = f"{self._convert_to_string(for_date)}_{symbol}"
            return date_stock_key in self.df_downloaded.index and safe_df_scalar_check(
                self.df_downloaded, date_stock_key, "BarSize", bar_size
            )
        else:
            # Check if any download exists for this symbol and bar size
            for index in self.df_downloaded.index:
                if index.endswith(f"_{symbol}") and safe_df_scalar_check(
                    self.df_downloaded, index, "BarSize", bar_size
                ):
                    return True
            return False

    def get_earliest_available_bar(self, symbol: str) -> str | None:
        """
        Get the earliest available bar for a symbol.

        Args:
            symbol: Stock symbol

        Returns:
            Earliest available bar datetime string or None
        """
        # Check failed stocks first
        if self.df_failed is not None and symbol in self.df_failed.index:
            earliest = safe_df_scalar_access(self.df_failed, symbol, "EarliestAvailBar")
            if earliest:
                return str(earliest)

        # Check downloadable stocks
        if self.df_downloadable is not None and symbol in self.df_downloadable.index:
            earliest = safe_df_scalar_access(
                self.df_downloadable, symbol, "EarliestAvailBar"
            )
            if earliest:
                return str(earliest)

        return None

    def _convert_to_string(self, value: Any) -> str:
        """
        Convert various datetime types to string format.

        Args:
            value: Value to convert

        Returns:
            String representation of the value
        """
        if not value:
            return ""

        if hasattr(value, "strftime") and not isinstance(value, str):
            return value.strftime("%Y-%m-%d %H:%M:%S")
        elif str(type(value)).find("Timestamp") >= 0:
            return str(value)
        else:
            return str(value)

    def _save_failed_stocks(self) -> None:
        """Save failed stocks DataFrame to file."""
        try:
            if self.df_failed is not None:
                # Sort by stock symbol for consistency
                sorted_df = (
                    self.df_failed.sort_values("Stock")
                    if "Stock" in self.df_failed.columns
                    else self.df_failed.sort_index()
                )

                # Ensure directory exists
                os.makedirs(os.path.dirname(self.failed_stocks_path), exist_ok=True)

                sorted_df.to_excel(
                    self.failed_stocks_path,
                    sheet_name="Sheet1",
                    index=True,
                    engine="openpyxl",
                )
                self.fail_changes = 0
                print(f"✅ Saved failed stocks to {self.failed_stocks_path}")
        except Exception as e:
            handle_error(e, module="DataPersistence", function="_save_failed_stocks")

    def _save_downloadable_stocks(self) -> None:
        """Save downloadable stocks DataFrame to file."""
        try:
            if self.df_downloadable is not None:
                # Ensure directory exists
                os.makedirs(
                    os.path.dirname(self.downloadable_stocks_path), exist_ok=True
                )

                self.df_downloadable.to_excel(
                    self.downloadable_stocks_path,
                    sheet_name="Sheet1",
                    index=True,
                    engine="openpyxl",
                )
                self.downloadable_changes = 0
                print(
                    f"✅ Saved downloadable stocks to {self.downloadable_stocks_path}"
                )
        except Exception as e:
            handle_error(
                e, module="DataPersistence", function="_save_downloadable_stocks"
            )

    def _save_downloaded_stocks(self) -> None:
        """Save downloaded stocks DataFrame to file."""
        try:
            if self.df_downloaded is not None:
                # Ensure directory exists
                os.makedirs(os.path.dirname(self.downloaded_stocks_path), exist_ok=True)

                self.df_downloaded.to_excel(
                    self.downloaded_stocks_path,
                    sheet_name="Sheet1",
                    index=True,
                    engine="openpyxl",
                )
                self.downloaded_changes = 0
                print(f"✅ Saved downloaded stocks to {self.downloaded_stocks_path}")
        except Exception as e:
            handle_error(
                e, module="DataPersistence", function="_save_downloaded_stocks"
            )

    def save_all(self) -> None:
        """Force save all DataFrames regardless of change count."""
        self._save_failed_stocks()
        self._save_downloadable_stocks()
        self._save_downloaded_stocks()

    def get_statistics(self) -> dict[str, Any]:
        """
        Get data persistence statistics.

        Returns:
            Dictionary with current statistics
        """
        return {
            "failed_stocks_count": len(self.df_failed)
            if self.df_failed is not None
            else 0,
            "downloadable_stocks_count": len(self.df_downloadable)
            if self.df_downloadable is not None
            else 0,
            "downloaded_records_count": len(self.df_downloaded)
            if self.df_downloaded is not None
            else 0,
            "pending_fail_changes": self.fail_changes,
            "pending_downloadable_changes": self.downloadable_changes,
            "pending_downloaded_changes": self.downloaded_changes,
        }

    def cleanup(self) -> None:
        """Cleanup and save any pending changes."""
        print("🧹 DataPersistence cleanup...")
        self.save_all()
        print("✅ DataPersistence cleanup complete")


def get_data_persistence_service() -> DataPersistenceService:
    """
    Factory function to get a DataPersistence instance.

    Returns:
        DataPersistenceService instance
    """
    return DataPersistenceService()


# Backward compatibility - Legacy interface adapter
class DataPersistenceAdapter:
    """
    Adapter class that provides the old requestCheckerCLS interface
    for data persistence functionality only.
    """

    def __init__(self):
        self.data_service = DataPersistenceService()

        # Legacy properties for compatibility
        self.df_IBFailed = self.data_service.df_failed
        self.df_IBDownloadable = self.data_service.df_downloadable
        self.df_IBDownloaded = self.data_service.df_downloaded
        self.FailChanges = 0
        self.DownloadableChanges = 0
        self.DownloadedChanges = 0

    def appendFailed(
        self,
        symbol,
        NonExistant=True,
        EarliestAvailBar="",
        BarSize="",
        forDate="",
        comment="",
    ):
        """Legacy method - delegates to new service"""
        return self.data_service.append_failed(
            symbol=symbol,
            non_existent=NonExistant,
            earliest_avail_bar=EarliestAvailBar,
            bar_size=BarSize,
            for_date=forDate,
            comment=comment,
        )

    def is_failed(self, symbol, BarSize, forDate=""):
        """Legacy method - delegates to new service"""
        return self.data_service.is_failed(symbol, BarSize, forDate)

    def appendDownloadable(
        self, symbol, BarSize, EarliestAvailBar, StartDate="", EndDate=""
    ):
        """Legacy method - delegates to new service"""
        return self.data_service.append_downloadable(
            symbol=symbol,
            bar_size=BarSize,
            earliest_avail_bar=EarliestAvailBar,
            start_date=StartDate,
            end_date=EndDate,
        )

    def appendDownloaded(self, symbol, BarSize, forDate):
        """Legacy method - delegates to new service"""
        return self.data_service.append_downloaded(symbol, BarSize, forDate)

    def Download_Exists(self, symbol, BarSize, forDate=""):
        """Legacy method - delegates to new service"""
        return self.data_service.download_exists(symbol, BarSize, forDate)


if __name__ == "__main__":
    # Simple test
    print("🧪 Testing DataPersistenceService...")

    service = DataPersistenceService()
    stats = service.get_statistics()

    print("✅ Service created successfully")
    print(f"📊 Initial stats: {stats}")

    # Test adding a failed record
    result = service.append_failed("TEST", non_existent=False, comment="Test comment")
    print(f"📝 Added failed record: {result}")

    # Test checking if failed
    is_failed = service.is_failed("TEST", "1 min")
    print(f"🔍 Is TEST failed: {is_failed}")

    # Get updated stats
    updated_stats = service.get_statistics()
    print(f"📊 Updated stats: {updated_stats}")

    # Cleanup
    service.cleanup()
    print("✅ DataPersistenceService test complete")
