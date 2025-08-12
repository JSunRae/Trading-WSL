"""Type stubs for joblib"""
from typing import Any

def dump(
    value: Any,
    filename: str,
    compress: int = 0,
    protocol: Any | None = None
) -> list[str] | None: ...

def load(
    filename: str,
    mmap_mode: str | None = None,
    ensure_native_byte_order: str = "auto"
) -> Any: ...
