from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.services.market_data.market_data_service import MarketDataService
from src.utils.ib_connection_helper import get_ib_connection


@dataclass(slots=True)
class PresenterState:
    connected: bool = False


class TradingPresenter:
    """Presenter coordinating UI with MarketDataService."""

    def __init__(self, view: Any) -> None:
        self.view = view
        self.state = PresenterState()
        self.ib: Any | None = None
        self.mds: MarketDataService | None = None

    async def initialize(self) -> None:
        self.view.set_status("Connecting to IB...")
        self.ib, _tracker = await get_ib_connection(live_mode=False)
        assert self.ib is not None
        self.mds = MarketDataService(self.ib)  # type: ignore[arg-type]
        self.state.connected = True
        self.view.set_status("Connected. Ready.")
        await self.refresh()

    async def shutdown(self) -> None:
        if self.mds:
            self.mds.stop_all()
        self.view.set_status("Disconnected.")

    async def add_symbol(self, symbol: str) -> None:
        if not self.mds:
            self.view.set_status("Not connected yet")
            return
        ok = self.mds.start_level2(symbol)
        self.view.set_status(f"Added {symbol}" if ok else f"Failed to add {symbol}")
        await self.refresh()

    async def remove_symbols(self, symbols: list[str]) -> None:
        if not self.mds:
            return
        for s in symbols:
            self.mds.stop_level2(s)
        self.view.set_status(f"Removed: {', '.join(symbols)}")
        await self.refresh()

    async def refresh(self) -> None:
        if not self.mds:
            return
        active = self.mds.active().get("level2", [])
        self.view.set_active(active)
