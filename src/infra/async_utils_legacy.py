"""
Async utilities for safe concurrency, pacing, and IB throttle prevention.

This module provides:
- RateLimiter: Prevents IB API throttling with configurable rate limits
- gather_bounded: Bounded concurrency to avoid overwhelming IB Gateway
- with_retry: Intelligent retry logic with exponential backoff
- timeout helpers: Prevent hanging operations
"""

from __future__ import annotations

import asyncio
import time
import logging
from typing import Any, Awaitable, Callable, Iterable, TypeVar, cast
from types import TracebackType

logger = logging.getLogger(__name__)

T = TypeVar("T")
AnyCoro = Callable[[], Awaitable[T]]


class RateLimiter:
    """
    Async rate limiter with burst capacity to prevent IB API throttling.
    
    IB has strict rate limits:
    - Historical data: ~50 requests per 10 minutes
    - Market data: ~100 concurrent subscriptions
    - Orders: Variable based on account type
    
    Example:
        hist_limiter = RateLimiter(rate_per_sec=0.1, burst=2)  # 6 requests/min
        
        async with hist_limiter:
            data = await ib.reqHistoricalData(...)
    """
    
    def __init__(self, rate_per_sec: float, burst: int = 1) -> None:
        """
        Initialize rate limiter.
        
        Args:
            rate_per_sec: Maximum requests per second (can be fractional)
            burst: Maximum burst requests before rate limiting kicks in
        """
        self._min_interval = 1.0 / max(rate_per_sec, 1e-9)
        self._last = 0.0
        self._lock = asyncio.Lock()
        self._sem = asyncio.Semaphore(burst)
        
        logger.debug(
            f"RateLimiter initialized: {rate_per_sec:.3f} req/sec, "
            f"burst={burst}, min_interval={self._min_interval:.3f}s"
        )

    async def __aenter__(self):
        """Enter async context - acquire semaphore and enforce rate limit."""
        await self._sem.acquire()
        async with self._lock:
            now = time.perf_counter()
            delay = max(0.0, self._min_interval - (now - self._last))
            if delay > 0:
                logger.debug(f"Rate limiting: sleeping {delay:.3f}s")
                await asyncio.sleep(delay)
            self._last = time.perf_counter()
        return self

    async def __aexit__(self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: TracebackType | None):
        """Exit async context - release semaphore."""
        self._sem.release()


async def gather_bounded(
    coros: Iterable[Awaitable[T]], 
    limit: int = 5,
    return_exceptions: bool = False
) -> list[T]:
    """
    Bounded concurrent execution to prevent overwhelming IB Gateway.
    
    IB Gateway can handle limited concurrent requests. This function
    ensures we don't exceed safe limits while maximizing throughput.
    
    Args:
        coros: Iterable of coroutines to execute
        limit: Maximum concurrent operations (default: 5)
        return_exceptions: If True, include exceptions in results
        
    Returns:
        List of results in same order as input
        
    Example:
        # Safe concurrent data retrieval
        tasks = [req_hist(stock(Symbol(sym))) for sym in symbols]
        results = await gather_bounded(tasks, limit=3)
    """
    sem = asyncio.Semaphore(limit)
    
    async def run(coro: Awaitable[T]) -> T:
        async with sem:
            return await coro
    
    coro_list = list(coros)  # Convert to list to get count
    logger.debug(f"Running {len(coro_list)} tasks with concurrency limit {limit}")
    
    try:
        result = await asyncio.gather(
            *(run(coro) for coro in coro_list),
            return_exceptions=return_exceptions
        )
        return cast(list[T], result)
    except Exception as e:
        logger.error(f"gather_bounded failed: {e}")
        raise


