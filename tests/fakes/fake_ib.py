"""Test double for IB client allowing unit tests without ib_async installed."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


class _Event(list[Callable[..., Any]]):  # simplistic signal substitute
    def connect(self, fn: Callable[..., Any]) -> None:  # noqa: D401
        self.append(fn)

    def emit(self, *args: Any, **kwargs: Any) -> None:
        for fn in list(self):
            try:
                fn(*args, **kwargs)
            except Exception:  # pragma: no cover - test helper leniency
                pass


@dataclass
class _DepthTicker:
    updateEvent: _Event = field(default_factory=_Event)  # noqa: N815 - vendor style
    domBids: list[Any] = field(default_factory=list)  # noqa: N815  # elements: depth bid objects
    domAsks: list[Any] = field(default_factory=list)  # noqa: N815  # elements: depth ask objects
    domTicks: list[Any] = field(default_factory=list)  # noqa: N815  # elements: raw tick objects


@dataclass
class _TickByTickTicker:
    updateEvent: _Event = field(default_factory=_Event)  # noqa: N815
    ticks: list[Any] = field(default_factory=list)  # elements: tick objects


class FakeIB:
    """Minimal subset of ib_async.IB used by services, implemented in-memory."""

    def __init__(self) -> None:
        self.connected = False
        self._depth_subs: list[_DepthTicker] = []
        self._tbt_subs: list[_TickByTickTicker] = []

    async def connectAsync(self, host: str, port: int, clientId: int) -> bool:  # noqa: N802,N803
        await asyncio.sleep(0)
        self.connected = True
        return True

    def disconnect(self) -> None:  # noqa: D401
        self.connected = False

    # Depth API stubs -------------------------------------------------
    def reqMktDepth(self, *args: Any, **kwargs: Any) -> _DepthTicker:  # noqa: D401,N802
        ticker = _DepthTicker()
        self._depth_subs.append(ticker)
        return ticker

    def cancelMktDepth(self, *args: Any, **kwargs: Any) -> None:  # noqa: D401,N802
        pass

    # Tick-by-tick API stubs -----------------------------------------
    def reqTickByTickData(self, *args: Any, **kwargs: Any) -> _TickByTickTicker:  # noqa: N802
        ticker = _TickByTickTicker()
        self._tbt_subs.append(ticker)
        return ticker

    def cancelTickByTickData(self, *args: Any, **kwargs: Any) -> None:  # noqa: N802
        pass

    # Historical ------------------------------------------------------
    async def reqHistoricalDataAsync(self, *args: Any, **kwargs: Any) -> list[Any]:  # noqa: N802
        await asyncio.sleep(0)
        return []

    # Qualification (noop) -------------------------------------------
    def qualifyContracts(self, *args: Any, **kwargs: Any) -> None:  # noqa: N802
        return None


__all__ = ["FakeIB"]
