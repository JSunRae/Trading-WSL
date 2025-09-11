from __future__ import annotations

from collections.abc import Callable
from typing import Any

Callback = Callable[[str, dict[str, Any]], None]
_subscribers: list[Callback] = []


def subscribe(callback: Callback) -> None:
    if callback not in _subscribers:
        _subscribers.append(callback)


def unsubscribe(callback: Callback) -> None:
    if callback in _subscribers:
        _subscribers.remove(callback)


def publish_config_changed(filename: str, diff: dict[str, Any]) -> None:
    for cb in list(_subscribers):
        try:
            cb(filename, diff)
        except Exception:
            # Best-effort; avoid raising into publisher
            pass
