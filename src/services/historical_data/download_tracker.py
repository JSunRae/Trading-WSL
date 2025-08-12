"""
Download Tracker Service

Extracted from requestCheckerCLS to handle download tracking and status management.
This addresses the monolithic class decomposition critical issue.

Responsibilities:
- Track completed downloads
- Track failed downloads
- Manage downloadable symbols
- Handle Excel file I/O for tracking data
"""

import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pandas as pd

# Import configuration management
try:
    from ...core.config import get_config
    from ...core.error_handler import DataError, ErrorSeverity, TradingSystemError
except ImportError:
    # Fallback for direct execution
    sys.path.append(str(Path(__file__).parent.parent.parent.parent))
    from src.core.config import get_config
    from src.core.error_handler import DataError, ErrorSeverity


class DownloadTracker:
    """
    Manages tracking of historical data downloads.

    Extracted from the monolithic requestCheckerCLS to provide focused
    functionality for download status management.
    """

    def __init__(self):
        """Initialize the download tracker with configuration-based paths"""
        self.config = get_config()

        # Initialize DataFrames with error handling
        self._load_tracking_data()

        # Change counters for batch saves
        self.fail_changes = 0
        self.downloadable_changes = 0
        self.downloaded_changes = 0

        # Batch save thresholds
        self.FAIL_SAVE_THRESHOLD = 20
        self.DOWNLOADABLE_SAVE_THRESHOLD = 100
        self.DOWNLOADED_SAVE_THRESHOLD = 50

    def _load_tracking_data(self):
        """Load tracking data from Excel files"""
        # Load failed stocks
        try:
            failed_path = self.config.get_data_file_path("ib_failed_stocks")
            self.df_failed = pd.read_excel(
                failed_path,
                sheet_name=0,
                header=0,
                engine="openpyxl",
                index_col="Stock",
            )
        except (FileNotFoundError, PermissionError, ValueError) as e:
            print(f"Warning: Could not load IB Failed Stocks.xlsx: {e}")
            self.df_failed = pd.DataFrame(index=pd.Index([], name="Stock"))

        # Load downloadable stocks
        try:
            downloadable_path = self.config.get_data_file_path("ib_downloadable_stocks")
            self.df_downloadable = pd.read_excel(
                downloadable_path,
                sheet_name=0,
                header=0,
                engine="openpyxl",
                index_col="Stock",
            )
        except (FileNotFoundError, PermissionError, ValueError) as e:
            print(f"Warning: Could not load IB Downloadable Stocks.xlsx: {e}")
            self.df_downloadable = pd.DataFrame(index=pd.Index([], name="Stock"))

        # Load downloaded stocks
        try:
            downloaded_path = self.config.get_data_file_path("ib_downloaded_stocks")
            self.df_downloaded = pd.read_excel(
                downloaded_path,
                sheet_name=0,
                header=0,
                engine="openpyxl",
                index_col="DateStock",
            )
        except (FileNotFoundError, PermissionError, ValueError) as e:
            print(f"Warning: Could not load IB Downloaded Stocks.xlsx: {e}")
            self.df_downloaded = pd.DataFrame(index=pd.Index([], name="DateStock"))

    def mark_failed(
        self,
        symbol: str,
        bar_size: str = "",
        for_date: str = "",
        non_existent: bool = True,
        earliest_avail_bar: str = "",
        comment: str = "",
    ) -> bool:
        """
        Mark a symbol as failed for download

        Args:
            symbol: Stock symbol
            bar_size: Bar size (e.g., "1 min", "30 mins")
            for_date: Date string for the failed attempt
            non_existent: True if symbol doesn't exist, False if just unavailable for date
            earliest_avail_bar: Earliest available bar for the symbol
            comment: Error comment

        Returns:
            True if marked successfully
        """
        if not symbol:
            raise DataError("Symbol cannot be blank", ErrorSeverity.MEDIUM)

        save_needed = False

        if bar_size == "" and comment != "":
            # This is an error capture, only add comment
            for i in range(10):
                comment_col = f"Comment{i}"
                date_col = f"Date{i}"

                if comment_col not in self.df_failed.columns:
                    self.df_failed.loc[symbol, date_col] = for_date
                    self.df_failed.loc[symbol, comment_col] = comment
                    save_needed = True
                    break
                elif pd.isnull(self.df_failed.loc[symbol, comment_col]):
                    self.df_failed.loc[symbol, date_col] = for_date
                    self.df_failed.loc[symbol, comment_col] = comment
                    save_needed = True
                    break
                elif (
                    self.df_failed.loc[symbol, comment_col] == f"{for_date}::{comment}"
                ):
                    break  # Already noted

            # Set default non-existent status if not set
            if pd.isnull(self.df_failed.loc[symbol, "NonExistant"]):
                self.df_failed.loc[symbol, "NonExistant"] = "Maybe"

        else:
            # Regular failure tracking
            save_needed = True
            self.df_failed.loc[symbol, "NonExistant"] = "Yes" if non_existent else "No"

            if not non_existent:
                # Set earliest available bar if provided
                if earliest_avail_bar and pd.isnull(
                    self.df_failed.loc[symbol, "EarliestAvailBar"]
                ):
                    self.df_failed.loc[symbol, "EarliestAvailBar"] = earliest_avail_bar

                # Track latest failed date for this bar size
                latest_failed_col = f"{bar_size}-LatestFailed"
                if latest_failed_col not in self.df_failed.columns:
                    self.df_failed.loc[symbol, latest_failed_col] = for_date
                else:
                    try:
                        current_latest = self.df_failed.at[symbol, latest_failed_col]
                        if pd.isnull(current_latest) or current_latest > for_date:
                            self.df_failed.loc[symbol, latest_failed_col] = for_date
                    except (KeyError, IndexError):
                        self.df_failed.loc[symbol, latest_failed_col] = for_date

        if save_needed:
            self.fail_changes += 1
            self._save_failed_if_needed()

        return True

    def is_failed(self, symbol: str, bar_size: str, for_date: str = "") -> bool:
        """
        Check if a symbol is marked as failed

        Args:
            symbol: Stock symbol
            bar_size: Bar size
            for_date: Date to check

        Returns:
            True if marked as failed
        """
        if symbol not in self.df_failed.index:
            return False

        # Check if symbol is completely non-existent
        non_existent = self.df_failed.loc[symbol, "NonExistant"]
        if non_existent == "Yes":
            return True

        # Check date-specific failures
        if for_date:
            latest_failed_col = f"{bar_size}-LatestFailed"
            if latest_failed_col in self.df_failed.columns:
                try:
                    latest_failed = self.df_failed.at[symbol, latest_failed_col]
                    if not pd.isnull(latest_failed) and latest_failed >= for_date:
                        return True
                except (KeyError, IndexError):
                    pass

        return False

    def mark_downloaded(self, symbol: str, bar_size: str, for_date: str) -> bool:
        """
        Mark a symbol as successfully downloaded

        Args:
            symbol: Stock symbol
            bar_size: Bar size
            for_date: Date downloaded

        Returns:
            True if marked successfully
        """
        # Create the compound key
        if isinstance(for_date, str):
            date_str = for_date[:10]  # Take first 10 characters (YYYY-MM-DD)
        elif isinstance(for_date, (date, datetime)):
            date_str = for_date.strftime("%Y-%m-%d")
        else:
            date_str = str(for_date)[:10]

        stock_date = f"{date_str}-{symbol}"

        # Mark as downloaded
        if stock_date not in self.df_downloaded.index:
            self.df_downloaded.loc[stock_date, bar_size] = "Yes"
            self.df_downloaded.loc[stock_date, "Stock"] = symbol
            self.df_downloaded.loc[stock_date, "Date"] = for_date
            # Fill other columns with "TBA"
            self.df_downloaded.loc[stock_date, :] = self.df_downloaded.loc[
                stock_date, :
            ].fillna("TBA")
        else:
            current_value = self.df_downloaded.loc[stock_date, bar_size]
            if pd.isnull(current_value) or current_value == "TBA":
                self.df_downloaded.loc[stock_date, bar_size] = "Yes"

        self.downloaded_changes += 1
        self._save_downloaded_if_needed()
        return True

    def is_downloaded(self, symbol: str, bar_size: str, for_date: str) -> bool:
        """
        Check if data has been downloaded

        Args:
            symbol: Stock symbol
            bar_size: Bar size
            for_date: Date to check

        Returns:
            True if already downloaded
        """
        # Create the compound key
        if isinstance(for_date, str):
            date_str = for_date[:10]
        elif isinstance(for_date, (date, datetime)):
            date_str = for_date.strftime("%Y-%m-%d")
        else:
            date_str = str(for_date)[:10]

        stock_date = f"{date_str}-{symbol}"

        if stock_date not in self.df_downloaded.index:
            return False

        try:
            status = self.df_downloaded.at[stock_date, bar_size]
            return status == "Yes"
        except (KeyError, IndexError):
            return False

    def _save_failed_if_needed(self):
        """Save failed stocks if threshold reached"""
        if self.fail_changes >= self.FAIL_SAVE_THRESHOLD:
            self.save_failed()

    def _save_downloaded_if_needed(self):
        """Save downloaded stocks if threshold reached"""
        if self.downloaded_changes >= self.DOWNLOADED_SAVE_THRESHOLD:
            self.save_downloaded()

    def save_failed(self):
        """Save failed stocks data"""
        if self.fail_changes > 0:
            self.fail_changes = 0
            self.df_failed = self.df_failed.sort_values("Stock")
            failed_path = self.config.get_data_file_path("ib_failed_stocks")
            self.df_failed.to_excel(
                failed_path,
                sheet_name="Sheet1",
                index=True,
                engine="openpyxl",
            )
            print(f"💾 Saved failed stocks data to {failed_path}")

    def save_downloaded(self):
        """Save downloaded stocks data"""
        if self.downloaded_changes > 0:
            self.downloaded_changes = 0
            self.df_downloaded = self.df_downloaded.sort_index()
            downloaded_path = self.config.get_data_file_path("ib_downloaded_stocks")
            self.df_downloaded.to_excel(
                downloaded_path,
                sheet_name="Sheet1",
                index=True,
                engine="openpyxl",
                merge_cells=False,
            )
            print(f"💾 Saved downloaded stocks data to {downloaded_path}")

    def save_all(self):
        """Save all tracking data"""
        self.save_failed()
        self.save_downloaded()
        print("💾 All download tracking data saved")

    def get_statistics(self) -> dict[str, Any]:
        """Get statistics about download tracking"""
        return {
            "failed_stocks": len(self.df_failed),
            "downloaded_records": len(self.df_downloaded),
            "downloadable_stocks": len(self.df_downloadable),
            "pending_saves": {
                "failed": self.fail_changes,
                "downloaded": self.downloaded_changes,
                "downloadable": self.downloadable_changes,
            },
        }
