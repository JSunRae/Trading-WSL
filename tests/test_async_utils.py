import asyncio
import time

import pytest

from src.infra.async_utils import RateLimiter, gather_bounded, with_retry, with_timeout


@pytest.mark.asyncio
async def test_rate_limiter_basic():
    limiter = RateLimiter(rate_per_sec=1.0, burst=1)
    t0 = time.monotonic()
    async with limiter:
        pass
    async with limiter:
        pass
    t1 = time.monotonic()
    assert t1 - t0 >= 1.0  # second call should be rate-limited


@pytest.mark.asyncio
async def test_rate_limiter_reset():
    limiter = RateLimiter(rate_per_sec=2.0, burst=1)
    async with limiter:
        pass
    await asyncio.sleep(0.6)
    t0 = time.monotonic()
    async with limiter:
        pass
    t1 = time.monotonic()
    assert t1 - t0 < 0.2  # should not be rate-limited after wait


@pytest.mark.asyncio
async def test_gather_bounded_parallel():
    concurrency = 0
    max_concurrency = 0
    lock = asyncio.Lock()

    async def task(i: int) -> int:
        nonlocal concurrency, max_concurrency
        async with lock:
            concurrency += 1
            max_concurrency = max(max_concurrency, concurrency)
        await asyncio.sleep(0.1)
        async with lock:
            concurrency -= 1
        return i

    coros = [task(i) for i in range(5)]
    results = await gather_bounded(coros, limit=2)
    assert sorted(results) == list(range(5))
    assert max_concurrency <= 2


@pytest.mark.asyncio
async def test_with_retry_success_after_failures():
    attempts = []

    async def fn():
        attempts.append(time.monotonic())
        if len(attempts) < 3:
            raise ValueError("fail")
        return "ok"

    result = await with_retry(
        lambda: fn(), retries=5, backoff=0.01, exceptions=(ValueError,)
    )
    assert result == "ok"
    assert len(attempts) == 3


@pytest.mark.asyncio
async def test_with_timeout_raises():
    async def slow():
        await asyncio.sleep(0.2)

    with pytest.raises(asyncio.TimeoutError):
        await with_timeout(slow(), timeout=0.05)
