#!/usr/bin/env python3
"""
Integrated Error Handling System

This module integrates connection pooling, circuit breakers, and retry mechanisms
to provide comprehensive error handling that addresses root causes rather than symptoms.
"""

import logging
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.config import get_config
from src.core.connection_pool import ConnectionPriority, get_connection_pool
from src.core.error_handler import TradingSystemError, get_error_handler, handle_error
from src.core.retry_manager import RetryConfig, get_retry_manager


class SystemHealth(Enum):
    """Overall system health status"""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    CRITICAL = "critical"


class ServiceStatus(Enum):
    """Individual service status"""

    OPERATIONAL = "operational"
    SLOW = "slow"
    FAILING = "failing"
    DOWN = "down"


@dataclass
class HealthMetrics:
    """Health metrics for monitoring"""

    timestamp: datetime = field(default_factory=datetime.now)
    success_rate: float = 100.0
    average_response_time: float = 0.0
    error_rate: float = 0.0
    connection_pool_health: float = 100.0
    circuit_breaker_open: bool = False
    total_requests: int = 0
    failed_requests: int = 0

    def get_health_score(self) -> float:
        """Calculate overall health score (0-100)"""
        # Weight different factors
        weights = {
            "success_rate": 0.4,
            "response_time": 0.2,
            "connection_health": 0.2,
            "circuit_breaker": 0.2,
        }

        # Calculate response time score (inverse relationship)
        response_score = max(0, 100 - (self.average_response_time * 10))

        # Circuit breaker penalty
        circuit_score = 0 if self.circuit_breaker_open else 100

        health_score = (
            self.success_rate * weights["success_rate"]
            + response_score * weights["response_time"]
            + self.connection_pool_health * weights["connection_health"]
            + circuit_score * weights["circuit_breaker"]
        )

        return max(0, min(100, health_score))

    def get_status(self) -> SystemHealth:
        """Get system health status based on metrics"""
        score = self.get_health_score()

        if score >= 90:
            return SystemHealth.HEALTHY
        elif score >= 70:
            return SystemHealth.DEGRADED
        elif score >= 40:
            return SystemHealth.UNHEALTHY
        else:
            return SystemHealth.CRITICAL


@dataclass
class ServiceConfig:
    """Configuration for individual services"""

    name: str
    retry_config: RetryConfig | None = None
    priority: ConnectionPriority = ConnectionPriority.NORMAL
    timeout: float = 30.0
    health_check_interval: float = 60.0
    failure_threshold: int = 5
    enable_circuit_breaker: bool = True


