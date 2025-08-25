"""Helpers for L2 (order book) file path manipulation and atomic writes.

These utilities are vendor-agnostic and intentionally lightweight so they can
be imported inside tests without pulling heavy dependencies.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import pandas as pd

__all__ = ["with_source_suffix", "atomic_write_parquet"]


def with_source_suffix(path: Path, source: str = "databento") -> Path:
    """Return a new path with ``_<source>`` inserted before the extension.

    Examples
    --------
    >>> with_source_suffix(Path("/x/2025-07-29_snapshots.parquet"))
    PosixPath('/x/2025-07-29_snapshots_databento.parquet')
    """
    suffix = path.suffix or ".parquet"
    stem = path.stem
    return path.with_name(f"{stem}_{source}{suffix}")


Compression = Literal["snappy", "gzip", "brotli", "lz4", "zstd"] | None


def atomic_write_parquet(
    df: pd.DataFrame,
    dest: Path,
    *,
    compression: Compression = "snappy",
    overwrite: bool = False,
) -> None:
    """Atomically write DataFrame to ``dest`` (idempotent by default).

    If ``dest`` exists and ``overwrite`` is False the function is a no-op so
    callers can safely re-invoke without mutating timestamps (supports tests
    verifying idempotent skip semantics). When ``overwrite`` is True the file
    is replaced atomically.
    """
    if dest.exists() and not overwrite:
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".tmp")
    try:
        df.to_parquet(tmp, compression=compression)
        tmp.replace(dest)
    except Exception:
        try:
            if tmp.exists():
                tmp.unlink()
        finally:
            raise
