"""L2SlotManager enforces a hard cap of 5 concurrent Level 2 streams.

Provides FIFO upgrade queue and emits structured events via metrics.emit_event.
"""

from __future__ import annotations

import threading
from collections import deque

from src.observability.metrics import emit_event, inc

MAX_L2_SLOTS = 5


class L2SlotManager:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._active: set[str] = set()
        self._queue: deque[str] = deque()
        self._attempts: dict[str, int] = {}

    # --- Public API ---
    def try_acquire(self, symbol: str) -> bool:
        with self._lock:
            if symbol in self._active:
                return True
            if len(self._active) < MAX_L2_SLOTS and symbol not in self._queue:
                self._active.add(symbol)
                emit_event("l2_acquired", symbol=symbol, active=len(self._active))
                inc("active_l2", 1)
                return True
            # enqueue if not already queued
            if symbol not in self._queue and symbol not in self._active:
                self._queue.append(symbol)
            return False

    def release(self, symbol: str) -> None:
        with self._lock:
            if symbol in self._active:
                self._active.remove(symbol)
                emit_event("l2_released", symbol=symbol, active=len(self._active))
                inc("active_l2", -1)
        self._promote_if_possible()

    def fail_and_requeue(self, symbol: str) -> None:
        with self._lock:
            if symbol in self._active:
                self._active.remove(symbol)
                inc("active_l2", -1)
            if symbol not in self._queue:
                self._queue.appendleft(symbol)
            self._attempts[symbol] = self._attempts.get(symbol, 0) + 1
            emit_event(
                "l2_subscribe_failed", symbol=symbol, attempts=self._attempts[symbol]
            )
        self._promote_if_possible()

    def promote_next(self) -> str | None:
        with self._lock:
            if len(self._active) >= MAX_L2_SLOTS:
                return None
            while self._queue:
                sym = self._queue.popleft()
                if sym in self._active:
                    continue
                self._active.add(sym)
                emit_event("l2_promoted", symbol=sym, active=len(self._active))
                inc("active_l2", 1)
                return sym
            return None

    def queued(self) -> list[str]:
        with self._lock:
            return list(self._queue)

    def active(self) -> list[str]:
        with self._lock:
            return list(self._active)

    # --- Internal ---
    def _promote_if_possible(self) -> None:
        promoted = self.promote_next()
        if promoted is not None:
            # event already emitted
            pass
