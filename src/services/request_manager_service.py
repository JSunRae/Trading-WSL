"""
Request Manager Service - Extracted from MasterPy_Trading.py

This service handles IB API request tracking, throttling, and management.
Replaces the request management functionality from requestCheckerCLS.

Author: Interactive Brokers Trading System
Created: December 2024 (Phase 2 Monolithic Decomposition)
"""

import os
import signal
import sys
import time
from atexit import register as atexit_register
from datetime import date, datetime, timedelta
from time import perf_counter
from typing import Any

from joblib import dump, load

# Add src to path for imports
sys.path.append(os.path.join(os.path.dirname(__file__), "..", ".."))

try:
    from src.core.config import get_config
    from src.core.error_handler import TradingSystemError, handle_error
except ImportError:
    # Fallback for when running as standalone script
    print("Warning: Could not import core modules, using fallback implementations")

    def get_config():
        """Fallback config function"""
        return None

    def handle_error(error, context=None, module="", function=""):
        """Fallback error handler"""
        print(f"Error in {module}.{function}: {error}")
        return None

    class TradingSystemError(Exception):
        """Fallback exception class"""

        pass


class RequestManagerService:
    """
    Manages IB API request tracking, throttling, and pacing.

    Handles:
    - Request rate limiting and pacing
    - Request history tracking
    - Error handling for request failures
    - Graceful shutdown management
    """

    def __init__(self, ib_connection=None):
        """
        Initialize the Request Manager Service.

        Args:
            ib_connection: IB connection object (ib_insync.IB instance)
        """
        self.ib = ib_connection

        # Request tracking
        self.req_dict: dict[int, tuple[str, str, datetime]] = {}
        self.req_time = perf_counter()
        self.req_time_prev = perf_counter()
        self.sleep_total = 0
        self.total_slept = 0

        # Request history for pacing
        self.timeframe_requests: list[float] = []
        self.all_requests: list[float] = []

        # Previous request tracking for duplicate detection
        self.symbol_prev = ""
        self.end_date_time_prev = date.today() + timedelta(1)  # Tomorrow
        self.what_to_show_prev = ""

        # Download state
        self.downloading = False

        # Graceful exit handling
        self.exit_flag = False
        self.on_exit_run = perf_counter()
        signal.signal(signal.SIGINT, self._keyboard_interrupt_handler)
        atexit_register(self.on_exit)

        # Load configuration and initialize
        self._load_config()
        self._load_request_history()

    def _load_config(self) -> None:
        """Load configuration settings."""
        try:
            self.config = get_config()
        except Exception as e:
            handle_error(e, module="RequestManager", function="_load_config")
            self.config = None

    def _load_request_history(self) -> None:
        """Load request history from disk for pacing calculations."""
        from src.core.config import get_config as _gc

        history_file = _gc().get_special_file("request_checker_bin")

        if os.path.exists(history_file):
            try:
                self.timeframe_requests, self.all_requests = load(str(history_file))

                # Adjust times based on file age
                file_age = time.time() - os.path.getmtime(history_file)
                max_time = (
                    max(max(self.timeframe_requests), max(self.all_requests)) + file_age
                )

                # Reset performance counter timing
                self.all_requests = [x - max_time for x in self.all_requests]
                self.timeframe_requests = [
                    x - max_time for x in self.timeframe_requests
                ]

            except Exception as e:
                handle_error(
                    e, module="RequestManager", function="_load_request_history"
                )
                self.timeframe_requests = []
                self.all_requests = []
        else:
            self.timeframe_requests = []
            self.all_requests = []

    def send_request(
        self, timeframe: str, symbol: str, end_date_time: datetime, what_to_show: str
    ) -> int | None:
        """
        Send a request with proper pacing and tracking.

        Args:
            timeframe: The timeframe for the request
            symbol: Stock symbol
            end_date_time: End datetime for the request
            what_to_show: What data to show (TRADES, MIDPOINT, etc.)

        Returns:
            Request ID if successful, None if rate limited
        """
        # Check for duplicate requests
        if (
            symbol == self.symbol_prev
            and end_date_time == self.end_date_time_prev
            and what_to_show == self.what_to_show_prev
        ):
            return None

        # Check rate limiting
        if not self._can_send_request():
            sleep_time = self._calculate_sleep_time()
            if sleep_time > 0:
                self._sleep_with_monitoring(sleep_time)

        # Generate request ID and track
        req_id = self._generate_request_id()
        self.req_dict[req_id] = (symbol, timeframe, end_date_time)

        # Update request history
        current_time = perf_counter()
        self.all_requests.append(current_time)
        self.timeframe_requests.append(current_time)

        # Update previous request tracking
        self.symbol_prev = symbol
        self.end_date_time_prev = end_date_time
        self.what_to_show_prev = what_to_show

        # Update timing
        self.req_time_prev = self.req_time
        self.req_time = current_time

        return req_id

    def _can_send_request(self) -> bool:
        """
        Check if we can send a request based on rate limiting.

        Returns:
            True if request can be sent, False if rate limited
        """
        current_time = perf_counter()

        # Remove old requests (older than 10 minutes)
        cutoff_time = current_time - 600  # 10 minutes
        self.all_requests = [t for t in self.all_requests if t > cutoff_time]
        self.timeframe_requests = [
            t for t in self.timeframe_requests if t > cutoff_time
        ]

        # Check rate limits
        recent_requests = len(
            [t for t in self.all_requests if t > current_time - 60]
        )  # Last minute

        # IB allows ~50 requests per second, be conservative with 30
        if recent_requests >= 30:
            return False

        return True

    def _calculate_sleep_time(self) -> float:
        """
        Calculate how long to sleep based on request pacing.

        Returns:
            Sleep time in seconds
        """
        current_time = perf_counter()

        # Find the oldest request in the last minute
        recent_requests = [t for t in self.all_requests if t > current_time - 60]

        if len(recent_requests) >= 30:
            # Sleep until the oldest request is more than 60 seconds old
            oldest_recent = min(recent_requests)
            sleep_time = 61 - (current_time - oldest_recent)
            return max(0, sleep_time)

        return 0

    def _sleep_with_monitoring(self, sleep_time: float) -> None:
        """
        Sleep with monitoring and logging.

        Args:
            sleep_time: Time to sleep in seconds
        """
        if sleep_time <= 0:
            return

        print(f"⏰ Rate limiting: Sleeping {sleep_time:.1f} seconds...")
        self.sleep_total += sleep_time
        self.total_slept += sleep_time

        # Sleep in smaller chunks to allow for interruption
        end_time = time.time() + sleep_time
        while time.time() < end_time and not self.exit_flag:
            chunk_sleep = min(1.0, end_time - time.time())
            if chunk_sleep > 0:
                time.sleep(chunk_sleep)

    def _generate_request_id(self) -> int:
        """
        Generate a unique request ID.

        Returns:
            Unique request ID
        """
        # Simple incrementing ID based on current requests
        if self.req_dict:
            return max(self.req_dict.keys()) + 1
        return 1

    def remove_request(self, req_id: int) -> None:
        """
        Remove a completed request from tracking.

        Args:
            req_id: Request ID to remove
        """
        if req_id in self.req_dict:
            del self.req_dict[req_id]

    def get_request_info(self, req_id: int) -> tuple[str, str, datetime] | None:
        """
        Get information about a tracked request.

        Args:
            req_id: Request ID to look up

        Returns:
            Tuple of (symbol, timeframe, end_date_time) or None if not found
        """
        return self.req_dict.get(req_id)

    def get_active_requests(self) -> dict[int, tuple[str, str, datetime]]:
        """
        Get all currently active requests.

        Returns:
            Dictionary of active requests
        """
        return self.req_dict.copy()

    def requests_remaining(self) -> int:
        """
        Calculate remaining requests before hitting rate limit.

        Returns:
            Number of requests that can be sent immediately
        """
        current_time = perf_counter()
        recent_requests = len([t for t in self.all_requests if t > current_time - 60])
        return max(0, 30 - recent_requests)

    def sleep_remaining(self) -> float:
        """
        Calculate remaining sleep time for rate limiting.

        Returns:
            Remaining sleep time in seconds
        """
        return self._calculate_sleep_time()

    def is_downloading(self) -> bool:
        """
        Check if currently downloading data.

        Returns:
            True if downloading, False otherwise
        """
        return self.downloading

    def set_downloading(self, downloading: bool) -> None:
        """
        Set the downloading state.

        Args:
            downloading: New downloading state
        """
        self.downloading = downloading

    def save_request_history(self) -> None:
        """Save request history to disk for persistence across sessions."""
        os.makedirs("./Files", exist_ok=True)

        for _ in range(3):  # Retry up to 3 times
            try:
                dump(
                    [self.timeframe_requests, self.all_requests],
                    str(get_config().get_special_file("request_checker_bin")),
                    compress=True,
                )
                break
            except Exception as e:
                handle_error(
                    e, module="RequestManager", function="save_request_history"
                )
                continue

    def get_statistics(self) -> dict[str, Any]:
        """
        Get request manager statistics.

        Returns:
            Dictionary with current statistics
        """
        current_time = perf_counter()

        return {
            "active_requests": len(self.req_dict),
            "total_sleep_time": self.sleep_total,
            "requests_last_minute": len(
                [t for t in self.all_requests if t > current_time - 60]
            ),
            "requests_remaining": self.requests_remaining(),
            "sleep_remaining": self.sleep_remaining(),
            "is_downloading": self.downloading,
            "uptime_seconds": current_time - self.on_exit_run,
        }

    def _keyboard_interrupt_handler(self, signum, frame) -> None:
        """Handle keyboard interrupt gracefully."""
        print("\n🛑 KeyboardInterrupt received in RequestManager. Shutting down...")
        self.exit_flag = True
        self.on_exit()

    def on_exit(self) -> None:
        """Cleanup when exiting."""
        if perf_counter() - self.on_exit_run < 2:  # Prevent multiple calls
            return

        print("🧹 RequestManager cleanup...")
        self.save_request_history()

        # Clear active requests
        self.req_dict.clear()

        print("✅ RequestManager cleanup complete")