async def with_retry(
    fn: AnyCoro[T], 
    *, 
    retries: int = 3, 
    backoff: float = 0.5,
    exceptions: tuple[type[Exception], ...] = (Exception,)
) -> T:
    """
    Retry coroutine with exponential backoff.
    
    IB operations can fail due to network issues, temporary overload,
    or connection problems. This provides intelligent retry logic.
    
    Args:
        fn: Async function to retry (no-args lambda)
        retries: Maximum retry attempts
        backoff: Initial backoff delay (doubles each retry)
        exceptions: Exception types to retry on
        
    Returns:
        Function result on success
        
    Raises:
        Last exception after all retries exhausted
        
    Example:
        result = await with_retry(
            lambda: req_hist(contract),
            retries=3,
            backoff=1.0
        )
    """
    last_exception = None
    
    for attempt in range(retries + 1):
        try:
            if attempt > 0:
                delay = backoff * (2 ** (attempt - 1))
                logger.debug(f"Retry attempt {attempt}/{retries} after {delay:.1f}s")
                await asyncio.sleep(delay)
            
            return await fn()
            
        except exceptions as e:
            last_exception = e
            if attempt == retries:
                logger.error(f"All {retries} retry attempts failed: {e}")
                break
            else:
                logger.warning(f"Attempt {attempt + 1} failed: {e}, retrying...")
    
    # This should never be None due to loop logic, but satisfy type checker
    assert last_exception is not None
    raise last_exception


async def with_timeout(
    coro: Awaitable[T], 
    timeout: float,
    timeout_msg: str | None = None
) -> T:
    """
    Add timeout to coroutine with custom error message.
    
    Args:
        coro: Coroutine to execute
        timeout: Timeout in seconds
        timeout_msg: Custom timeout message
        
    Returns:
        Coroutine result
        
    Raises:
        asyncio.TimeoutError: If timeout exceeded
    """
    try:
        return await asyncio.wait_for(coro, timeout=timeout)
    except asyncio.TimeoutError:
        msg = timeout_msg or f"Operation timed out after {timeout}s"
        logger.error(msg)
        raise asyncio.TimeoutError(msg)


class AsyncContextManager:
    """
    Helper for ensuring proper cleanup in async operations.
    
    Example:
        async with AsyncContextManager(setup_fn, cleanup_fn):
            # Do work
            pass
    """
    
    def __init__(
        self, 
        setup_fn: Callable[[], Awaitable[Any]] | None = None,
        cleanup_fn: Callable[[], Awaitable[Any]] | None = None
    ):
        self.setup_fn = setup_fn
        self.cleanup_fn = cleanup_fn
        
    async def __aenter__(self):
        if self.setup_fn:
            return await self.setup_fn()
        return self
        
    async def __aexit__(self, exc_type: type[BaseException] | None, exc_val: BaseException | None, exc_tb: TracebackType | None):
        if self.cleanup_fn:
            try:
                await self.cleanup_fn()
            except Exception as e:
                logger.error(f"Cleanup failed: {e}")


# Pre-configured rate limiters for common IB operations
# These are conservative defaults - adjust based on your IB account limits

# Historical data: IB allows ~50 requests per 10 minutes
HIST_DATA_LIMITER = RateLimiter(rate_per_sec=0.08, burst=2)  # ~5 req/min

# Market data subscriptions: More permissive but still bounded
MARKET_DATA_LIMITER = RateLimiter(rate_per_sec=2.0, burst=5)  # 2 req/sec

# Contract details: Moderate rate limit
CONTRACT_DETAILS_LIMITER = RateLimiter(rate_per_sec=1.0, burst=3)  # 1 req/sec

# Order operations: Conservative for safety
ORDER_LIMITER = RateLimiter(rate_per_sec=0.5, burst=1)  # 0.5 req/sec


# Export commonly used items
__all__ = [
    "RateLimiter",
    "gather_bounded", 
    "with_retry",
    "with_timeout",
    "AsyncContextManager",
    "HIST_DATA_LIMITER",
    "MARKET_DATA_LIMITER", 
    "CONTRACT_DETAILS_LIMITER",
    "ORDER_LIMITER",
]
