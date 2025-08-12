from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.core.performance import LRUCache, get_performance_monitor, performance_monitor


def test_performance_monitor_records_success_and_failure(tmp_path: Path):
    monitor = get_performance_monitor()
    # Ensure a clean slate for deterministic assertions
    monitor.metrics.clear()

    calls: dict[str, int] = {"n": 0}

    @performance_monitor
    def sometimes_fails(x: int) -> int:
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("boom")
        return x * 2

    # First call fails but still recorded
    try:
        sometimes_fails(2)
    except RuntimeError:
        pass
    # Second call succeeds
    assert sometimes_fails(3) == 6

    stats = monitor.get_system_stats()
    assert stats.get("total_calls", 0) >= 2
    assert stats.get("successful_calls", 0) >= 1

    # Export metrics JSON
    out_file = tmp_path / "perf.json"
    path = monitor.export_metrics(out_file)
    assert path.exists()
    data = json.loads(path.read_text())
    assert "metrics" in data and isinstance(data["metrics"], list)


def test_lru_cache_eviction_and_ttl(monkeypatch):  # noqa: ANN001
    cache = LRUCache(max_size=2, default_ttl=1)
    cache.put("a", 1)
    cache.put("b", 2)
    # Access 'a' to increase its access_count so 'b' becomes LRU
    assert cache.get("a") == 1
    # Insert 'c' causing eviction of least accessed key ('b')
    cache.put("c", 3)
    assert cache.get("b") is None
    assert cache.get("a") == 1
    assert cache.get("c") == 3

    # Simulate TTL expiry by monkeypatching datetime.now used in CacheEntry.is_expired
    import src.core.performance as perf_mod

    real_dt = perf_mod.datetime

    class FakeDateTime(real_dt.__class__):  # type: ignore[misc]
        @classmethod
        def now(cls, tz: Any | None = None):
            # Advance time by 2 seconds to force expiry
            return real_dt.now(tz) + perf_mod.timedelta(seconds=2)

    monkeypatch.setattr(perf_mod, "datetime", FakeDateTime)
    # size() also triggers cleanup of expired entries
    assert cache.size() == 0
