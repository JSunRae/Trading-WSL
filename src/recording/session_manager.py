"""SessionManager orchestrates tick + L2 recording with slot enforcement."""

from __future__ import annotations

from datetime import UTC, datetime

from src.observability import metrics
from src.recording.l2_slot_manager import L2SlotManager

# Lazy import to avoid heavy dependencies until needed
from src.services.market_data.market_data_service import MarketDataService


class SessionInfo:
    def __init__(self, symbol: str) -> None:
        self.symbol = symbol
        self.mode = "tick_only"  # tick_only | l2 | queued
        self.start_time = datetime.now(UTC).isoformat()
        self.queued = False


class SessionManager:
    def __init__(
        self, md_service: MarketDataService, slots: L2SlotManager | None = None
    ) -> None:
        self._md = md_service
        self._slots = slots or L2SlotManager()
        self._sessions: dict[str, SessionInfo] = {}

    def start(self, symbol: str) -> SessionInfo:
        if symbol in self._sessions:
            return self._sessions[symbol]
        info = SessionInfo(symbol)
        # Always start ticks
        self._md.start_ticks(symbol)
        # Attempt L2
        if self._slots.try_acquire(symbol):
            if self._md.start_level2(symbol):
                info.mode = "l2"
            else:
                # subscription failed; requeue
                self._slots.fail_and_requeue(symbol)
                info.mode = "queued"
                info.queued = True
        else:
            info.mode = "queued"
            info.queued = True
        self._sessions[symbol] = info
        metrics.emit_event("session_started", symbol=symbol, mode=info.mode)
        return info

    def stop(self, symbol: str) -> None:
        info = self._sessions.get(symbol)
        if not info:
            return
        # Stop L2 if active
        if info.mode == "l2":
            self._md.stop_level2(symbol)
            self._slots.release(symbol)
        # Always stop ticks
        self._md.stop_ticks(symbol)
        metrics.emit_event("session_stopped", symbol=symbol)
        self._sessions.pop(symbol, None)

    def upgrade_cycle(self) -> None:
        # Attempt promotions
        promoted = self._slots.promote_next()
        if promoted:
            if self._md.start_level2(promoted):
                s = self._sessions.get(promoted)
                if s:
                    s.mode = "l2"
                    s.queued = False
                    metrics.emit_event("session_upgraded", symbol=promoted)
            else:
                self._slots.fail_and_requeue(promoted)

    def active_summary(self) -> dict[str, int]:
        ticks = len(self._sessions)
        l2 = sum(1 for s in self._sessions.values() if s.mode == "l2")
        queued = sum(1 for s in self._sessions.values() if s.mode == "queued")
        return {"ticks": ticks, "l2": l2, "queued": queued}

    def list_sessions(self) -> list[SessionInfo]:
        return list(self._sessions.values())

    def stop_all(self) -> None:
        for sym in list(self._sessions.keys()):
            self.stop(sym)
