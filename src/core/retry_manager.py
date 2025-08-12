#!/usr/bin/env python3
"""
Retry Mechanism with Exponential Backoff

This module provides robust retry mechanisms to handle transient failures
in the trading system, addressing root causes of error proliferation.
"""

import asyncio
import logging
import random
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from functools import wraps
from pathlib import Path
from typing import Any

from src.types.project_types import AnyFn

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.error_handler import TradingSystemError, get_error_handler, handle_error


class RetryStrategy(Enum):
    """Different retry strategies"""

    FIXED_DELAY = "fixed_delay"
    EXPONENTIAL_BACKOFF = "exponential_backoff"
    LINEAR_BACKOFF = "linear_backoff"
    JITTERED_EXPONENTIAL = "jittered_exponential"


class FailureType(Enum):
    """Types of failures that can be retried"""

    CONNECTION_ERROR = "connection_error"
    TIMEOUT_ERROR = "timeout_error"
    RATE_LIMIT_ERROR = "rate_limit_error"
    TEMPORARY_ERROR = "temporary_error"
    DATA_ERROR = "data_error"
    SYSTEM_ERROR = "system_error"


@dataclass
class RetryConfig:
    """Configuration for retry mechanisms"""

    max_attempts: int = 3
    base_delay: float = 1.0
    max_delay: float = 60.0
    strategy: RetryStrategy = RetryStrategy.EXPONENTIAL_BACKOFF
    jitter: bool = True
    backoff_multiplier: float = 2.0

    # Failure-specific settings
    retryable_exceptions: list[type] | None = None
    non_retryable_exceptions: list[type] | None = None
    failure_conditions: list[AnyFn] | None = None

    # Callbacks
    on_retry: AnyFn | None = None
    on_failure: AnyFn | None = None
    on_success: AnyFn | None = None


@dataclass
class RetryAttempt:
    """Information about a retry attempt"""

    attempt_number: int
    delay: float
    exception: Exception | None
    timestamp: float
    elapsed_time: float


class RetryStats:
    """Statistics tracking for retry operations"""

    def __init__(self):
        self.total_operations = 0
        self.successful_operations = 0
        self.failed_operations = 0
        self.total_attempts = 0
        self.total_retry_time = 0.0
        self.retry_counts: dict[int, int] = {}  # attempts -> count
        self.failure_types: dict[str, int] = {}

    def record_operation(
        self,
        attempts: int,
        success: bool,
        total_time: float,
        failure_type: str | None = None,
    ):
        """Record the results of a retry operation"""
        self.total_operations += 1
        self.total_attempts += attempts
        self.total_retry_time += total_time

        if success:
            self.successful_operations += 1
        else:
            self.failed_operations += 1
            if failure_type:
                self.failure_types[failure_type] = (
                    self.failure_types.get(failure_type, 0) + 1
                )

        self.retry_counts[attempts] = self.retry_counts.get(attempts, 0) + 1

    def get_success_rate(self) -> float:
        """Get success rate percentage"""
        if self.total_operations == 0:
            return 100.0
        return (self.successful_operations / self.total_operations) * 100

    def get_average_attempts(self) -> float:
        """Get average number of attempts per operation"""
        if self.total_operations == 0:
            return 0.0
        return self.total_attempts / self.total_operations

    def get_summary(self) -> dict[str, Any]:
        """Get comprehensive statistics summary"""
        return {
            "total_operations": self.total_operations,
            "success_rate": self.get_success_rate(),
            "average_attempts": self.get_average_attempts(),
            "total_retry_time": self.total_retry_time,
            "retry_distribution": self.retry_counts,
            "failure_types": self.failure_types,
        }


