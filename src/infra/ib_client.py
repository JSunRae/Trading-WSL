from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from ._ib_availability import IBUnavailableError, ib_available, require_ib

if TYPE_CHECKING:  # Only for static typing
    from ib_async import IB  # type: ignore[import-not-found]
else:  # Placeholder; replaced on first successful get_ib call

    class IB:  # type: ignore[override]
        ...  # noqa: D401


@runtime_checkable
class IBClient(Protocol):  # Minimal protocol of what we actually use
    def disconnect(self) -> None: ...  # noqa: D401,E701

    async def connectAsync(  # noqa: D401,N802  (vendor camelCase retained)
        self,
        host: str,
        port: int,
        clientId: int,  # noqa: N803 (3rd-party API)
    ) -> bool: ...  # noqa: E701


_ib: IB | None = None
_lock = asyncio.Lock()


async def get_ib() -> IB:
    """Get (and lazily create) a shared IB client instance.

    Raises:
        IBUnavailableError: if ib_async isn't installed.
    """
    require_ib()
    # Perform the import only when needed (after availability check)
    # Late import to avoid hard runtime dependency for test-only environments
    if not ib_available():  # Should be unreachable after require_ib, defensive
        raise IBUnavailableError("ib_async not installed")
    if "RealIB" not in globals():  # Load actual class once
        from ib_async import IB  # type: ignore

        globals()["RealIB"] = IB

    global _ib
    async with _lock:
        if _ib is None:
            _ib = globals()["RealIB"]()  # type: ignore[call-arg]
            await _ib.connectAsync("127.0.0.1", 7497, clientId=1)  # type: ignore[attr-defined]
    assert _ib is not None  # narrow for type checker
    return _ib


async def close_ib() -> None:
    """Close and reset the shared IB client instance (if present)."""
    global _ib
    async with _lock:
        if _ib is not None:
            try:
                _ib.disconnect()  # type: ignore[call-arg]
            except Exception:  # pragma: no cover - best effort
                pass
            _ib = None


def ib_client_available() -> bool:
    """Lightweight check for external callers (mirrors ib_available)."""
    return ib_available()


__all__ = [
    "get_ib",
    "close_ib",
    "ib_client_available",
    "IBClient",
    "IBUnavailableError",
]
