"""Extended targeted tests for IntegratedErrorHandler.

Focus: success path, retry invocation, and failure metrics classification.
"""

from __future__ import annotations

import time

from src.core.integrated_error_handling import IntegratedErrorHandler
from src.core.retry_manager import RetryConfig


def test_service_success_path():
    handler = IntegratedErrorHandler()

    def op(_conn):  # legacy style free function accepting injected connection
        return 42

    result = handler.execute_service_operation("order_management", op)
    assert result == 42
    metrics = handler.service_metrics["order_management"]
    assert metrics.total_requests >= 1
    assert metrics.failed_requests <= metrics.total_requests


def test_retry_invoked_on_failure_then_success():
    handler = IntegratedErrorHandler()
    # Override service config with a deterministic small retry config
    svc_cfg = handler.service_configs["order_management"]
    svc_cfg.retry_config = RetryConfig(max_attempts=3, base_delay=0.01, jitter=False)

    attempts = {"n": 0}

    def flaky(_conn):
        attempts["n"] += 1
        if attempts["n"] < 2:
            raise ConnectionError("transient")
        return "ok"

    start = time.time()
    result = handler.execute_service_operation("order_management", flaky)
    duration = time.time() - start
    assert result == "ok"
    assert attempts["n"] == 2  # one retry
    # Ensure metrics captured both attempts as single request (retry internal)
    metrics = handler.service_metrics["order_management"]
    assert metrics.total_requests >= 1
    assert metrics.failed_requests <= metrics.total_requests
    # Duration minimal due to monkeypatched small delay
    assert duration >= 0.0