class RetryManager:
    """Advanced retry manager with multiple strategies"""

    def __init__(self, config: RetryConfig | None = None):
        self.config = config or RetryConfig()
        self.error_handler = get_error_handler()
        self.logger = logging.getLogger(__name__)
        self.stats = RetryStats()

        # Default retryable exceptions
        if self.config.retryable_exceptions is None:
            self.config.retryable_exceptions = [
                ConnectionError,
                TimeoutError,
                OSError,
                TradingSystemError,
            ]

        # Default non-retryable exceptions
        if self.config.non_retryable_exceptions is None:
            self.config.non_retryable_exceptions = [
                ValueError,
                TypeError,
                KeyError,
                AttributeError,
            ]

    def execute_with_retry(self, func: AnyFn, *args: Any, **kwargs: Any) -> Any:
        """Execute function with retry logic"""

        operation_start = time.time()
        attempts: list[RetryAttempt] = []
        last_exception = None

        for attempt in range(1, self.config.max_attempts + 1):
            attempt_start = time.time()

            try:
                # Execute the function
                result = func(*args, **kwargs)

                # Success callback
                if self.config.on_success:
                    self.config.on_success(attempt, time.time() - operation_start)

                # Record successful operation
                self.stats.record_operation(
                    attempts=attempt,
                    success=True,
                    total_time=time.time() - operation_start,
                )

                if attempt > 1:
                    self.logger.info(f"Operation succeeded on attempt {attempt}")

                return result

            except Exception as e:
                last_exception = e
                elapsed = time.time() - attempt_start

                # Check if this exception should be retried
                if not self._should_retry(e, attempt):
                    # Record failed operation
                    self.stats.record_operation(
                        attempts=attempt,
                        success=False,
                        total_time=time.time() - operation_start,
                        failure_type=type(e).__name__,
                    )

                    # Failure callback
                    if self.config.on_failure:
                        self.config.on_failure(e, attempt)

                    # Log and re-raise
                    handle_error(
                        e,
                        module=__name__,
                        function="execute_with_retry",
                        context={
                            "attempt": attempt,
                            "total_attempts": self.config.max_attempts,
                            "function": func.__name__  # type: ignore[attr-defined]
                            if hasattr(func, "__name__")  # pyright: ignore[reportUnknownMemberType]  # callable name access
                            else str(func),
                        },
                    )
                    raise

                # Record this attempt
                attempts.append(
                    RetryAttempt(
                        attempt_number=attempt,
                        delay=0,  # Will be set below
                        exception=e,
                        timestamp=time.time(),
                        elapsed_time=elapsed,
                    )
                )

                # If this was the last attempt, give up
                if attempt >= self.config.max_attempts:
                    # Record failed operation
                    self.stats.record_operation(
                        attempts=attempt,
                        success=False,
                        total_time=time.time() - operation_start,
                        failure_type=type(e).__name__,
                    )

                    self.logger.error(f"Operation failed after {attempt} attempts: {e}")

                    # Failure callback
                    if self.config.on_failure:
                        self.config.on_failure(e, attempt)

                    raise

                # Calculate delay for next attempt
                delay = self._calculate_delay(attempt)
                attempts[-1].delay = delay

                self.logger.warning(
                    f"Attempt {attempt} failed: {e}. Retrying in {delay:.1f}s..."
                )

                # Retry callback
                if self.config.on_retry:
                    self.config.on_retry(e, attempt, delay)

                # Wait before next attempt
                time.sleep(delay)

        # Should never reach here, but just in case
        if last_exception:
            raise last_exception

    def _should_retry(self, exception: Exception, attempt: int) -> bool:
        """Determine if an exception should be retried"""

        # Check if we've reached max attempts
        if attempt >= self.config.max_attempts:
            return False

        # Check non-retryable exceptions first
        for exc_type in self.config.non_retryable_exceptions or []:
            if isinstance(exception, exc_type):
                return False

        # Check retryable exceptions
        for exc_type in self.config.retryable_exceptions or []:
            if isinstance(exception, exc_type):
                return True

        # Check custom failure conditions
        if self.config.failure_conditions:
            for condition in self.config.failure_conditions:
                try:
                    if condition(exception):
                        return True
                except Exception:
                    # If condition check fails, don't retry
                    pass

        # Default: don't retry unknown exceptions
        return False

    def _calculate_delay(self, attempt: int) -> float:
        """Calculate delay for next retry attempt"""

        if self.config.strategy == RetryStrategy.FIXED_DELAY:
            delay = self.config.base_delay

        elif self.config.strategy == RetryStrategy.LINEAR_BACKOFF:
            delay = self.config.base_delay * attempt

        elif self.config.strategy == RetryStrategy.EXPONENTIAL_BACKOFF:
            delay = self.config.base_delay * (
                self.config.backoff_multiplier ** (attempt - 1)
            )

        elif self.config.strategy == RetryStrategy.JITTERED_EXPONENTIAL:
            base_delay = self.config.base_delay * (
                self.config.backoff_multiplier ** (attempt - 1)
            )
            # Add random jitter (±25%)
            jitter_range = base_delay * 0.25
            delay = base_delay + random.uniform(-jitter_range, jitter_range)

        else:
            delay = self.config.base_delay

        # Apply jitter if enabled (for non-jittered strategies)
        if (
            self.config.jitter
            and self.config.strategy != RetryStrategy.JITTERED_EXPONENTIAL
        ):
            jitter_range = delay * 0.1  # ±10% jitter
            delay += random.uniform(-jitter_range, jitter_range)

        # Ensure delay is within bounds
        delay = max(0.1, min(delay, self.config.max_delay))

        return delay


# Global retry manager instance
_retry_manager: RetryManager | None = None


