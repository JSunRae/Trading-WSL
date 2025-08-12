"""Infrastructure layer public exports (lazy, optional IB dependency).

This package deliberately avoids importing modules that *may* import the
optional ``ib_async`` dependency at import time. Instead we provide thin
wrapper functions that perform the real import only when a symbol is first
used. This keeps ``import src.infra`` safe in environments where the `[ibkr]`
extra (and thus ``ib_async``) is not installed.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .async_utils import RateLimiter, gather_bounded, with_retry
from .ib_client import IBUnavailableError, close_ib, get_ib, ib_client_available

if TYPE_CHECKING:  # pragma: no cover - static typing only
    # Real functions for type information only (aliases unused at runtime)
    from .contract_factories import forex as _forex_real  # noqa: F401
    from .contract_factories import future as _future_real
    from .contract_factories import stock as _stock_real
    from .ib_requests import (  # noqa: F401
        req_hist as _req_hist_real,  # noqa: F401
    )
    from .ib_requests import (
        req_mkt_depth as _req_mkt_depth_real,  # noqa: F401
    )
    from .ib_requests import (
        req_tick_by_tick_data as _req_tick_by_tick_data_real,  # noqa: F401
    )


# ---------------------------- Lazy wrapper helpers -------------------------
def stock(*args: Any, **kwargs: Any):  # noqa: D401
    from . import contract_factories as _cf

    return _cf.stock(*args, **kwargs)


def forex(*args: Any, **kwargs: Any):  # noqa: D401
    from . import contract_factories as _cf

    return _cf.forex(*args, **kwargs)


def future(*args: Any, **kwargs: Any):  # noqa: D401
    from . import contract_factories as _cf

    return _cf.future(*args, **kwargs)


async def req_hist(*args: Any, **kwargs: Any):  # noqa: D401
    from . import ib_requests as _req

    return await _req.req_hist(*args, **kwargs)


def req_mkt_depth(*args: Any, **kwargs: Any):  # noqa: D401
    from . import ib_requests as _req

    return _req.req_mkt_depth(*args, **kwargs)


def req_tick_by_tick_data(*args: Any, **kwargs: Any):  # noqa: D401
    from . import ib_requests as _req

    return _req.req_tick_by_tick_data(*args, **kwargs)


__all__ = [
    # Client management
    "get_ib",
    "close_ib",
    "ib_client_available",
    "IBUnavailableError",
    # Contract factory wrappers
    "stock",
    "forex",
    "future",
    # Request wrappers
    "req_hist",
    "req_mkt_depth",
    "req_tick_by_tick_data",
    # Async utilities
    "RateLimiter",
    "gather_bounded",
    "with_retry",
]
