"""
Functional tests for src/core/connection_pool.py
Covers multi-acquire/release, pool exhaustion, timeouts, and circuit breaker logic.
All IB dependencies are mocked/faked.
"""

import time

import pytest

from src.core.connection_pool import (
    CircuitBreaker,
    ConnectionConfig,
    ConnectionPool,
    ConnectionPriority,
    ConnectionState,
)


class DummyConnection:
    def __init__(self, client_id):
        self.client_id = client_id
        self.active = True

    def close(self):
        self.active = False


@pytest.fixture
def pool():
    # Use small pool for exhaustion test
    config = ConnectionConfig(
        max_connections=2, min_connections=1, connection_timeout=0.1
    )
    pool = ConnectionPool(config)
    # Patch connection creation to use DummyConnection
    pool._connections = {i: DummyConnection(i) for i in range(config.max_connections)}
    pool._available_connections = list(pool._connections.keys())
    return pool


def test_acquire_release(pool):
    conn1 = pool.get_connection(ConnectionPriority.NORMAL)
    conn2 = pool.get_connection(ConnectionPriority.NORMAL)
    assert conn1 is not None and conn2 is not None
    # Track client_id for returning
    pool.return_connection(conn1.client_id)
    pool.return_connection(conn2.client_id)
    # Should be able to reacquire
    conn3 = pool.get_connection(ConnectionPriority.NORMAL)
    assert conn3 is not None


def test_pool_exhaustion(pool):
    conn1 = pool.get_connection(ConnectionPriority.NORMAL)
    conn2 = pool.get_connection(ConnectionPriority.NORMAL)
    from src.core.error_handler import TradingSystemError

    with pytest.raises(TradingSystemError):
        pool.get_connection(ConnectionPriority.NORMAL, timeout=0.01)
    pool.return_connection(conn1.client_id)
    pool.return_connection(conn2.client_id)


def test_circuit_breaker():
    cb = CircuitBreaker(failure_threshold=2, timeout=0.01)

    from src.core.error_handler import TradingSystemError

    def fail():
        raise TradingSystemError("fail")

    # Two failures should open breaker
    with pytest.raises(TradingSystemError):
        cb.call(fail)
    with pytest.raises(TradingSystemError):
        cb.call(fail)
    assert cb.state == ConnectionState.OPEN
    # Wait for timeout, should reset
    time.sleep(0.02)
    with pytest.raises(TradingSystemError):
        cb.call(fail)
    assert cb.state in [ConnectionState.HALF_OPEN, ConnectionState.OPEN]
