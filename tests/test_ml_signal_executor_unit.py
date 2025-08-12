from __future__ import annotations

# pyright: reportUnusedImport=false, reportPrivateUsage=false, reportGeneralTypeIssues=false, reportUnknownArgumentType=false, reportUnknownMemberType=false, reportUnknownVariableType=false
from datetime import UTC, datetime, timedelta

from src.domain.ml_types import SizingMode
from src.execution.ml_signal_executor import (
    ExecutionReport,
    MLSignalExecutor,
    MLTradingSignal,
    SignalExecution,
    SignalStatus,
    SignalType,
)


def make_sig(**overrides):
    now = datetime.now(UTC)
    signal_id = overrides.get("signal_id", "s-unit")
    symbol = overrides.get("symbol", "AAPL")
    signal_type = overrides.get("signal_type", SignalType.BUY)
    confidence = overrides.get("confidence", 0.7)
    target_quantity = overrides.get("target_quantity", 10)
    signal_timestamp = overrides.get("signal_timestamp", now)
    model_version = overrides.get("model_version", "v1")
    strategy_name = overrides.get("strategy_name", "strat")
    return MLTradingSignal(
        signal_id=signal_id,
        symbol=symbol,
        signal_type=signal_type,
        confidence=confidence,
        target_quantity=target_quantity,
        signal_timestamp=signal_timestamp,
        model_version=model_version,
        strategy_name=strategy_name,
    )


def test_validate_signal_paths():
    ex = MLSignalExecutor()
    # invalid: use SimpleNamespace to bypass dataclass __post_init__
    from types import SimpleNamespace

    bad = SimpleNamespace(
        confidence=-0.1,  # out of range
        target_quantity=0,  # zero quantity
        symbol="",  # invalid symbol
        signal_type=SignalType.CLOSE_LONG,  # not in allowed list in validator
    )
    ok, violations = ex.validate_signal(bad)  # type: ignore[arg-type]
    assert not ok and violations

    good = make_sig()
    ok2, violations2 = ex.validate_signal(good)
    assert ok2 and not violations2


def test_confidence_and_position_size():
    ex = MLSignalExecutor()
    sig_hi = make_sig(confidence=1.0, target_quantity=100)
    sig_lo = make_sig(confidence=0.0, target_quantity=100)
    # boundaries
    assert ex.confidence_factor(sig_hi) == 1.0
    assert ex.confidence_factor(sig_lo) == 0.0

    # sizing: FIXED returns base, CONFIDENCE scales
    fixed = ex.calculate_position_size(sig_hi, method=SizingMode.FIXED)
    assert fixed.final_size == abs(sig_hi.target_quantity)
    cw = ex.calculate_position_size(sig_hi, method=SizingMode.CONFIDENCE_WEIGHTED)
    assert cw.final_size == int(
        abs(sig_hi.target_quantity) * ex.confidence_factor(sig_hi)
    )


def test_generate_execution_report_contents():
    ex = MLSignalExecutor()
    sig = make_sig(target_quantity=20, confidence=0.9)
    se = SignalExecution(signal_id="exec-1", signal=sig, status=SignalStatus.EXECUTED)
    # populate execution stats
    se.orders_created = [1, 2]
    se.total_filled_quantity = 20
    se.average_fill_price = 101.25
    se.total_commission = 1.23
    se.execution_start_time = datetime.now(UTC) - timedelta(seconds=2)
    se.execution_complete_time = datetime.now(UTC)
    se.signal_to_execution_latency_ms = 250.0

    report: ExecutionReport = ex._generate_execution_report(
        se
    )  # private method by design
    assert report.execution_summary["execution_status"] == SignalStatus.EXECUTED.value
    assert report.performance_metrics["fill_rate_pct"] == 100.0
    assert report.risk_metrics["confidence_score"] == sig.confidence
    assert report.execution_quality["orders_created"] == 2
    assert report.execution_quality["execution_time_seconds"] is not None


def test_execution_stats_success_rate():
    ex = MLSignalExecutor()
    # simulate some outcomes directly
    ex.execution_stats["signals_executed_successfully"] = 3
    ex.execution_stats["signals_failed"] = 1
    ex.execution_stats["signals_timed_out"] = 1
    stats = ex.get_execution_stats()
    assert stats["success_rate_pct"] > 0


def test_execute_signal_buy_hold_and_close_long_failure():  # pyright: ignore[reportArgumentType]
    class DummyOrderSvc:
        def __init__(self):
            self.placed = []

        def place_order(self, _conn, order_request):
            self.placed.append(order_request)
            return type("Order", (), {"order_id": 42})()

        def get_position(self, symbol):  # no position -> None
            return None

    ex = MLSignalExecutor()
    ex.order_service = DummyOrderSvc()  # monkeypatch instance attribute

    # BUY path
    buy_sig = make_sig(signal_type=SignalType.BUY, target_quantity=5)
    se_buy = SignalExecution(signal_id="e-b", signal=buy_sig)
    ok_buy = ex._execute_signal(se_buy)
    assert ok_buy is True
    assert se_buy.status == SignalStatus.EXECUTING
    assert se_buy.orders_created

    # HOLD path -> immediate executed
    hold_sig = make_sig(signal_type=SignalType.HOLD, target_quantity=0)
    se_hold = SignalExecution(signal_id="e-h", signal=hold_sig)
    ok_hold = ex._execute_signal(se_hold)
    assert ok_hold is True
    assert se_hold.status == SignalStatus.EXECUTED

    # CLOSE_LONG with no position -> failure
    close_sig = make_sig(signal_type=SignalType.CLOSE_LONG, target_quantity=0)
    se_close = SignalExecution(signal_id="e-c", signal=close_sig)
    ok_close = ex._execute_signal(se_close)
    assert ok_close is False
    assert se_close.status == SignalStatus.FAILED
