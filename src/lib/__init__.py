"""Library module for IB integration and compatibility layers."""

from .ib_async_wrapper import (
    Contract,
    IBAsync,
    Stock,
)

from .ib_insync_compat import (
    IB,
    Stock as CompatStock,
)

__all__ = [
    # ib_async_wrapper
    "Contract",
    "IBAsync",
    "Stock",
    # ib_insync_compat
    "IB",
    "CompatStock",
]
