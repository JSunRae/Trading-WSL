from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from src.execution.ml_signal_executor import (
    MLSignalExecutor,
    MLTradingSignal,
    SignalExecution,
    SignalStatus,
    SignalType,
)
from src.services.order_management_service import OrderStatus


# pyright: reportUnusedImport=false, reportPrivateUsage=false, reportGeneralTypeIssues=false, reportUnknownArgumentType=false, reportUnknownMemberType=false
def make_sig(**overrides: Any) -> MLTradingSignal:
    now = datetime.now(UTC)
    defaults: dict[str, Any] = dict(
        signal_id="s-monitor",
        symbol=overrides.get("symbol", "AAPL"),
        signal_type=overrides.get("signal_type", SignalType.SELL),
        confidence=overrides.get("confidence", 0.9),
        target_quantity=overrides.get("target_quantity", 7),
        signal_timestamp=overrides.get("signal_timestamp", now),
        model_version="v1",
        strategy_name="strat",
        max_execution_time_seconds=overrides.get("max_execution_time_seconds", 5),
    )
    return MLTradingSignal(**defaults)


class DummyOrder:
    def __init__(
        self,
        status: OrderStatus,
        filled: int = 0,
        avg: float | None = None,
        commission: float = 0.0,
        is_active: bool = True,
    ) -> None:
        self.status = status
        self.filled_quantity = filled
        self.avg_fill_price = avg
        self.commission = commission
        self.is_active = is_active


class TransitioningOrderSvc:
    """Order service stub that returns a sequence of statuses and then final state.

    status_seq is a list of tuples: (status, filled_qty, avg_price, commission, is_active)
    """

    def __init__(
        self, status_seq: list[tuple[OrderStatus, int, float | None, float, bool]]
    ):
        self._seq = status_seq
        self._idx = 0
        self._last_id = 100

    def place_order(self, _conn, order_request):  # noqa: ARG002
        self._last_id += 1
        return type("Order", (), {"order_id": self._last_id})()

    def get_order(self, _order_id):  # noqa: ARG002
        if self._idx >= len(self._seq):
            self._idx = len(self._seq) - 1
        status, filled, avg, comm, active = self._seq[self._idx]
        # advance for next call
        if self._idx < len(self._seq) - 1:
            self._idx += 1
        return DummyOrder(status, filled, avg, comm, active)

    def get_position(self, _symbol):  # for CLOSE paths
        class P:
            quantity = -5
            is_flat = False

        return P()


def test_sell_execute_and_monitor_success(monkeypatch):
    # Sequence: pending -> partial -> filled
    seq = [
        (OrderStatus.PENDING_SUBMIT, 0, None, 0.0, True),
        (OrderStatus.PARTIAL_FILLED, 3, 100.0, 0.03, True),
        (OrderStatus.FILLED, 7, 100.5, 0.07, False),
    ]
    svc = TransitioningOrderSvc(seq)
    ex = MLSignalExecutor(order_service=svc)
    sig = make_sig(signal_type=SignalType.SELL, target_quantity=7)
    se = SignalExecution(signal_id="mon-1", signal=sig)
    assert ex._execute_signal(se) is True
    assert se.status == SignalStatus.EXECUTING
    # Speed up monitoring loop by setting tiny timeout
    se.signal.max_execution_time_seconds = 2
    # Remove sleep to keep test fast
    monkeypatch.setattr("src.execution.ml_signal_executor.time.sleep", lambda _: None)
    ex._monitor_execution(se)
    assert se.status == SignalStatus.EXECUTED
    assert se.total_filled_quantity == 7
    assert se.average_fill_price is not None


def test_monitor_all_failed_sets_failed(monkeypatch):
    # Sequence: submitted but inactive/cancelled with no fills
    seq = [
        (OrderStatus.SUBMITTED, 0, None, 0.0, False),
        (OrderStatus.CANCELLED, 0, None, 0.0, False),
    ]
    svc = TransitioningOrderSvc(seq)
    ex = MLSignalExecutor(order_service=svc)
    sig = make_sig(signal_type=SignalType.BUY, target_quantity=3)
    se = SignalExecution(signal_id="mon-2", signal=sig)
    assert ex._execute_signal(se) is True
    monkeypatch.setattr("src.execution.ml_signal_executor.time.sleep", lambda _: None)
    se.signal.max_execution_time_seconds = 2
    ex._monitor_execution(se)
    assert se.status in (SignalStatus.FAILED, SignalStatus.TIMEOUT)
    if se.status == SignalStatus.FAILED:
        assert se.error_message is not None


def test_close_short_zero_qty_allowed_and_timeout(monkeypatch):
    # CLOSE_SHORT with zero target_quantity should be allowed by dataclass and compute from position
    class Svc(TransitioningOrderSvc):
        def __init__(self):
            super().__init__([(OrderStatus.SUBMITTED, 0, None, 0.0, True)])

    svc = Svc()
    ex = MLSignalExecutor(order_service=svc)
    sig = make_sig(
        signal_type=SignalType.CLOSE_SHORT,
        target_quantity=0,
        max_execution_time_seconds=0,
    )
    se = SignalExecution(signal_id="mon-3", signal=sig)
    assert ex._execute_signal(se) is True
    # No waiting; timeout immediately
    monkeypatch.setattr("src.execution.ml_signal_executor.time.sleep", lambda _: None)
    ex._monitor_execution(se)
    assert se.status == SignalStatus.TIMEOUT
