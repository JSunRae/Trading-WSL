"""Atomic JSON state persistence for gap recorder sessions & preferences."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from src.config import extensions as cfg_ext


@dataclass
class SessionState:
    symbol: str
    mode: str  # tick_only | l2 | queued
    start_time: str
    queued: bool = False


@dataclass
class AppState:
    sessions: list[SessionState]
    hidden_symbols: list[str]
    preferences: dict[str, Any]


class StateStore:
    def __init__(self, path: str | None = None) -> None:
        self.path = Path(path or cfg_ext.runtime_state_path())
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def load(self) -> AppState | None:
        try:
            if not self.path.exists():
                return None
            with self.path.open("r", encoding="utf-8") as f:
                raw = json.load(f)
            sessions = [SessionState(**s) for s in raw.get("sessions", [])]
            hidden = raw.get("hidden_symbols", [])
            prefs = raw.get("preferences", {})
            return AppState(sessions=sessions, hidden_symbols=hidden, preferences=prefs)
        except Exception:
            return None

    def save(self, state: AppState) -> bool:
        tmp = self.path.with_suffix(".tmp")
        data = {
            "sessions": [asdict(s) for s in state.sessions],
            "hidden_symbols": state.hidden_symbols,
            "preferences": state.preferences,
        }
        try:
            with tmp.open("w", encoding="utf-8") as f:
                json.dump(data, f, separators=(",", ":"))
                f.flush()
                os.fsync(f.fileno())
            tmp.replace(self.path)
            return True
        except Exception:
            if tmp.exists():
                try:
                    tmp.unlink()
                except Exception:
                    pass
            return False
