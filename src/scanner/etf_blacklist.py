"""ETF blacklist loader.

Loads a simple newline-delimited list of ETF symbols.
Lines beginning with '#' or blank lines are ignored.
Symbols are uppercased and returned as a set for O(1) membership tests.
"""

from __future__ import annotations

from pathlib import Path


def load_etf_blacklist(path: str | None) -> set[str]:
    if not path:
        return set()
    p = Path(path)
    if not p.exists():
        return set()
    symbols: set[str] = set()
    try:
        for line in p.read_text().splitlines():
            t = line.strip()
            if not t or t.startswith("#"):
                continue
            symbols.add(t.upper())
    except Exception:
        return set()
    return symbols


__all__ = ["load_etf_blacklist"]
