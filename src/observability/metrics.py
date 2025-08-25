"""Lightweight metrics counters & structured logging for scanner/recorder."""

from __future__ import annotations

import logging
import threading
from time import time
from typing import Any

_logger = logging.getLogger(__name__)
_lock = threading.Lock()
_counters: dict[str, int] = {}


def inc(name: str, value: int = 1) -> None:
    with _lock:
        _counters[name] = _counters.get(name, 0) + value


def get(name: str) -> int:
    with _lock:
        return _counters.get(name, 0)


def snapshot() -> dict[str, int]:
    with _lock:
        return dict(_counters)


def emit_event(event: str, **fields: Any) -> None:
    payload = {"event": event, "ts": int(time()), **fields}
    # Flat key=value pattern for easy grep
    kv = " ".join(f"{k}={v}" for k, v in payload.items())
    _logger.info(kv)
