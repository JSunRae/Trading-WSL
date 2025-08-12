"""Contract factory helpers with optional IB dependency (version 2).

This module no longer imports `ib_async` at import time. Real contract classes
are imported lazily only when available; otherwise lightweight fake objects are
returned so tests and environments without the optional `[ibkr]` extra function
without errors.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal, Protocol, runtime_checkable

from src.types.project_types import Currency, Exchange, Symbol

from ._ib_availability import ib_available, require_ib

if TYPE_CHECKING:  # Static typing only
    from ib_async import Contract as _Contract  # type: ignore[import-not-found]

    ContractT = _Contract  # type: ignore[assignment]
else:

    @runtime_checkable
    class ContractProto(Protocol):
        symbol: str  # noqa: D401

    ContractT = Any  # Accept real or fake at runtime


class _FakeContract:
    def __init__(self, symbol: str, exchange: str, currency: str) -> None:
        self.symbol = symbol
        self.exchange = exchange
        self.currency = currency

    def __repr__(self) -> str:  # pragma: no cover - simple debug aid
        return f"FakeContract(symbol={self.symbol}, exchange={self.exchange}, currency={self.currency})"


def _real():  # Lazy load vendor classes if available
    require_ib()
    from ib_async import Forex, Future, Stock  # type: ignore

    return Stock, Forex, Future


WhatToShow = Literal[
    "TRADES",
    "MIDPOINT",
    "BID",
    "ASK",
    "BID_ASK",
    "ADJUSTED_LAST",
    "HISTORICAL_VOLATILITY",
    "OPTION_IMPLIED_VOLATILITY",
]


def stock(
    symbol: Symbol,
    exchange: Exchange = Exchange("SMART"),
    currency: Currency = Currency("USD"),
) -> ContractT:
    if ib_available():
        Stock, _Forex, _Future = _real()  # noqa: N806
        return Stock(str(symbol), str(exchange), str(currency))  # type: ignore[return-value]
    return _FakeContract(str(symbol), str(exchange), str(currency))  # type: ignore[return-value]


def forex(pair: Symbol, exchange: Exchange = Exchange("IDEALPRO")) -> ContractT:
    if ib_available():
        _Stock, Forex, _Future = _real()  # noqa: N806
        return Forex(str(pair), str(exchange))  # type: ignore[return-value]
    return _FakeContract(str(pair), str(exchange), "USD")  # type: ignore[return-value]


def future(
    symbol: Symbol,
    exchange: Exchange,
    currency: Currency,
    lastTradeDateOrContractMonth: str,  # noqa: N803
) -> ContractT:
    if ib_available():
        _Stock, _Forex, Future = _real()  # noqa: N806
        f = Future(str(symbol), str(exchange), str(currency))  # type: ignore[assignment]
        if hasattr(f, "lastTradeDateOrContractMonth"):
            try:  # pragma: no cover
                f.lastTradeDateOrContractMonth = lastTradeDateOrContractMonth  # type: ignore[attr-defined]
            except Exception:
                pass
        return f  # type: ignore[return-value]
    return _FakeContract(str(symbol), str(exchange), str(currency))  # type: ignore[return-value]


__all__ = ["WhatToShow", "stock", "forex", "future", "ContractT"]
