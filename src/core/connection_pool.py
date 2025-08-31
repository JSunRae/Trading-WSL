#!/usr/bin/env python3
"""
Connection Pool Manager for Interactive Brokers

This module implements connection pooling and circuit breakers to address
the root cause of connection errors in the trading system.
"""

import logging
import sys
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.config import get_config
from src.core.error_handler import TradingSystemError, get_error_handler, handle_error


class ConnectionState(Enum):
    """Connection states for circuit breaker pattern"""

    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Circuit is open, preventing connections
    HALF_OPEN = "half_open"  # Testing if connection has recovered


class ConnectionPriority(Enum):
    """Priority levels for connection requests"""

    CRITICAL = 1  # Market data, order execution
    HIGH = 2  # Historical data downloads
    NORMAL = 3  # General queries
    LOW = 4  # Background tasks


@dataclass
class ConnectionMetrics:
    """Metrics for monitoring connection health"""

    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    average_response_time: float = 0.0
    last_failure_time: datetime | None = None
    consecutive_failures: int = 0
    uptime_percentage: float = 100.0


@dataclass
class ConnectionConfig:
    """Configuration for connection pool"""

    max_connections: int = 5
    min_connections: int = 1
    connection_timeout: float = 30.0
    retry_attempts: int = 3
    retry_delay: float = 1.0
    circuit_breaker_threshold: int = 5
    circuit_breaker_timeout: float = 60.0
    health_check_interval: float = 30.0


class CircuitBreaker:
    """Circuit breaker pattern for connection fault tolerance"""

    def __init__(self, failure_threshold: int = 5, timeout: float = 60.0):
        self.failure_threshold = failure_threshold
        self.timeout = timeout
        self.state = ConnectionState.CLOSED
        self.failure_count = 0
        self.last_failure_time = None
        self.logger = logging.getLogger(__name__)

    def call(self, func: Callable, *args, **kwargs) -> Any:
        """Execute function with circuit breaker protection"""

        if self.state == ConnectionState.OPEN:
            if self._should_attempt_reset():
                self.state = ConnectionState.HALF_OPEN
                self.logger.info("Circuit breaker entering HALF_OPEN state")
            else:
                raise TradingSystemError(
                    "Circuit breaker is OPEN - connection unavailable",
                    context={
                        "failure_count": self.failure_count,
                        "last_failure": self.last_failure_time,
                        "timeout_remaining": self._get_timeout_remaining(),
                    },
                )

        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result

        except Exception:
            self._on_failure()
            raise

    def _should_attempt_reset(self) -> bool:
        """Check if we should attempt to reset the circuit breaker"""
        if self.last_failure_time is None:
            return True

        time_since_failure = time.time() - self.last_failure_time.timestamp()
        return time_since_failure >= self.timeout

    def _get_timeout_remaining(self) -> float:
        """Get remaining timeout duration"""
        if self.last_failure_time is None:
            return 0.0

        elapsed = time.time() - self.last_failure_time.timestamp()
        return max(0.0, self.timeout - elapsed)

    def _on_success(self):
        """Handle successful operation"""
        if self.state == ConnectionState.HALF_OPEN:
            self.state = ConnectionState.CLOSED
            self.failure_count = 0
            self.logger.info("Circuit breaker reset to CLOSED state")

    def _on_failure(self):
        """Handle failed operation"""
        self.failure_count += 1
        self.last_failure_time = datetime.now()

        if self.failure_count >= self.failure_threshold:
            self.state = ConnectionState.OPEN
            self.logger.warning(
                f"Circuit breaker OPENED after {self.failure_count} failures"
            )


