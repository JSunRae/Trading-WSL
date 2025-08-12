from __future__ import annotations

from typing import Any

_REG: dict[str, Any] = {}


def register_service(name: str, svc: Any) -> None:
    _REG[name] = svc


def get_service(name: str) -> Any:
    if name not in _REG:
        raise KeyError(f"service '{name}' not registered")
    return _REG[name]


def clear_registry() -> None:
    _REG.clear()
