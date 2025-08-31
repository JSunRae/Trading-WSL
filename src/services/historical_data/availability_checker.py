"""
Availability Checker Service

Extracted from requestCheckerCLS to handle data availability checking.
This addresses the monolithic class decomposition critical issue.

Responsibilities:
- Check if symbol data is available for download
- Determine earliest available bar for symbols
- Manage symbol availability status
"""

import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

# Import configuration management
try:
    from ...core.config import get_config
except ImportError:
    # Fallback for direct execution
    sys.path.append(str(Path(__file__).parent.parent.parent.parent))
    from src.core.config import get_config


class AvailabilityChecker:
    """
    Checks data availability for symbols and timeframes.

    Extracted from the monolithic requestCheckerCLS to provide focused
    functionality for availability checking.
    """

    def __init__(self, download_tracker=None):
        """Initialize the availability checker"""
        self.config = get_config()
        self.download_tracker = download_tracker
        self._cache = {}  # Simple caching for availability checks

    def is_available_for_download(
        self, symbol: str, bar_size: str, for_date: str = ""
    ) -> bool:
        """
        Check if symbol data is available for download

        Args:
            symbol: Stock symbol
            bar_size: Bar size (e.g., "1 min", "30 mins")
            for_date: Date string to check

        Returns:
            True if available for download
        """
        if not symbol:
            return False

        # Use cache key for performance
        cache_key = f"{symbol}_{bar_size}_{for_date}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        # Check if it's marked as failed
        if self.download_tracker and self.download_tracker.is_failed(
            symbol, bar_size, for_date
        ):
            self._cache[cache_key] = False
            return False

        # Check date-based availability
        if for_date:
            try:
                if isinstance(for_date, str) and for_date != "":
                    try:
                        check_date = datetime.strptime(for_date, "%Y-%m-%d %H:%M:%S")
                    except ValueError:
                        check_date = datetime.strptime(for_date, "%Y-%m-%d %H:%M:%S.%f")
                elif for_date == "":
                    # Handle blank date case
                    self._cache[cache_key] = True
                    return True
                else:
                    check_date = for_date

                # Check against earliest available data if we have tracking info
                if (
                    self.download_tracker
                    and hasattr(self.download_tracker, "df_failed")
                    and symbol in self.download_tracker.df_failed.index
                ):
                    earliest_avail = self.download_tracker.df_failed.loc[
                        symbol, "EarliestAvailBar"
                    ]
                    if (
                        not pd.isnull(earliest_avail)
                        and isinstance(earliest_avail, datetime | pd.Timestamp)
                        and earliest_avail > check_date
                    ):
                        self._cache[cache_key] = False
                        return False

                    # Check for specific bar size failures
                    latest_failed_col = f"{bar_size}-LatestFailed"
                    if (
                        latest_failed_col in self.download_tracker.df_failed.columns
                        and not pd.isnull(
                            self.download_tracker.df_failed.loc[
                                symbol, latest_failed_col
                            ]
                        )
                    ):
                        latest_failed = self.download_tracker.df_failed.loc[
                            symbol, latest_failed_col
                        ]
                        if latest_failed < for_date:  # Failed for a later date
                            self._cache[cache_key] = False
                            return False

            except Exception as e:
                print(f"Warning: Error checking date availability for {symbol}: {e}")
                # Default to available if we can't check properly
                self._cache[cache_key] = True
                return True

        # Default to available
        self._cache[cache_key] = True
        return True

    def get_earliest_available_bar(
        self, symbol: str, ib_connection=None
    ) -> datetime | None:
        """
        Get the earliest available bar for a symbol

        Args:
            symbol: Stock symbol
            ib_connection: IB connection object (if available)

        Returns:
            Earliest available datetime or None if unknown
        """
        # First check if we have it cached in our tracking data
        if (
            self.download_tracker
            and hasattr(self.download_tracker, "df_failed")
            and symbol in self.download_tracker.df_failed.index
        ):
            earliest_avail = self.download_tracker.df_failed.loc[
                symbol, "EarliestAvailBar"
            ]
            if not pd.isnull(earliest_avail):
                try:
                    return pd.Timestamp(str(earliest_avail))
                except Exception:
                    pass

        # Check downloadable stocks data
        if (
            self.download_tracker
            and hasattr(self.download_tracker, "df_downloadable")
            and symbol in self.download_tracker.df_downloadable.index
        ):
            earliest_avail = self.download_tracker.df_downloadable.loc[
                symbol, "EarliestAvailBar"
            ]
            if not pd.isnull(earliest_avail):
                try:
                    return pd.Timestamp(str(earliest_avail))
                except Exception:
                    pass

        # If we have an IB connection, we could make an API call here
        # This is where the original code would call ib.reqHeadTimeStamp()
        # For now, return a default early date
        if ib_connection:
            try:
                # Note: This would need a proper contract object
                # earliest_bar = ib_connection.reqHeadTimeStamp(contract, "TRADES", useRTH=False, formatDate=1)
                # return pd.Timestamp(str(earliest_bar))
                pass
            except Exception as e:
                print(f"Warning: Could not get earliest bar from IB for {symbol}: {e}")

        # Default fallback - assume data starts from 2000
        return pd.Timestamp(year=2000, month=1, day=1)

    def check_data_exists(self, symbol: str, bar_size: str, for_date: str) -> bool:
        """
        Check if data file already exists for the given parameters

        Args:
            symbol: Stock symbol
            bar_size: Bar size
            for_date: Date string

        Returns:
            True if data file exists
        """
        try:
            # Get the expected file path
            file_path = self.config.get_data_file_path(
                "ib_download", symbol=symbol, timeframe=bar_size, date_str=for_date
            )

            return file_path.exists() and file_path.stat().st_size > 0
        except Exception as e:
            print(f"Warning: Error checking if data exists for {symbol}: {e}")
            return False

    def validate_symbol_format(self, symbol: str) -> bool:
        """
        Validate symbol format

        Args:
            symbol: Stock symbol to validate

        Returns:
            True if symbol format is valid
        """
        if not symbol or not isinstance(symbol, str):
            return False

        # Basic validation - should be alphanumeric, potentially with dots/hyphens
        import re

        return bool(re.match(r"^[A-Z0-9.-]{1,10}$", symbol.upper()))

    def clear_cache(self):
        """Clear the availability cache"""
        self._cache.clear()

    def get_cache_statistics(self) -> dict[str, Any]:
        """Get cache statistics"""
        return {
            "cache_size": len(self._cache),
            "cached_symbols": len(set(key.split("_")[0] for key in self._cache.keys())),
        }