class ConnectionPool:
    """High-performance connection pool for Interactive Brokers"""

    def __init__(self, config: ConnectionConfig | None = None):
        self.config = config or ConnectionConfig()
        self.error_handler = get_error_handler()
        self.logger = logging.getLogger(__name__)

        # Connection management
        self._connections: dict[int, Any] = {}  # clientId -> connection
        self._available_connections: list[int] = []
        self._busy_connections: dict[int, float] = {}  # clientId -> start_time
        self._connection_metrics: dict[int, ConnectionMetrics] = {}

        # Thread safety
        self._lock = threading.RLock()
        self._shutdown = False

        # Circuit breaker
        self.circuit_breaker = CircuitBreaker(
            failure_threshold=self.config.circuit_breaker_threshold,
            timeout=self.config.circuit_breaker_timeout,
        )

        # Health monitoring
        self._health_check_thread = None
        self._start_health_monitoring()

    def get_connection(
        self,
        priority: ConnectionPriority = ConnectionPriority.NORMAL,
        timeout: float | None = None,
    ) -> "ManagedConnection":
        """Get a connection from the pool with priority handling"""

        timeout = timeout or self.config.connection_timeout
        start_time = time.time()

        while time.time() - start_time < timeout:
            with self._lock:
                if self._shutdown:
                    raise TradingSystemError("Connection pool is shut down")

                # Try to get an available connection
                available_conn = self._get_available_connection(priority)
                if available_conn is not None:
                    return available_conn

                # If no connections available, try to create one
                if len(self._connections) < self.config.max_connections:
                    new_conn = self._create_connection()
                    if new_conn is not None:
                        return new_conn

            # Wait a bit before retrying
            time.sleep(0.1)

        raise TradingSystemError(
            f"Connection timeout after {timeout}s",
            context={
                "priority": priority.name,
                "active_connections": len(self._busy_connections),
                "total_connections": len(self._connections),
            },
        )

    def _get_available_connection(
        self, priority: ConnectionPriority
    ) -> Optional["ManagedConnection"]:
        """Get an available connection based on priority"""

        if not self._available_connections:
            return None

        # For critical operations, try to free up a connection if needed
        if priority == ConnectionPriority.CRITICAL and not self._available_connections:
            self._handle_critical_priority()

        if self._available_connections:
            client_id = self._available_connections.pop(0)
            connection = self._connections[client_id]
            self._busy_connections[client_id] = time.time()

            return ManagedConnection(self, client_id, connection)

        return None

    def _handle_critical_priority(self):
        """Handle critical priority requests by freeing up connections"""

        # Find the longest running non-critical connection
        longest_running = None
        longest_time = 0

        for client_id, start_time in self._busy_connections.items():
            running_time = time.time() - start_time
            if running_time > longest_time:
                longest_time = running_time
                longest_running = client_id

        # If found a long-running connection, mark it for interruption
        if longest_running and longest_time > 30:  # 30 seconds threshold
            self.logger.warning(
                f"Interrupting long-running connection {longest_running} for critical request"
            )
            # Note: Actual interruption would depend on IB API implementation

    def _create_connection(self) -> Optional["ManagedConnection"]:
        """Create a new connection"""

        try:
            # Circuit breaker protection
            def create_ib_connection():
                return self._create_ib_connection()

            connection = self.circuit_breaker.call(create_ib_connection)

            if connection is not None:
                client_id = len(self._connections) + 1000  # Start from 1000
                self._connections[client_id] = connection
                self._connection_metrics[client_id] = ConnectionMetrics()
                self._busy_connections[client_id] = time.time()

                self.logger.info(f"Created new connection with client_id {client_id}")
                return ManagedConnection(self, client_id, connection)

        except Exception as e:
            handle_error(e, module=__name__, function="_create_connection")

        return None

    def _create_ib_connection(self):
        """Create actual IB connection (placeholder for IB API integration)"""

        # This would integrate with the actual IB API
        # For now, return a mock connection for testing
        config = get_config()

        # Simulate connection creation
        time.sleep(0.1)  # Simulate connection time

        mock_connection = {
            "host": config.ib_connection.host,
            "port": config.ib_connection.port,
            "paper_trading": config.ib_connection.paper_trading,
            "connected": True,
            "created_at": datetime.now(),
        }

        return mock_connection

    def return_connection(self, client_id: int, had_error: bool = False):
        """Return a connection to the pool"""

        with self._lock:
            if client_id in self._busy_connections:
                # Update metrics
                duration = time.time() - self._busy_connections[client_id]
                self._update_metrics(client_id, duration, had_error)

                # Return to available pool
                del self._busy_connections[client_id]

                if not had_error and client_id in self._connections:
                    self._available_connections.append(client_id)
                else:
                    # Remove faulty connection
                    self._remove_connection(client_id)

    def _update_metrics(self, client_id: int, duration: float, had_error: bool):
        """Update connection metrics"""

        if client_id not in self._connection_metrics:
            self._connection_metrics[client_id] = ConnectionMetrics()

        metrics = self._connection_metrics[client_id]
        metrics.total_requests += 1

        if had_error:
            metrics.failed_requests += 1
            metrics.last_failure_time = datetime.now()
            metrics.consecutive_failures += 1
        else:
            metrics.successful_requests += 1
            metrics.consecutive_failures = 0

        # Update average response time
        total_successful = metrics.successful_requests
        if total_successful > 0:
            current_avg = metrics.average_response_time
            metrics.average_response_time = (
                current_avg * (total_successful - 1) + duration
            ) / total_successful

        # Update uptime percentage
        if metrics.total_requests > 0:
            metrics.uptime_percentage = (
                metrics.successful_requests / metrics.total_requests * 100
            )

    def _remove_connection(self, client_id: int):
        """Remove a connection from the pool"""

        if client_id in self._connections:
            # Cleanup connection
            connection = self._connections[client_id]
            try:
                # This would call actual IB API disconnect
                connection["connected"] = False
            except Exception:
                # Swallow any cleanup error to ensure removal proceeds
                pass

            del self._connections[client_id]

            if client_id in self._available_connections:
                self._available_connections.remove(client_id)

            self.logger.info(f"Removed connection {client_id} from pool")

    def _start_health_monitoring(self):
        """Start health monitoring thread"""

        def health_check():
            while not self._shutdown:
                try:
                    self._perform_health_check()
                    time.sleep(self.config.health_check_interval)
                except Exception as e:
                    handle_error(e, module=__name__, function="health_check")

        self._health_check_thread = threading.Thread(target=health_check, daemon=True)
        self._health_check_thread.start()

    def _perform_health_check(self):
        """Perform health check on all connections"""

        with self._lock:
            unhealthy_connections = []

            for client_id, metrics in self._connection_metrics.items():
                # Check for unhealthy connections
                if metrics.consecutive_failures >= 3 or metrics.uptime_percentage < 80:
                    unhealthy_connections.append(client_id)

            # Remove unhealthy connections
            for client_id in unhealthy_connections:
                self.logger.warning(f"Removing unhealthy connection {client_id}")
                self._remove_connection(client_id)

            # Ensure minimum connections
            while (
                len(self._connections) < self.config.min_connections
                and len(self._connections) < self.config.max_connections
            ):
                self._create_connection()

    def get_pool_status(self) -> dict[str, Any]:
        """Get current pool status"""

        with self._lock:
            return {
                "total_connections": len(self._connections),
                "available_connections": len(self._available_connections),
                "busy_connections": len(self._busy_connections),
                "circuit_breaker_state": self.circuit_breaker.state.value,
                "circuit_breaker_failures": self.circuit_breaker.failure_count,
                "metrics": {
                    client_id: {
                        "total_requests": metrics.total_requests,
                        "success_rate": metrics.uptime_percentage,
                        "avg_response_time": metrics.average_response_time,
                        "consecutive_failures": metrics.consecutive_failures,
                    }
                    for client_id, metrics in self._connection_metrics.items()
                },
            }

    def shutdown(self):
        """Gracefully shutdown the connection pool"""

        self.logger.info("Shutting down connection pool...")

        with self._lock:
            self._shutdown = True

            # Close all connections
            for client_id in list(self._connections.keys()):
                self._remove_connection(client_id)

            self._connections.clear()
            self._available_connections.clear()
            self._busy_connections.clear()

        # Wait for health check thread to finish
        if self._health_check_thread and self._health_check_thread.is_alive():
            self._health_check_thread.join(timeout=5.0)

        self.logger.info("Connection pool shutdown complete")


