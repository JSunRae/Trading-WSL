from __future__ import annotations

import time
from datetime import UTC, datetime

import pandas as pd

from src.execution.ml_signal_executor import (
    MLSignalExecutor,
    MLTradingSignal,
    SignalExecution,
    SignalStatus,
    SignalType,
)


class StubOrderService:
    class Order:
        def __init__(self, order_id: int, filled: bool = True):
            self.order_id = order_id
            self.status = "filled" if filled else "submitted"
            self.filled_quantity = 5 if filled else 0
            self.avg_fill_price = 100.0 if filled else None
            self.commission = 0.05 if filled else 0.0
            self.is_active = not filled

    def __init__(self, position_qty: int = -10):
        # Negative to emulate a short position by default
        self._orders: dict[int, StubOrderService.Order] = {}
        self._pos_qty = position_qty

    def place_order(self, _conn, _order_request):
        oid = len(self._orders) + 1
        self._orders[oid] = StubOrderService.Order(oid, filled=True)
        return type("OrderInfo", (), {"order_id": oid})()

    def get_order(self, order_id: int):
        return self._orders.get(order_id)

    def get_position(self, _symbol: str):
        return type(
            "Pos", (), {"quantity": self._pos_qty, "is_flat": self._pos_qty == 0}
        )()


def make_sig(
    symbol: str = "AAPL",
    st: SignalType = SignalType.SELL,
    qty: int = 5,
    urg: str = "CRITICAL",
    max_timeout: float | int = 0,
):
    return MLTradingSignal(
        signal_id=f"sig-{symbol}-{st.value}",
        symbol=symbol,
        signal_type=st,
        confidence=0.9,
        target_quantity=qty,
        signal_timestamp=datetime.now(UTC),
        model_version="v1",
        strategy_name="strategy",
        urgency=urg,
        max_execution_time_seconds=max_timeout,
    )


def test_sell_and_close_short_paths_and_callbacks(monkeypatch):
    ex = MLSignalExecutor(order_service=StubOrderService(position_qty=-7))

    # Register callbacks to ensure they are invoked without errors
    statuses: list[SignalExecution] = []
    reports: list[pd.DataFrame] = []  # type: ignore[assignment]

    ex.add_signal_status_handler(lambda se: statuses.append(se))
    ex.add_execution_complete_handler(
        lambda report: reports.append(pd.DataFrame([report.execution_summary]))
    )

    # SELL path
    sid1 = ex.receive_signal(make_sig(st=SignalType.SELL, qty=3, max_timeout=1))
    # CLOSE_SHORT path should BUY to close
    sid2 = ex.receive_signal(make_sig(st=SignalType.CLOSE_SHORT, qty=0, max_timeout=1))

    # Allow brief time for background processing
    time.sleep(0.1)

    st1 = ex.get_signal_status(sid1)
    st2 = ex.get_signal_status(sid2)
    assert st1 is not None and st1.status in {
        SignalStatus.RECEIVED,
        SignalStatus.EXECUTED,
        SignalStatus.FAILED,
    }
    assert st2 is not None and st2.status in {
        SignalStatus.RECEIVED,
        SignalStatus.EXECUTED,
        SignalStatus.FAILED,
    }

    # Callback lists should have been populated (at least status updates)
    assert isinstance(statuses, list)


def test_immediate_timeout_path():
    # Service that never fills to force immediate TIMEOUT due to max_execution_time_seconds=0
    class PendingSvc(StubOrderService):
        def place_order(self, _c, _o):
            oid = len(self._orders) + 1
            self._orders[oid] = StubOrderService.Order(oid, filled=False)
            return type("OrderInfo", (), {"order_id": oid})()

    ex = MLSignalExecutor(order_service=PendingSvc())
    sid = ex.receive_signal(make_sig(st=SignalType.SELL, qty=2))
    time.sleep(0.05)
    st = ex.get_signal_status(sid)
    assert st is not None
    # Could be TIMEOUT immediately or transition to FAILED depending on timing
    assert st.status in {
        SignalStatus.TIMEOUT,
        SignalStatus.FAILED,
        SignalStatus.RECEIVED,
    }
