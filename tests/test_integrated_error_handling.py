"""
Functional tests for src/core/integrated_error_handling.py
Covers full error handling pipeline, multiple errors, and health metrics.
"""

from src.core.integrated_error_handling import (
    HealthMetrics,
    IntegratedErrorHandler,
    SystemHealth,
)


def test_error_pipeline():
    from src.core.error_handler import ErrorCategory, ErrorSeverity, TradingSystemError

    handler = IntegratedErrorHandler()
    # Execute failing operations through handler to record metrics
    from typing import Any

    def failing_op(
        _conn: Any,
    ) -> None:  # _conn may be service object or pooled connection
        raise TradingSystemError("failing", ErrorCategory.SYSTEM, ErrorSeverity.HIGH)

    # Ensure a known service exists
    service_name = "order_management"
    failures = 0
    for _ in range(5):
        try:
            handler.execute_service_operation(service_name, failing_op)
        except TradingSystemError:
            failures += 1
    metrics = handler.service_metrics[service_name]
    assert failures == 5
    assert metrics.failed_requests >= 5
    assert metrics.get_status() in [
        SystemHealth.UNHEALTHY,
        SystemHealth.CRITICAL,
        SystemHealth.DEGRADED,
    ]


def test_health_metrics():
    metrics = HealthMetrics(
        success_rate=50.0,
        average_response_time=2.0,
        error_rate=50.0,
        connection_pool_health=50.0,
        circuit_breaker_open=True,
        total_requests=10,
        failed_requests=5,
    )
    score = metrics.get_health_score()
    assert 0 <= score <= 100
    status = metrics.get_status()
    assert status in [
        SystemHealth.HEALTHY,
        SystemHealth.DEGRADED,
        SystemHealth.UNHEALTHY,
        SystemHealth.CRITICAL,
    ]