def get_request_manager(ib_connection=None) -> RequestManagerService:
    """
    Factory function to get a RequestManager instance.

    Args:
        ib_connection: IB connection object

    Returns:
        RequestManagerService instance
    """
    return RequestManagerService(ib_connection)


# Backward compatibility - Legacy interface
class RequestManagerAdapter:
    """
    Adapter class that provides the old requestCheckerCLS interface
    for request management functionality only.
    """

    def __init__(self, host="127.0.0.1", port=7497, clientId=1, ib=None):
        self.request_service = RequestManagerService(ib)

        # Legacy properties for compatibility
        self.ReqDict = self.request_service.req_dict
        self.Downloading = False
        self.exitflag = False

    def SendRequest(self, timeframe, symbol, endDateTime, WhatToShow):
        """Legacy method - delegates to new service"""
        return self.request_service.send_request(
            timeframe, symbol, endDateTime, WhatToShow
        )

    def ReqRemaining(self):
        """Legacy method - delegates to new service"""
        return self.request_service.requests_remaining()

    def SleepRem(self):
        """Legacy method - delegates to new service"""
        return self.request_service.sleep_remaining()

    def Save_requestChecks(self):
        """Legacy method - delegates to new service"""
        return self.request_service.save_request_history()

    def On_Exit(self):
        """Legacy cleanup method"""
        return self.request_service.on_exit()


if __name__ == "__main__":
    # Simple test
    print("🧪 Testing RequestManagerService...")

    manager = RequestManagerService()
    stats = manager.get_statistics()

    print("✅ Service created successfully")
    print(f"📊 Initial stats: {stats}")
    print(f"🎯 Requests remaining: {manager.requests_remaining()}")

    # Cleanup
    manager.on_exit()
    print("✅ RequestManagerService test complete")
