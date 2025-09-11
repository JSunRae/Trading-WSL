from __future__ import annotations

import pytest


class FakeView:
    def __init__(self) -> None:
        self.status_messages: list[str] = []
        self.active: list[str] = []

    def set_status(self, text: str) -> None:
        self.status_messages.append(text)

    def set_active(self, symbols: list[str]) -> None:
        self.active = list(symbols)


class FakeMDS:
    def __init__(self) -> None:
        self._active: set[str] = set()

    def start_level2(self, symbol: str) -> bool:
        self._active.add(symbol)
        return True

    def stop_level2(self, symbol: str) -> None:
        self._active.discard(symbol)

    def stop_all(self) -> None:
        self._active.clear()

    def active(self) -> dict[str, list[str]]:
        return {"level2": sorted(self._active)}


@pytest.mark.asyncio
async def test_presenter_add_remove(monkeypatch: pytest.MonkeyPatch) -> None:
    # Lazy import to avoid importing PyQt in CI
    mod = __import__("src.ui.trading_app.presenter", fromlist=["TradingPresenter"])
    Presenter = mod.TradingPresenter

    view = FakeView()
    p = Presenter(view)

    # Patch presenter internals to use FakeMDS and skip real IB connection
    p.mds = FakeMDS()  # type: ignore[assignment]

    await p.add_symbol("AAPL")
    assert "Added AAPL" in view.status_messages[-1]
    # refresh called implicitly -> active updated
    assert view.active == ["AAPL"]

    await p.add_symbol("MSFT")
    assert view.active == ["AAPL", "MSFT"]

    await p.remove_symbols(["AAPL"])
    assert view.active == ["MSFT"]

    await p.refresh()
    assert view.active == ["MSFT"]
