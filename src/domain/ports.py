"""Domain-level protocol abstractions to decouple from ib_async runtime.

Only the minimal surface actually required by services is defined here. This
keeps unit tests independent of the vendor library by allowing fakes to
implement these protocols.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class MarketDataClient(Protocol):
    async def connectAsync(self, host: str, port: int, clientId: int) -> bool: ...  # noqa: N802,N803,E701
    def disconnect(self) -> None: ...  # noqa: E701

    # Historical data (async wrapper already used)
    # def reqHistoricalDataAsync(...): ...  # intentionally omitted until needed


@runtime_checkable
class DepthDataHandle(Protocol):  # Represents returned ticker/depth subscription
    updateEvent: Any  # noqa: N815 - vendor style attr; duck-typed


__all__ = ["MarketDataClient", "DepthDataHandle"]