def get_retry_manager() -> RetryManager:
    """Get the global retry manager instance"""
    global _retry_manager

    if _retry_manager is None:
        _retry_manager = RetryManager()

    return _retry_manager


def retry_on_failure(config: RetryConfig | None = None):
    """Decorator for automatic retry on failure"""

    def decorator(func: AnyFn) -> AnyFn:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            retry_manager = RetryManager(config) if config else get_retry_manager()
            return retry_manager.execute_with_retry(func, *args, **kwargs)

        return wrapper

    return decorator


def retry_async(config: RetryConfig | None = None):
    """Decorator for async functions with retry logic"""

    def decorator(func: AnyFn) -> AnyFn:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            retry_manager = RetryManager(config) if config else get_retry_manager()

            # Async wrapper for the retry logic
            def sync_func() -> Any:
                # Create a new event loop for this thread
                try:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    return loop.run_until_complete(func(*args, **kwargs))
                finally:
                    loop.close()

            return retry_manager.execute_with_retry(sync_func)

        return wrapper

    return decorator


# Specialized retry configurations for common use cases


def get_connection_retry_config() -> RetryConfig:
    """Get retry configuration optimized for connection errors"""
    return RetryConfig(
        max_attempts=5,
        base_delay=1.0,
        max_delay=30.0,
        strategy=RetryStrategy.JITTERED_EXPONENTIAL,
        backoff_multiplier=2.0,
        retryable_exceptions=[ConnectionError, TimeoutError, OSError],
        non_retryable_exceptions=[ValueError, TypeError, KeyError],
    )


def get_rate_limit_retry_config() -> RetryConfig:
    """Get retry configuration optimized for rate limiting"""
    return RetryConfig(
        max_attempts=10,
        base_delay=5.0,
        max_delay=300.0,  # 5 minutes max
        strategy=RetryStrategy.LINEAR_BACKOFF,
        backoff_multiplier=1.5,
    )


def get_data_download_retry_config() -> RetryConfig:
    """Get retry configuration optimized for data downloads"""
    return RetryConfig(
        max_attempts=3,
        base_delay=2.0,
        max_delay=60.0,
        strategy=RetryStrategy.EXPONENTIAL_BACKOFF,
        backoff_multiplier=3.0,
        jitter=True,
    )


# Example usage functions


@retry_on_failure(get_connection_retry_config())
def connect_to_ib():
    """Example function that might fail due to connection issues"""
    # Simulate connection attempt
    if random.random() < 0.7:  # 70% chance of failure
        raise ConnectionError("Failed to connect to IB Gateway")

    return "Connected successfully"


@retry_on_failure(get_data_download_retry_config())
def download_market_data(symbol: str):
    """Example function that might fail during data download"""
    # Simulate download attempt
    if random.random() < 0.5:  # 50% chance of failure
        raise TimeoutError(f"Timeout downloading data for {symbol}")

    return f"Downloaded market data for {symbol}"


@retry_on_failure(get_rate_limit_retry_config())
def make_api_request(endpoint: str):
    """Example function that might hit rate limits"""
    # Simulate API request
    if random.random() < 0.3:  # 30% chance of rate limit
        raise Exception("Rate limit exceeded")

    return f"API response from {endpoint}"


def main():
    """Demo the retry system"""

    print("🔄 Retry Mechanism Demo")
    print("=" * 40)

    # Get retry manager
    retry_manager = get_retry_manager()

    print("🧪 Testing retry mechanisms...")

    # Test 1: Connection retry
    print("\n1️⃣ Testing connection retry...")
    try:
        result = connect_to_ib()
        print(f"✅ {result}")
    except Exception as e:
        print(f"❌ Failed: {e}")

    # Test 2: Data download retry
    print("\n2️⃣ Testing data download retry...")
    try:
        result = download_market_data("AAPL")
        print(f"✅ {result}")
    except Exception as e:
        print(f"❌ Failed: {e}")

    # Test 3: API rate limit retry
    print("\n3️⃣ Testing rate limit retry...")
    try:
        result = make_api_request("/market-data")
        print(f"✅ {result}")
    except Exception as e:
        print(f"❌ Failed: {e}")

    # Show statistics
    print("\n📊 Retry Statistics:")
    stats = retry_manager.stats.get_summary()
    print(f"  Total operations: {stats['total_operations']}")
    print(f"  Success rate: {stats['success_rate']:.1f}%")
    print(f"  Average attempts: {stats['average_attempts']:.1f}")
    print(f"  Total retry time: {stats['total_retry_time']:.1f}s")

    if stats["failure_types"]:
        print(f"  Failure types: {stats['failure_types']}")

    print("\n🎉 Retry mechanism demo complete!")


if __name__ == "__main__":
    main()
