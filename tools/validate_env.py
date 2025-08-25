"""Environment & configuration validator for L2 backfill release hardening.

Validations:
- Required env vars present: DATABENTO_API_KEY (warn if missing in non-strict), DATABENTO_DATASET, DATABENTO_SCHEMA
- Symbol mapping file exists & is readable (SYMBOL_MAPPING_FILE)
- Optional guards: L2_MAX_ROWS_PER_TASK, L2_ZERO_ROW_MAX numeric when set
Exits non-zero on hard failures so CI can stop early.
"""

from __future__ import annotations

import os
from pathlib import Path

REQUIRED = [
    "DATABENTO_DATASET",
    "DATABENTO_SCHEMA",
]  # API key optional (tool handles absence unless strict)
OPTIONAL_NUMERIC = ["L2_MAX_ROWS_PER_TASK", "L2_ZERO_ROW_MAX"]
MAPPING_KEY = "SYMBOL_MAPPING_FILE"


def _fail(msg: str) -> None:
    print(f"FAIL {msg}")
    raise SystemExit(1)


def main() -> int:
    missing = [k for k in REQUIRED if not os.getenv(k)]
    if missing:
        _fail(f"Missing required env vars: {','.join(missing)}")
    mapping = os.getenv(MAPPING_KEY)
    if not mapping:
        _fail(f"{MAPPING_KEY} not set")
    p = Path(mapping)
    if not p.exists():
        _fail(f"Mapping file missing: {p}")
    if p.stat().st_size == 0:
        _fail(f"Mapping file empty: {p}")
    # Optional numeric guards
    for k in OPTIONAL_NUMERIC:
        v = os.getenv(k)
        if v:
            try:
                int(v)
            except ValueError:
                _fail(f"{k} must be integer if set (got {v})")
    # Soft warning for API key
    if not os.getenv("DATABENTO_API_KEY"):
        print(
            "WARN DATABENTO_API_KEY not set (backfill will run in unavailable mode unless strict)"
        )
    print("OK environment validation passed")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
