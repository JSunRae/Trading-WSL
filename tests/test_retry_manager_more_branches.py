from __future__ import annotations

from src.core.retry_manager import RetryConfig, RetryManager


def test_retry_manager_exhausts_and_records_stats(monkeypatch):  # noqa: ANN001
    # Deterministic delays (no jitter)
    cfg = RetryConfig(max_attempts=3, base_delay=0.01, jitter=False)
    rm = RetryManager(cfg)

    calls = {"n": 0}

    def always_fail() -> None:
        calls["n"] += 1
        raise ConnectionError("net down")

    # Speed up sleep
    monkeypatch.setattr("time.sleep", lambda _x: None)

    try:
        rm.execute_with_retry(always_fail)
    except ConnectionError:
        pass

    # 3 attempts should be recorded as failed
    s = rm.stats.get_summary()
    assert s["total_operations"] == 1
    assert s["failure_types"].get("ConnectionError", 0) == 1


def test_retry_manager_non_retryable_short_circuits():
    cfg = RetryConfig(max_attempts=5, base_delay=0.01, jitter=False)
    rm = RetryManager(cfg)

    def raises_value_error():
        raise ValueError("nope")

    try:
        rm.execute_with_retry(raises_value_error)
    except ValueError:
        pass

    s = rm.stats.get_summary()
    assert s["total_operations"] == 1
    # Should have only attempted once due to non-retryable
    assert s["average_attempts"] <= 1.0