class IntegratedErrorHandler:
    """Integrated error handling system combining all strategies"""

    def __init__(self):
        self.config = get_config()
        self.error_handler = get_error_handler()
        self.connection_pool = get_connection_pool()
        self.retry_manager = get_retry_manager()
        self.logger = logging.getLogger(__name__)

        # Health monitoring
        self.health_metrics = HealthMetrics()
        self.service_metrics: dict[str, HealthMetrics] = {}
        self.service_configs: dict[str, ServiceConfig] = {}

        # Service registry
        self._register_default_services()

        # Health monitoring thread
        self._health_monitor_active = True
        self._start_health_monitoring()

    def _register_default_services(self):
        """Register default services with appropriate configurations"""

        # Market data service - critical priority
        self.register_service(
            ServiceConfig(
                name="market_data",
                retry_config=RetryConfig(
                    max_attempts=3,
                    base_delay=0.5,
                    strategy=RetryConfig().strategy,
                    retryable_exceptions=[ConnectionError, TimeoutError],
                ),
                priority=ConnectionPriority.CRITICAL,
                timeout=10.0,
                failure_threshold=3,
            )
        )

        # Historical data service - high priority
        self.register_service(
            ServiceConfig(
                name="historical_data",
                retry_config=RetryConfig(
                    max_attempts=5,
                    base_delay=2.0,
                    max_delay=30.0,
                    strategy=RetryConfig().strategy,
                ),
                priority=ConnectionPriority.HIGH,
                timeout=60.0,
                failure_threshold=5,
            )
        )

        # Order management service - critical priority
        self.register_service(
            ServiceConfig(
                name="order_management",
                retry_config=RetryConfig(
                    max_attempts=2,
                    base_delay=0.1,
                    max_delay=5.0,
                    strategy=RetryConfig().strategy,
                ),
                priority=ConnectionPriority.CRITICAL,
                timeout=5.0,
                failure_threshold=2,
            )
        )

        # Data persistence service - normal priority
        self.register_service(
            ServiceConfig(
                name="data_persistence",
                retry_config=RetryConfig(
                    max_attempts=3, base_delay=1.0, strategy=RetryConfig().strategy
                ),
                priority=ConnectionPriority.NORMAL,
                timeout=30.0,
                failure_threshold=10,
            )
        )

        # ML signal execution service - high priority (injection capable)
        self.register_service(
            ServiceConfig(
                name="ml_signal_execution",
                retry_config=RetryConfig(
                    max_attempts=2,
                    base_delay=0.2,
                    strategy=RetryConfig().strategy,
                ),
                priority=ConnectionPriority.HIGH,
                timeout=10.0,
                failure_threshold=5,
            )
        )

        # ML risk management service - high priority
        self.register_service(
            ServiceConfig(
                name="ml_risk_management",
                retry_config=RetryConfig(
                    max_attempts=2,
                    base_delay=0.2,
                    strategy=RetryConfig().strategy,
                ),
                priority=ConnectionPriority.HIGH,
                timeout=10.0,
                failure_threshold=5,
            )
        )

    def register_service(self, service_config: ServiceConfig):
        """Register a service with the error handling system"""
        self.service_configs[service_config.name] = service_config
        self.service_metrics[service_config.name] = HealthMetrics()
        self.logger.info(f"Registered service: {service_config.name}")

    def execute_service_operation(
        self,
        service_name: str,
        operation: Callable[..., Any],
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        """Execute a service operation with full error handling and registry support"""

        # Try to resolve service object from registry (for test/prod injection)
        try:
            from src.infra.service_registry import get_service

            service_obj = get_service(service_name)
        except Exception:
            service_obj = None

        if service_name not in self.service_configs:
            raise ValueError(f"Unknown service: {service_name}")

        service_config = self.service_configs[service_name]
        service_metrics = self.service_metrics[service_name]

        operation_start = time.time()

        try:
            # Wrap operation with connection pool and retry logic
            def wrapped_operation():
                # If the operation is already bound (method of instance), call directly
                is_bound = (
                    hasattr(operation, "__self__") and operation.__self__ is not None
                )  # type: ignore[attr-defined]
                if is_bound:
                    return operation(*args, **kwargs)
                # If a service object is registered, call without injecting it (method already has self)
                if service_obj is not None:
                    return operation(*args, **kwargs)
                # Otherwise obtain a connection and pass as first argument (legacy style free function)
                with self.connection_pool.get_connection(
                    service_config.priority
                ) as connection:
                    return operation(connection, *args, **kwargs)

            # Execute with retry
            if service_config.retry_config:
                retry_manager = self.retry_manager.__class__(
                    service_config.retry_config
                )
                result = retry_manager.execute_with_retry(wrapped_operation)
            else:
                result = wrapped_operation()

            # Record success
            duration = time.time() - operation_start
            self._record_operation_success(service_name, duration)

            return result

        except Exception as e:
            # Record failure
            duration = time.time() - operation_start
            self._record_operation_failure(service_name, e, duration)

            # Enhanced error context
            error_context = {
                "service": service_name,
                "operation": operation.__name__
                if hasattr(operation, "__name__")
                else str(operation),
                "duration": duration,
                "service_health": service_metrics.get_health_score(),
                "system_health": self.health_metrics.get_health_score(),
            }

            handle_error(
                e,
                module=__name__,
                function="execute_service_operation",
                context=error_context,
            )
            raise

    def _record_operation_success(self, service_name: str, duration: float) -> None:
        """Record successful operation metrics"""
        metrics = self.service_metrics[service_name]
        metrics.total_requests += 1

        # Update success-related metrics
        success_count = metrics.total_requests - metrics.failed_requests
        metrics.success_rate = (success_count / metrics.total_requests) * 100
        metrics.error_rate = (metrics.failed_requests / metrics.total_requests) * 100

        # Exponential moving average for response time
        if metrics.total_requests == 1:
            metrics.average_response_time = duration
        else:
            alpha = 0.1
            metrics.average_response_time = (
                alpha * duration + (1 - alpha) * metrics.average_response_time
            )

        metrics.timestamp = datetime.now()

    def _record_operation_failure(
        self, service_name: str, exception: Exception, duration: float
    ):
        """Record failed operation metrics"""
        metrics = self.service_metrics[service_name]

        # Update request counters
        metrics.total_requests += 1
        metrics.failed_requests += 1

        # Update success rate
        success_count = metrics.total_requests - metrics.failed_requests
        metrics.success_rate = (success_count / metrics.total_requests) * 100

        # Update error rate
        metrics.error_rate = (metrics.failed_requests / metrics.total_requests) * 100

        # Update response time (even for failures)
        if metrics.total_requests == 1:
            metrics.average_response_time = duration
        else:
            alpha = 0.1
            metrics.average_response_time = (
                alpha * duration + (1 - alpha) * metrics.average_response_time
            )

        metrics.timestamp = datetime.now()

    def _start_health_monitoring(self):
        """Start background health monitoring"""

        def health_monitor():
            while self._health_monitor_active:
                try:
                    self._update_system_health()
                    time.sleep(30)  # Check every 30 seconds
                except Exception as e:
                    handle_error(e, module=__name__, function="health_monitor")

        import threading

        health_thread = threading.Thread(target=health_monitor, daemon=True)
        health_thread.start()

    def _update_system_health(self):
        """Update overall system health metrics"""

        # Get connection pool status
        pool_status = self.connection_pool.get_pool_status()

        # Calculate connection pool health
        total_connections = pool_status["total_connections"]
        if total_connections > 0:
            pool_health = (
                pool_status["available_connections"] / total_connections
            ) * 100
        else:
            pool_health = 0

        # Aggregate service metrics
        if self.service_metrics:
            service_success_rates = [
                m.success_rate for m in self.service_metrics.values()
            ]
            service_response_times = [
                m.average_response_time for m in self.service_metrics.values()
            ]

            avg_success_rate = sum(service_success_rates) / len(service_success_rates)
            avg_response_time = sum(service_response_times) / len(
                service_response_times
            )

            total_requests = sum(
                m.total_requests for m in self.service_metrics.values()
            )
            total_failures = sum(
                m.failed_requests for m in self.service_metrics.values()
            )
        else:
            avg_success_rate = 100.0
            avg_response_time = 0.0
            total_requests = 0
            total_failures = 0

        # Update system health metrics
        self.health_metrics = HealthMetrics(
            timestamp=datetime.now(),
            success_rate=avg_success_rate,
            average_response_time=avg_response_time,
            error_rate=(total_failures / max(1, total_requests)) * 100,
            connection_pool_health=pool_health,
            circuit_breaker_open=(pool_status["circuit_breaker_state"] == "open"),
            total_requests=total_requests,
            failed_requests=total_failures,
        )

    def get_system_status(self) -> dict[str, Any]:
        """Get comprehensive system status"""

        # Update health before reporting
        self._update_system_health()

        system_status: dict[str, Any] = {}
        system_status["overall_health"] = self.health_metrics.get_status().value
        system_status["health_score"] = self.health_metrics.get_health_score()
        system_status["timestamp"] = self.health_metrics.timestamp.isoformat()
        system_status["metrics"] = {
            "success_rate": self.health_metrics.success_rate,
            "average_response_time": self.health_metrics.average_response_time,
            "error_rate": self.health_metrics.error_rate,
            "total_requests": self.health_metrics.total_requests,
        }
        system_status["connection_pool"] = self.connection_pool.get_pool_status()
        system_status["services"] = {}

        # Add service-specific status
        for service_name, metrics in self.service_metrics.items():
            config = self.service_configs[service_name]

            service_status = ServiceStatus.OPERATIONAL
            health_score = metrics.get_health_score()

            if health_score < 50:
                service_status = ServiceStatus.DOWN
            elif health_score < 70:
                service_status = ServiceStatus.FAILING
            elif health_score < 90:
                service_status = ServiceStatus.SLOW

            (system_status["services"])[service_name] = {
                "status": service_status.value,
                "health_score": health_score,
                "success_rate": metrics.success_rate,
                "average_response_time": metrics.average_response_time,
                "total_requests": metrics.total_requests,
                "failed_requests": metrics.failed_requests,
                "priority": config.priority.name,
                "circuit_breaker_enabled": config.enable_circuit_breaker,
            }

        return system_status

    def get_health_report(self) -> str:
        """Generate a human-readable health report"""

        status = self.get_system_status()

        report_lines = [
            "🏥 Trading System Health Report",
            "=" * 50,
            f"📊 Overall Health: {status['overall_health'].upper()} ({status['health_score']:.1f}/100)",
            f"⏰ Report Time: {status['timestamp']}",
            "",
            "📈 System Metrics:",
            f"  Success Rate: {status['metrics']['success_rate']:.1f}%",
            f"  Average Response: {status['metrics']['average_response_time']:.2f}s",
            f"  Error Rate: {status['metrics']['error_rate']:.1f}%",
            f"  Total Requests: {status['metrics']['total_requests']:,}",
            "",
            "🔌 Connection Pool:",
            f"  Total Connections: {status['connection_pool']['total_connections']}",
            f"  Available: {status['connection_pool']['available_connections']}",
            f"  Busy: {status['connection_pool']['busy_connections']}",
            f"  Circuit Breaker: {status['connection_pool']['circuit_breaker_state'].upper()}",
            "",
            "🛠️ Services:",
        ]

        for service_name, service_info in status["services"].items():
            status_emoji = {
                "operational": "✅",
                "slow": "🟡",
                "failing": "🟠",
                "down": "❌",
            }.get(service_info["status"], "❓")

            report_lines.extend(
                [
                    f"  {status_emoji} {service_name.replace('_', ' ').title()}:",
                    f"    Status: {service_info['status'].upper()} ({service_info['health_score']:.1f}/100)",
                    f"    Success Rate: {service_info['success_rate']:.1f}%",
                    f"    Avg Response: {service_info['average_response_time']:.2f}s",
                    f"    Requests: {service_info['total_requests']:,} ({service_info['failed_requests']} failed)",
                    "",
                ]
            )

        return "\n".join(report_lines)

    def shutdown(self):
        """Gracefully shutdown the error handling system"""
        self.logger.info("Shutting down integrated error handler...")

        # Stop health monitoring
        self._health_monitor_active = False

        # Shutdown connection pool
        self.connection_pool.shutdown()

        self.logger.info("Integrated error handler shutdown complete")


# Global integrated error handler instance
_integrated_handler: IntegratedErrorHandler | None = None


def get_integrated_error_handler() -> IntegratedErrorHandler:
    """Get the global integrated error handler instance"""
    global _integrated_handler

    if _integrated_handler is None:
        _integrated_handler = IntegratedErrorHandler()

    return _integrated_handler


def with_error_handling(service_name: str):
    """Decorator for functions that need integrated error handling"""

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            handler = get_integrated_error_handler()
            return handler.execute_service_operation(
                service_name, func, *args, **kwargs
            )

        return wrapper

    return decorator


# Example service functions with integrated error handling


@with_error_handling("market_data")
def get_real_time_quotes(connection: Any, symbols: list[str]) -> dict[str, float]:
    """Get real-time quotes with integrated error handling"""
    # Simulate market data retrieval
    if len(symbols) > 100:  # Simulate overload
        raise TradingSystemError("Too many symbols requested")

    return {symbol: 100.0 + hash(symbol) % 50 for symbol in symbols}


@with_error_handling("historical_data")
def download_historical_bars(
    connection: Any, symbol: str, start_date: str, end_date: str
):
    """Download historical data with integrated error handling"""
    # Simulate historical data download
    import random

    if random.random() < 0.2:  # 20% chance of failure
        raise ConnectionError(f"Failed to download data for {symbol}")

    return f"Downloaded {symbol} data from {start_date} to {end_date}"


@with_error_handling("order_management")
def place_order(connection: Any, symbol: str, quantity: int, order_type: str):
    """Place order with integrated error handling"""
    # Simulate order placement
    if quantity <= 0:
        raise ValueError("Invalid quantity")

    return f"Order placed: {order_type} {quantity} shares of {symbol}"


def main():
    """Demo the integrated error handling system"""

    print("🏥 Integrated Error Handling Demo")
    print("=" * 50)

    # Get the integrated handler
    handler = get_integrated_error_handler()

    # Test various operations
    print("🧪 Testing service operations...")

    # Test market data
    try:
        quotes = get_real_time_quotes(["AAPL", "MSFT", "GOOGL"])
        print(f"✅ Market data: {len(quotes)} quotes received")
    except Exception as e:
        print(f"❌ Market data failed: {e}")

    # Test historical data
    try:
        result = download_historical_bars("TSLA", "2024-01-01", "2024-01-31")
        print(f"✅ Historical data: {result}")
    except Exception as e:
        print(f"❌ Historical data failed: {e}")

    # Test order management
    try:
        result = place_order("AAPL", 100, "BUY")
        print(f"✅ Order placement: {result}")
    except Exception as e:
        print(f"❌ Order placement failed: {e}")

    # Generate health report
    print(f"\n{handler.get_health_report()}")

    # Cleanup
    handler.shutdown()

    print("🎉 Integrated error handling demo complete!")


if __name__ == "__main__":
    main()
