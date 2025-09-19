from collections.abc import Iterable

import pytest

from src.infra.ib_conn import get_ib_connect_plan


def _has_any(items: Iterable[int], candidates: set[int]) -> bool:
    s = set(int(x) for x in items)
    return any(p in s for p in candidates)


@pytest.fixture()
def clear_env(monkeypatch: pytest.MonkeyPatch):
    # Ensure env is clean for each test
    for k in [
        "IB_HOST",
        "IB_PORT",
        "IB_CLIENT_ID",
        "IB_CONNECT_TIMEOUT",
        "IB_ALLOW_WINDOWS",
    ]:
        monkeypatch.delenv(k, raising=False)


def test_plan_linux_first_excludes_windows_by_default(
    monkeypatch: pytest.MonkeyPatch, clear_env: None
):
    # No windows allowed by default; explicitly set an invalid IB_PORT to ensure filtering
    monkeypatch.setenv("IB_PORT", "0")
    plan = get_ib_connect_plan()
    candidates = list(plan["candidates"])

    # No invalid ports
    assert all(1 <= int(p) <= 65535 for p in candidates), candidates
    # Linux-first defaults include 4002 and 7497
    assert 4002 in candidates
    assert 7497 in candidates
    # Windows/portproxy ports excluded by default
    assert 4003 not in candidates and 4004 not in candidates


def test_plan_windows_opt_in_includes_portproxy(
    monkeypatch: pytest.MonkeyPatch, clear_env: None
):
    monkeypatch.setenv("IB_ALLOW_WINDOWS", "1")
    plan = get_ib_connect_plan()
    candidates = list(plan["candidates"])

    assert 4002 in candidates and 7497 in candidates
    assert _has_any(candidates, {4003, 4004})


def test_env_port_included_when_valid(monkeypatch: pytest.MonkeyPatch, clear_env: None):
    monkeypatch.setenv("IB_PORT", "5000")
    plan = get_ib_connect_plan()
    candidates = list(plan["candidates"])
    # Valid env port appears (at least once) and is valid range
    assert 5000 in candidates
    assert all(1 <= int(p) <= 65535 for p in candidates)


def test_env_port_invalid_is_filtered(monkeypatch: pytest.MonkeyPatch, clear_env: None):
    # Invalid numeric 0 and non-numeric should be filtered out
    monkeypatch.setenv("IB_PORT", "0")
    plan = get_ib_connect_plan()
    candidates = list(plan["candidates"])
    assert 0 not in candidates
    assert all(1 <= int(p) <= 65535 for p in candidates)
