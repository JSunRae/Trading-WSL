"""Compatibility shim for config services.

This module forwards to the canonical implementation in
``src.core.configuration.services`` to avoid duplication and import
conflicts with ``src/core/config.py``.
"""

from __future__ import annotations

# Re-export selected symbols from the canonical module
from src.core.configuration.services import (  # noqa: F401
    ValidationResult,
    backup_config,
    diff_dict,
    load_config,
    save_config,
    validate_config,
)

__all__ = (
    "ValidationResult",
    "validate_config",
    "load_config",
    "save_config",
    "diff_dict",
    "backup_config",
)
