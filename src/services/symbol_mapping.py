"""Symbol mapping utilities for vendor integrations.

Mapping file is a simple JSON object: {"LOCAL_SYMBOL": "VENDOR_SYMBOL", ...}
Missing file or entry -> identity mapping.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Literal


def load_symbol_mapping(path: Path) -> dict[str, str]:
    if not path or not path.exists():
        return {}
    try:
        mapping = json.loads(path.read_text())
        if isinstance(mapping, dict):
            norm: dict[str, str] = {}
            for k, v in list(mapping.items()):  # type: ignore[assignment] - runtime normalize
                try:
                    ks = str(k)  # type: ignore[arg-type]
                    vs = str(v)  # type: ignore[arg-type]
                    if ks == vs:
                        print(
                            f"WARN symbol_mapping identity mapping {ks}->{vs} (consider removing)",
                            file=sys.stderr,
                        )
                    norm[ks] = vs
                except Exception:  # pragma: no cover - defensive
                    continue
            return norm
        return {}
    except Exception:  # pragma: no cover - parse errors -> empty mapping
        return {}


def to_vendor(
    symbol: str, vendor: Literal["databento"], mapping_file: Path | None
) -> str:  # noqa: ARG001
    if mapping_file and mapping_file.exists():
        mapping = load_symbol_mapping(mapping_file)
        return mapping.get(symbol, symbol)
    return symbol