class ManagedConnection:
    """Managed connection with automatic return to pool"""

    def __init__(self, pool: ConnectionPool, client_id: int, connection: Any):
        self.pool = pool
        self.client_id = client_id
        self.connection = connection
        self._returned = False
        self._had_error = False

    def __enter__(self):
        return self.connection

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            self._had_error = True
        self.return_to_pool()

    def return_to_pool(self):
        """Return connection to pool"""
        if not self._returned:
            self.pool.return_connection(self.client_id, self._had_error)
            self._returned = True

    def mark_error(self):
        """Mark this connection as having an error"""
        self._had_error = True


# Global connection pool instance
_connection_pool: ConnectionPool | None = None


def get_connection_pool() -> ConnectionPool:
    """Get the global connection pool instance"""
    global _connection_pool

    if _connection_pool is None:
        _connection_pool = ConnectionPool()

    return _connection_pool


def with_connection(priority: ConnectionPriority = ConnectionPriority.NORMAL):
    """Decorator for functions that need IB connections"""

    def decorator(func):
        def wrapper(*args, **kwargs):
            pool = get_connection_pool()

            with pool.get_connection(priority) as connection:
                # Inject connection as keyword argument
                kwargs["connection"] = connection
                return func(*args, **kwargs)

        return wrapper

    return decorator


# Example usage functions


@with_connection(ConnectionPriority.CRITICAL)
def get_market_data(symbol: str, timeframe: str, connection=None):
    """Example function using connection pool for market data"""
    # This would use the actual IB API
    return f"Market data for {symbol} {timeframe} via connection {connection}"


@with_connection(ConnectionPriority.HIGH)
def download_historical_data(
    symbol: str, start_date: str, end_date: str, connection=None
):
    """Example function using connection pool for historical data"""
    # This would use the actual IB API
    return f"Historical data for {symbol} from {start_date} to {end_date}"


def main():
    """Demo the connection pool system"""

    print("🔌 IB Connection Pool Demo")
    print("=" * 40)

    # Get pool instance
    pool = get_connection_pool()

    # Show initial status
    status = pool.get_pool_status()
    print("📊 Pool Status:")
    print(f"  Total connections: {status['total_connections']}")
    print(f"  Available: {status['available_connections']}")
    print(f"  Circuit breaker: {status['circuit_breaker_state']}")

    # Test connection usage
    print("\n🧪 Testing connection operations...")

    try:
        # Test normal operations
        result1 = get_market_data("AAPL", "1 min")
        print(f"✅ {result1}")

        result2 = download_historical_data("TSLA", "2024-01-01", "2024-01-31")
        print(f"✅ {result2}")

        # Show updated status
        status = pool.get_pool_status()
        print("\n📈 Updated Status:")
        print(
            f"  Total requests: {sum(m['total_requests'] for m in status['metrics'].values())}"
        )
        print(
            f"  Average success rate: {sum(m['success_rate'] for m in status['metrics'].values()) / len(status['metrics']) if status['metrics'] else 0:.1f}%"
        )

    except Exception as e:
        print(f"❌ Error: {e}")

    finally:
        # Cleanup
        pool.shutdown()

    print("\n🎉 Connection pool demo complete!")


if __name__ == "__main__":
    main()
