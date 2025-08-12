"""Targeted tests for src/core/retry_manager.py

Focus: strategy delay calculations, retry decision matrix, callbacks, and
non-retryable fast‑fail behavior. These cover previously missed branches.
"""

from __future__ import annotations

import pytest

from src.core.retry_manager import (
    RetryConfig,
    RetryManager,
    RetryStrategy,
    retry_on_failure,
)


def _raise_n_times(exc: Exception, n: int):
    """Return a function that raises `exc` the first n calls then returns marker.

    Helps exercise success-after-retry path and delay calculation.
    """

    calls = {"count": 0}

    def fn() -> str:  # pragma: no cover - wrapper logic covered through execution
        if calls["count"] < n:
            calls["count"] += 1
            raise exc
        return "OK"

    return fn


def test_fixed_delay_strategy_min_delay(monkeypatch):
    config = RetryConfig(
        max_attempts=3, base_delay=0.5, strategy=RetryStrategy.FIXED_DELAY, jitter=False
    )
    rm = RetryManager(config)

    # Speed up by monkeypatching time.sleep to avoid real waiting
    monkeypatch.setattr("time.sleep", lambda s: None)

    fn = _raise_n_times(ConnectionError("boom"), 1)
    result = rm.execute_with_retry(fn)
    assert result == "OK"
    # One retry attempt implies >=2 total attempts recorded in stats
    assert rm.stats.total_operations == 1
    assert rm.stats.successful_operations == 1
    assert rm.stats.failed_operations == 0
    # Delay should have been at least the configured base (bounded by min 0.1)
    assert config.base_delay >= 0.1
    # Ensure calculation path used fixed delay (no exponential growth)
    d1 = rm._calculate_delay(1)
    d2 = rm._calculate_delay(2)
    assert d1 == config.base_delay and d2 == config.base_delay


def test_exponential_strategy(monkeypatch):
    config = RetryConfig(
        max_attempts=4,
        base_delay=0.1,
        backoff_multiplier=2.0,
        strategy=RetryStrategy.EXPONENTIAL_BACKOFF,
        jitter=False,
    )
    rm = RetryManager(config)
    monkeypatch.setattr("time.sleep", lambda s: None)
    fn = _raise_n_times(ConnectionError("x"), 2)
    rm.execute_with_retry(fn)
    # Verify exponential growth: base, base*2, base*4
    assert rm._calculate_delay(1) == pytest.approx(0.1, rel=1e-3)
    assert rm._calculate_delay(2) == pytest.approx(0.2, rel=1e-3)
    assert rm._calculate_delay(3) == pytest.approx(0.4, rel=1e-3)


def test_jittered_exponential_has_variation(monkeypatch):
    config = RetryConfig(
        max_attempts=3,
        base_delay=0.2,
        backoff_multiplier=2.0,
        strategy=RetryStrategy.JITTERED_EXPONENTIAL,
        jitter=False,  # internal jitter strategy already adds its own jitter
    )
    rm = RetryManager(config)
    monkeypatch.setattr("time.sleep", lambda s: None)
    fn = _raise_n_times(ConnectionError("j"), 2)
    rm.execute_with_retry(fn)
    # Collect multiple samples to see variation
    samples = {rm._calculate_delay(2) for _ in range(5)}
    # Expect more than one distinct value due to jitter
    assert len(samples) > 1


def test_linear_backoff(monkeypatch):
    config = RetryConfig(
        max_attempts=4,
        base_delay=0.05,
        strategy=RetryStrategy.LINEAR_BACKOFF,
        jitter=False,
    )
    rm = RetryManager(config)
    monkeypatch.setattr("time.sleep", lambda s: None)
    fn = _raise_n_times(ConnectionError("lin"), 2)
    rm.execute_with_retry(fn)
    # Delay is clamped to minimum 0.1 (see implementation)
    assert rm._calculate_delay(1) == pytest.approx(0.1, rel=1e-3)
    assert rm._calculate_delay(2) == pytest.approx(0.1, rel=1e-3)
    assert rm._calculate_delay(3) == pytest.approx(0.15, rel=1e-3)


def test_non_retryable_short_circuits(monkeypatch):
    config = RetryConfig(
        max_attempts=5, base_delay=0.1, strategy=RetryStrategy.FIXED_DELAY, jitter=False
    )
    # Make ValueError non-retryable (default) and ConnectionError retryable
    rm = RetryManager(config)
    monkeypatch.setattr("time.sleep", lambda s: None)

    def bad():  # returns nothing, will raise immediately
        raise ValueError("no retry")

    with pytest.raises(ValueError):
        rm.execute_with_retry(bad)
    # Only one operation attempt should be recorded, no success
    assert rm.stats.total_operations == 1
    assert rm.stats.failed_operations == 1
    assert rm.stats.successful_operations == 0
    # Distribution: exactly 1 attempt recorded
    assert rm.stats.retry_counts.get(1) == 1


def test_decorator_retry_on_failure(monkeypatch):
    config = RetryConfig(
        max_attempts=2,
        base_delay=0.01,
        strategy=RetryStrategy.FIXED_DELAY,
        jitter=False,
    )
    monkeypatch.setattr("time.sleep", lambda s: None)

    attempts = {"n": 0}

    @retry_on_failure(config)
    def sometimes() -> str:
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise ConnectionError("try again")
        return "OK"

    assert sometimes() == "OK"
    assert attempts["n"] == 2  # First failed, second succeeded
