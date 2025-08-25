"""DEPRECATED: ib_Warror_dl legacy module.

All functionality has been migrated to the modern CLI (module):
    python -m src.tools.warrior_update --help

This file is now a thin stub kept briefly so that any lingering imports
fail fast with a clear message. It will be removed entirely soon.
"""

from __future__ import annotations

import warnings
from typing import Any

_DEPRECATION_MSG = (
    "ib_Warror_dl is fully retired. Use 'python -m src.tools.warrior_update' instead."
)

warnings.warn(_DEPRECATION_MSG, DeprecationWarning, stacklevel=2)

__all__: list[str] = [
    "Update_Warrior_Main",
    "Update_Warrior_30Min",
    "Update_Downloaded",
    "Create_Warrior_TrainList",
]


def _deprecated(
    *_args: Any, **_kwargs: Any
) -> None:  # pragma: no cover - transitional stub
    raise RuntimeError(_DEPRECATION_MSG)


# Legacy public entry points (now just raising with instructions)
def Update_Warrior_Main(*args: Any, **kwargs: Any) -> None:  # noqa: N802
    _deprecated(*args, **kwargs)


def Update_Warrior_30Min(*args: Any, **kwargs: Any) -> None:  # noqa: N802
    _deprecated(*args, **kwargs)


def Update_Downloaded(*args: Any, **kwargs: Any) -> None:  # noqa: N802
    _deprecated(*args, **kwargs)


def Create_Warrior_TrainList(*args: Any, **kwargs: Any) -> None:  # noqa: N802
    _deprecated(*args, **kwargs)


if __name__ == "__main__":  # pragma: no cover
    _deprecated()
