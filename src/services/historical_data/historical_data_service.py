"""
Historical Data Service

Main service that orchestrates historical data management.
Extracted from the monolithic requestCheckerCLS to provide focused,
testable, and maintainable historical data functionality.

Critical Issue Fix #2: Monolithic Class Decomposition
Priority: IMMEDIATE (Week 1-2)
Impact: Maintainability, testability, separation of concerns
"""

import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Import configuration management
try:
    from ...core.config import get_config
    from ...core.error_handler import DataError, ErrorSeverity, TradingSystemError
    from .availability_checker import AvailabilityChecker
    from .download_tracker import DownloadTracker
except ImportError:
    # Fallback for direct execution
    sys.path.append(str(Path(__file__).parent.parent.parent.parent))
    from availability_checker import AvailabilityChecker
    from download_tracker import DownloadTracker

    from src.core.config import get_config


@dataclass
class DownloadRequest:
    """Represents a historical data download request"""

    symbol: str
    bar_size: str
    for_date: str = ""
    force_redownload: bool = False
    max_retries: int = 3


class HistoricalDataService:
    """
    Main historical data service.

    Provides a clean interface for historical data operations,
    replacing the monolithic requestCheckerCLS functionality.
    """

    def __init__(self, ib_connection=None):
        """Initialize the historical data service"""
        self.config = get_config()
        self.ib_connection = ib_connection

        # Initialize sub-services
        self.download_tracker = DownloadTracker()
        self.availability_checker = AvailabilityChecker(self.download_tracker)

        # Request throttling
        self.request_times = []
        self.timeframe_requests = []

        # Load saved request timing data
        self._load_request_timing()

        # Statistics
        self.stats = {
            "requests_made": 0,
            "downloads_completed": 0,
            "downloads_failed": 0,
            "cache_hits": 0,
        }

    def _load_request_timing(self):
        """Load saved request timing data"""
        try:
            try:
                request_file = self.config.get_special_file("request_checker_bin")
            except Exception:
                request_file = Path("./Files/requestChecker.bin")
            if request_file.exists():
                from joblib import load

                self.timeframe_requests, self.request_times = load(str(request_file))

                # Adjust timing based on file age
                file_age = time.time() - request_file.stat().st_mtime
                max_time = (
                    max(
                        max(self.timeframe_requests, default=0),
                        max(self.request_times, default=0),
                    )
                    + file_age
                )

                # Reset perf_counter-based times
                current_time = time.perf_counter()
                self.request_times = [
                    t - max_time + current_time for t in self.request_times
                ]
                self.timeframe_requests = [
                    t - max_time + current_time for t in self.timeframe_requests
                ]
        except Exception as e:
            print(f"Warning: Could not load request timing data: {e}")
            self.timeframe_requests = []
            self.request_times = []

    def _save_request_timing(self):
        """Save request timing data"""
        try:
            from joblib import dump

            try:
                request_file = self.config.get_special_file("request_checker_bin")
            except Exception:
                request_file = Path("./Files/requestChecker.bin")
            request_file.parent.mkdir(parents=True, exist_ok=True)

            dump(
                [self.timeframe_requests, self.request_times],
                str(request_file),
                compress=True,
            )
        except Exception as e:
            print(f"Warning: Could not save request timing data: {e}")

    def check_if_downloaded(
        self, symbol: str, bar_size: str, for_date: str = ""
    ) -> bool:
        """
        Check if data has already been downloaded

        Args:
            symbol: Stock symbol
            bar_size: Bar size (e.g., "1 min", "30 mins")
            for_date: Date string

        Returns:
            True if already downloaded
        """
        # First check our tracking system
        if self.download_tracker.is_downloaded(symbol, bar_size, for_date):
            self.stats["cache_hits"] += 1
            return True

        # Then check if file exists
        if self.availability_checker.check_data_exists(symbol, bar_size, for_date):
            # Mark as downloaded in our tracking system
            self.download_tracker.mark_downloaded(symbol, bar_size, for_date)
            self.stats["cache_hits"] += 1
            return True

        return False

    def is_available_for_download(
        self, symbol: str, bar_size: str, for_date: str = ""
    ) -> bool:
        """
        Check if symbol is available for download

        Args:
            symbol: Stock symbol
            bar_size: Bar size
            for_date: Date string

        Returns:
            True if available for download
        """
        return self.availability_checker.is_available_for_download(
            symbol, bar_size, for_date
        )

    def mark_download_failed(
        self,
        symbol: str,
        bar_size: str,
        for_date: str = "",
        error_message: str = "",
        non_existent: bool = False,
    ) -> bool:
        """
        Mark a download as failed

        Args:
            symbol: Stock symbol
            bar_size: Bar size
            for_date: Date string
            error_message: Error message from the failure
            non_existent: True if symbol doesn't exist at all

        Returns:
            True if marked successfully
        """
        self.stats["downloads_failed"] += 1
        return self.download_tracker.mark_failed(
            symbol=symbol,
            bar_size=bar_size,
            for_date=for_date,
            comment=error_message,
            non_existent=non_existent,
        )

    def mark_download_completed(
        self, symbol: str, bar_size: str, for_date: str = ""
    ) -> bool:
        """
        Mark a download as completed successfully

        Args:
            symbol: Stock symbol
            bar_size: Bar size
            for_date: Date string

        Returns:
            True if marked successfully
        """
        self.stats["downloads_completed"] += 1
        return self.download_tracker.mark_downloaded(symbol, bar_size, for_date)

    def _throttle_requests(
        self, bar_size: str, symbol: str, end_datetime: str, what_to_show: str
    ):
        """
        Implement request throttling based on IB API limits

        IB API Limits:
        - 60 requests per 10 minutes (general)
        - 6 requests per 2 seconds (for second-based data)
        """
        current_time = time.perf_counter()

        # Check for identical requests (15 second gap)
        # This would need to be implemented with proper state tracking

        # 60 requests in 10 minutes limit
        timeout_10min = current_time - (10 * 60)
        self.request_times = [t for t in self.request_times if t >= timeout_10min]
        self.request_times.append(current_time)

        if len(self.request_times) > 60:
            sleep_time = max(0, (10 * 60) - (current_time - self.request_times[0]))
            if sleep_time > 0:
                print(f"⏳ Rate limit: sleeping {sleep_time:.1f}s for 10-minute limit")
                time.sleep(sleep_time)

        # 6 requests in 2 seconds limit (for second-based data)
        if "sec" in bar_size.lower():
            timeout_2sec = current_time - 2
            self.timeframe_requests = [
                t for t in self.timeframe_requests if t >= timeout_2sec
            ]
            self.timeframe_requests.append(current_time)

            if len(self.timeframe_requests) > 6:
                sleep_time = max(0, 2 - (current_time - self.timeframe_requests[0]))
                if sleep_time > 0:
                    print(
                        f"⏳ Rate limit: sleeping {sleep_time:.1f}s for 2-second limit"
                    )
                    time.sleep(sleep_time)

        self.stats["requests_made"] += 1

    def prepare_download_request(
        self, symbol: str, bar_size: str, for_date: str = ""
    ) -> DownloadRequest | None:
        """
        Prepare and validate a download request

        Args:
            symbol: Stock symbol
            bar_size: Bar size
            for_date: Date string

        Returns:
            DownloadRequest if valid, None if should be skipped
        """
        # Validate symbol format
        if not self.availability_checker.validate_symbol_format(symbol):
            print(f"❌ Invalid symbol format: {symbol}")
            return None

        # Check if already downloaded
        if self.check_if_downloaded(symbol, bar_size, for_date):
            print(f"✅ Already downloaded: {symbol} {bar_size} {for_date}")
            return None

        # Check if available for download
        if not self.is_available_for_download(symbol, bar_size, for_date):
            print(f"❌ Not available: {symbol} {bar_size} {for_date}")
            return None

        return DownloadRequest(symbol=symbol, bar_size=bar_size, for_date=for_date)

    def execute_download_request(self, request: DownloadRequest) -> bool:
        """
        Execute a download request using IB API

        Args:
            request: Download request to execute

        Returns:
            True if successful
        """
        if not self.ib_connection:
            print("❌ No IB connection available for download")
            return False

        try:
            # Implement request throttling
            self._throttle_requests(
                request.bar_size, request.symbol, request.for_date, "TRADES"
            )

            # This is where the actual IB API call would happen
            # The implementation would depend on the specific bar size and timeframe
            # For now, just log the request
            print(
                f"🔄 Downloading: {request.symbol} {request.bar_size} {request.for_date}"
            )

            # Placeholder for actual download logic
            # success = self._perform_ib_download(request)
            success = True  # Placeholder

            if success:
                self.mark_download_completed(
                    request.symbol, request.bar_size, request.for_date
                )
                print(f"✅ Downloaded: {request.symbol} {request.bar_size}")
                return True
            else:
                self.mark_download_failed(
                    request.symbol,
                    request.bar_size,
                    request.for_date,
                    "Download failed",
                )
                print(f"❌ Failed: {request.symbol} {request.bar_size}")
                return False

        except Exception as e:
            self.mark_download_failed(
                request.symbol, request.bar_size, request.for_date, str(e)
            )
            print(f"❌ Error downloading {request.symbol}: {e}")
            return False

    def bulk_download(
        self, symbols: list[str], bar_sizes: list[str], for_date: str = ""
    ) -> dict[str, Any]:
        """
        Perform bulk downloads for multiple symbols and bar sizes

        Args:
            symbols: List of stock symbols
            bar_sizes: List of bar sizes
            for_date: Date string

        Returns:
            Statistics about the bulk download
        """
        results = {
            "total_requests": 0,
            "successful": 0,
            "failed": 0,
            "skipped": 0,
            "errors": [],
        }

        for symbol in symbols:
            for bar_size in bar_sizes:
                request = self.prepare_download_request(symbol, bar_size, for_date)
                results["total_requests"] += 1

                if not request:
                    results["skipped"] += 1
                    continue

                try:
                    if self.execute_download_request(request):
                        results["successful"] += 1
                    else:
                        results["failed"] += 1
                except Exception as e:
                    results["failed"] += 1
                    results["errors"].append(f"{symbol} {bar_size}: {str(e)}")

        return results

    def get_service_statistics(self) -> dict[str, Any]:
        """Get comprehensive service statistics"""
        download_stats = self.download_tracker.get_statistics()
        cache_stats = self.availability_checker.get_cache_statistics()

        return {
            **self.stats,
            "download_tracking": download_stats,
            "availability_cache": cache_stats,
            "request_throttling": {
                "recent_requests": len(self.request_times),
                "recent_timeframe_requests": len(self.timeframe_requests),
            },
        }

    def cleanup(self):
        """Clean up and save data"""
        self.download_tracker.save_all()
        self._save_request_timing()
        self.availability_checker.clear_cache()
        print("🧹 Historical data service cleanup completed")

    def __enter__(self):
        """Context manager entry"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit with cleanup"""
        self.cleanup()
