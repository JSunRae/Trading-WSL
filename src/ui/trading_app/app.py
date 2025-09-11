from __future__ import annotations

import asyncio

try:
    from PyQt6.QtWidgets import QApplication
    from qasync import QEventLoop
except Exception:  # pragma: no cover - GUI optional
    QApplication = object  # type: ignore
    QEventLoop = object  # type: ignore

from .presenter import TradingPresenter
from .view import MainWindow


async def main_async() -> None:
    app = QApplication([])  # type: ignore[call-arg]
    loop = QEventLoop(app)  # type: ignore[call-arg]
    asyncio.set_event_loop(loop)

    win = MainWindow()
    presenter = TradingPresenter(win)

    # Hook callbacks (return None)
    def on_add(symbol: str) -> None:
        asyncio.create_task(presenter.add_symbol(symbol))

    def on_remove_selected(symbols: list[str]) -> None:
        asyncio.create_task(presenter.remove_symbols(symbols))

    def on_refresh() -> None:
        asyncio.create_task(presenter.refresh())

    win.on_add = on_add
    win.on_remove_selected = on_remove_selected
    win.on_refresh = on_refresh

    await presenter.initialize()

    win.show()  # type: ignore[attr-defined]
    try:
        with loop:  # type: ignore[attr-defined]
            await loop.run_forever()  # type: ignore[attr-defined]
    finally:
        await presenter.shutdown()


def main() -> None:
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
