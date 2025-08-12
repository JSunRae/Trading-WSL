"""Lightweight runtime detection for Interactive Brokers dependency.

This module centralises availability checks so the rest of the codebase can
avoid importing heavy vendor modules (ib_async) at module import time. Use
`ib_available()` before performing any real IB operations and prefer lazy
imports guarded by this check.
"""

from __future__ import annotations

import os
from functools import lru_cache


class IBUnavailableError(RuntimeError):
    """Raised when an IB operation is attempted without the dependency."""


@lru_cache(maxsize=1)
def ib_available() -> bool:
    """Return True only if the real ``ib_async`` module can be imported.

    Honors FORCE_FAKE_IB=1 to force unavailability (used in tests) and performs
    a real import (find_spec alone can yield false positives when only stubs exist).
    """
    if os.getenv("FORCE_FAKE_IB", "") == "1":  # explicit override
        return False
    try:  # pragma: no cover - trivial branch
        import ib_async  # type: ignore  # noqa: F401
    except ModuleNotFoundError:
        return False
    else:
        return True


def ib_client_available() -> bool:
    """Alias used by public API facade (stable exported name)."""
    return ib_available()


def require_ib() -> None:
    """Raise IBUnavailable if ib_async isn't installed (helper guard)."""
    if not ib_available():
        raise IBUnavailableError(
            "Interactive Brokers dependency 'ib_async' not installed. Install with 'pip install .[ibkr]' or 'pip install ib_async'."
        )


__all__ = ["ib_available", "ib_client_available", "require_ib", "IBUnavailableError"]
