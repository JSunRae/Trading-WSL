"""Deprecated legacy module: MasterPy_Trading.

All legacy contents removed. The last remaining class (`BarCLS`) was
retired from production (tests now use `tests/helpers/legacy_bar.py::BarClsTestShim`).

Removal schedule:
        * Soft deprecation warning emitted on import.
        * Final removal (file deletion) planned: 2025-09-30.

Action required: eliminate any remaining third‑party imports of
`src.MasterPy_Trading` (or `MasterPy_Trading`) before the removal date.

If some external code still needs interval formatting, implement a
project-local helper or adopt modern services directly.
"""

from __future__ import annotations

import warnings as _warnings

# TODO(2025-09-30): Remove this stub file entirely once ecosystem consumers have migrated.
_warnings.warn(
    "src.MasterPy_Trading is deprecated and will be removed on 2025-09-30; "
    "remove this import (no direct replacement; use modern service modules).",
    DeprecationWarning,
    stacklevel=2,
)

__all__: list[str] = []
