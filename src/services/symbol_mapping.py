"""Symbol mapping utilities for vendor integrations.

Mapping file is a simple JSON object: {"LOCAL_SYMBOL": "VENDOR_SYMBOL", ...}
Missing file or entry -> identity mapping.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Literal


def _normalize_bento_dataset(dataset: str) -> str:
    """Map common aliases to canonical DataBento dataset codes.

    Examples:
    - NASDAQ.ITCH -> XNAS.ITCH
    - NASDAQ.BASIC -> XNAS.BASIC
    - NASDAQ.QBBO -> XNAS.QBBO
    - NYSE.PILLAR -> XNYS.PILLAR
    - NYSE.BBO -> XNYS.BBO
    - NYSE.TRADES -> XNYS.TRADES

    Any unknown value is returned unchanged. Comparison is case-insensitive.
    """
    if not dataset:
        return dataset
    ds = dataset.strip().upper()
    aliases: dict[str, str] = {
        "NASDAQ.ITCH": "XNAS.ITCH",
        "NASDAQ.BASIC": "XNAS.BASIC",
        "NASDAQ.QBBO": "XNAS.QBBO",
        "NASDAQ.NLS": "XNAS.NLS",
        "NYSE.PILLAR": "XNYS.PILLAR",
        "NYSE.BBO": "XNYS.BBO",
        "NYSE.TRADES": "XNYS.TRADES",
        "NYSE.TRADESBBO": "XNYS.TRADESBBO",
    }
    return aliases.get(ds, dataset)


def load_symbol_mapping(path: Path) -> dict[str, str]:
    if not path or not path.exists():
        return {}
    try:
        mapping = json.loads(path.read_text())
        if isinstance(mapping, dict):
            norm: dict[str, str] = {}
            for k, v in list(mapping.items()):
                try:
                    ks = str(k)
                    # If nested object, keep string form for compatibility; resolved later
                    vs = v if isinstance(v, str) else json.dumps(v)
                    if ks == vs:
                        print(
                            f"WARN symbol_mapping identity mapping {ks}->{vs} (consider removing)",
                            file=sys.stderr,
                        )
                    norm[ks] = str(vs)
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


def resolve_vendor_params(
    symbol: str,
    vendor: Literal["databento"],
    mapping_file: Path | None,
    default_dataset: str,
    default_schema: str,
) -> tuple[str, str, str]:
    """Resolve (vendor_symbol, dataset, schema) with optional per-symbol overrides.

    Mapping file may contain either a simple string mapping or an object like:
        { "SYMBOL": { "symbol": "VENDOR_SYMBOL", "dataset": "XNYS.PILLAR", "schema": "mbp-10" } }

    Unknown or missing fields fall back to provided defaults.
    """
    vendor_symbol = symbol
    dataset = _normalize_bento_dataset(default_dataset)
    schema = default_schema
    if mapping_file and mapping_file.exists():
        try:
            obj = json.loads(mapping_file.read_text())
            if isinstance(obj, dict) and symbol in obj:
                entry = obj[symbol]
                if isinstance(entry, str):
                    vendor_symbol = entry
                elif isinstance(entry, dict):
                    vendor_symbol = str(entry.get("symbol", vendor_symbol))
                    dataset = _normalize_bento_dataset(
                        str(entry.get("dataset", dataset))
                    )
                    schema = str(entry.get("schema", schema))
        except Exception:
            pass
    return vendor_symbol, dataset, schema
