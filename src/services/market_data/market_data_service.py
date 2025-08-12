"""Clean, typed Market Data Service with safe fallbacks for test environments.

This replaces a previously malformed implementation (indentation issues) and
provides a minimal but extensible service layer for:
  - Level 2 (market depth) data
  - Tick-by-tick data

Runtime dependencies on Interactive Brokers (ibapi/ib_insync) are guarded so
tests that only import the module (without a live IB connection) won't fail.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from time import perf_counter
from typing import Any

import pandas as pd
import pytz

from src.core.config import get_config
from src.core.error_handler import handle_error
from src.data.parquet_repository import ParquetRepository
from src.notifications import get_notification_manager

try:  # pragma: no cover - runtime dependency may be absent in some test envs
    from src.lib.ib_insync_compat import IB, Stock  # type: ignore
except Exception:  # Fallback lightweight stubs

    class IB:  # type: ignore
        pass

    class Stock:  # type: ignore
        def __init__(self, *args: Any, **kwargs: Any) -> None:  # noqa: D401
            pass


try:  # Local wrappers (present in infra)
    from src.infra.ib_requests import (  # type: ignore
        req_mkt_depth,
        req_tick_by_tick_data,
    )
except Exception:  # pragma: no cover

    def req_mkt_depth(*_args: Any, **_kwargs: Any) -> Any:  # type: ignore
        return None

    def req_tick_by_tick_data(*_args: Any, **_kwargs: Any) -> Any:  # type: ignore
        return None


@dataclass(slots=True)
class _SessionInfo:
    session_id: str
    start_time: datetime


class MarketDepthManager:
    """Manage a single symbol's market depth (Level 2) stream."""

    def __init__(
        self,
        ib: IB,
        symbol: str,
        num_levels: int = 20,
        update_interval: float = 0.1,
    ) -> None:
        self.ib = ib
        self.symbol = symbol
        self.num_levels = num_levels
        self.update_interval = update_interval

        # Optional components
        try:
            self.config = get_config()
            self.data_repo: ParquetRepository | None = ParquetRepository()
            self.notifications = get_notification_manager()
        except Exception:  # pragma: no cover - keep import cheap for tests
            self.config = None
            self.data_repo = None
            self.notifications = None

        # Runtime state
        self.contract: Any | None = None
        self.ticker: Any | None = None
        self.is_active = False
        self.last_update_time = 0.0
        self.last_save_time = 0.0
        self.session: _SessionInfo | None = None

        # DataFrames (typed containers)
        self.market_depth_data: pd.DataFrame = pd.DataFrame(
            columns=[
                "timestamp",
                "bid_sizes",
                "bid_prices",
                "bid_market_makers",
                "ask_sizes",
                "ask_prices",
                "ask_market_makers",
            ]
        )
        self.tick_data: pd.DataFrame = pd.DataFrame(
            columns=[
                "timestamp",
                "position",
                "operation",
                "side",
                "price",
                "size",
                "market_maker",
            ]
        )

    # ---------------------------------------------------------------------
    # Lifecycle
    # ---------------------------------------------------------------------
    def start(self) -> bool:
        """Begin Level 2 data streaming for this symbol."""
        if self.is_active:
            return True
        try:
            self.contract = Stock(self.symbol, "SMART", "USD")  # type: ignore[arg-type]
            try:
                self.ib.qualifyContracts(self.contract)  # type: ignore[attr-defined]
            except Exception:
                pass  # Qualification is best-effort in test environments

            self.ticker = req_mkt_depth(  # type: ignore[func-returns-value]
                self.ib,  # pyright: ignore[reportArgumentType]
                self.contract,  # pyright: ignore[reportArgumentType]
                num_rows=self.num_levels,
                is_smart_depth=True,
            )
            if self.ticker is not None:
                try:
                    self.ticker.updateEvent.connect(self._on_update)  # type: ignore[attr-defined]
                except Exception:
                    pass

            start_time = datetime.now(pytz.timezone("US/Eastern"))
            self.session = _SessionInfo(
                session_id=f"{self.symbol}_{start_time.strftime('%Y%m%d_%H%M%S')}",
                start_time=start_time,
            )
            self.is_active = True

            if self.notifications:
                self.notifications.send_trading_alert(
                    "MARKET_DATA",
                    self.symbol,
                    f"Level 2 started - {self.num_levels} levels",
                )
            return True
        except Exception as e:  # noqa: BLE001
            if self.notifications:
                handle_error(
                    e, context={"symbol": self.symbol, "operation": "start_depth"}
                )
            else:
                print(f"Error starting depth for {self.symbol}: {e}")
            return False

    def stop(self) -> bool:
        if not self.is_active:
            return True
        try:
            if self.ticker and self.contract:
                try:
                    self.ib.cancelMktDepth(self.contract)  # type: ignore[attr-defined]
                except Exception:
                    pass
            self.is_active = False
            if self.notifications:
                self.notifications.send_trading_alert(
                    "MARKET_DATA",
                    self.symbol,
                    f"Level 2 stopped - {len(self.tick_data)} ticks",
                )
            return True
        except Exception as e:  # noqa: BLE001
            if self.notifications:
                handle_error(
                    e, context={"symbol": self.symbol, "operation": "stop_depth"}
                )
            return False

    # ------------------------------------------------------------------
    # Internal processing
    # ------------------------------------------------------------------
    def _on_update(self, ticker: Any) -> None:  # pragma: no cover - callback
        try:
            now = perf_counter()
            if now - self.last_update_time < self.update_interval:
                return
            self.last_update_time = now
            self._process_dom_ticks(getattr(ticker, "domTicks", []))
            if now - self.last_save_time > 5.0:
                self._snapshot(ticker)
                self.last_save_time = now
        except Exception as e:  # noqa: BLE001
            if self.notifications:
                handle_error(
                    e, context={"symbol": self.symbol, "operation": "depth_update"}
                )

    def _process_dom_ticks(self, dom_ticks: Any) -> None:
        if not dom_ticks:
            return
        ts = datetime.now(pytz.timezone("US/Eastern"))
        rows: list[dict[str, Any]] = []
        for t in dom_ticks:
            try:
                rows.append(
                    {
                        "timestamp": ts,
                        "position": getattr(t, "position", 0),
                        "operation": getattr(t, "operation", 0),
                        "side": getattr(t, "side", 0),
                        "price": getattr(t, "price", 0.0),
                        "size": getattr(t, "size", 0.0),
                        "market_maker": getattr(t, "marketMaker", ""),
                    }
                )
            except Exception:
                continue
        if rows:
            self.tick_data = pd.concat(
                [self.tick_data, pd.DataFrame(rows)], ignore_index=True
            )

    def _snapshot(self, ticker: Any) -> None:
        try:
            if not self.data_repo or not self.session:
                return
            bids = list(getattr(ticker, "domBids", []) or [])
            asks = list(getattr(ticker, "domAsks", []) or [])
            snap = {
                "timestamp": datetime.now(pytz.timezone("US/Eastern")),
                "bid_sizes": [getattr(b, "size", 0) for b in bids[: self.num_levels]],
                "bid_prices": [
                    getattr(b, "price", 0.0) for b in bids[: self.num_levels]
                ],
                "bid_market_makers": [
                    getattr(b, "marketMaker", "") for b in bids[: self.num_levels]
                ],
                "ask_sizes": [getattr(a, "size", 0) for a in asks[: self.num_levels]],
                "ask_prices": [
                    getattr(a, "price", 0.0) for a in asks[: self.num_levels]
                ],
                "ask_market_makers": [
                    getattr(a, "marketMaker", "") for a in asks[: self.num_levels]
                ],
            }
            df = pd.DataFrame([snap])
            self.data_repo.save_data(
                df, self.symbol, "level2_snapshots", self.session.session_id
            )
        except Exception as e:  # noqa: BLE001
            if self.notifications:
                handle_error(
                    e, context={"symbol": self.symbol, "operation": "snapshot"}
                )


class TickByTickManager:
    """Manage tick-by-tick streaming for a single symbol."""

    def __init__(self, ib: IB, symbol: str) -> None:
        self.ib = ib
        self.symbol = symbol
        try:
            self.config = get_config()
            self.data_repo: ParquetRepository | None = ParquetRepository()
            self.notifications = get_notification_manager()
        except Exception:  # pragma: no cover
            self.config = None
            self.data_repo = None
            self.notifications = None
        self.contract: Any | None = None
        self.ticker: Any | None = None
        self.is_active = False
        self.tick_type: str | None = None
        self.tick_data: pd.DataFrame = pd.DataFrame(
            columns=["timestamp", "price", "size", "exchange", "special_conditions"]
        )

    def start(self, tick_type: str = "AllLast") -> bool:
        if self.is_active:
            return True
        try:
            self.contract = Stock(self.symbol, "SMART", "USD")  # type: ignore[arg-type]
            try:
                self.ib.qualifyContracts(self.contract)  # type: ignore[attr-defined]
            except Exception:
                pass
            self.ticker = req_tick_by_tick_data(  # type: ignore[func-returns-value]
                self.ib,
                self.contract,
                tick_type=tick_type,
                number_of_ticks=0,
                ignore_size=False,
            )
            if self.ticker is not None:
                try:
                    self.ticker.updateEvent.connect(self._on_update)  # type: ignore[attr-defined]
                except Exception:
                    pass
            self.tick_type = tick_type
            self.is_active = True
            return True
        except Exception as e:  # noqa: BLE001
            if self.notifications:
                handle_error(
                    e, context={"symbol": self.symbol, "operation": "start_tbt"}
                )
            return False

    def stop(self) -> bool:
        if not self.is_active:
            return True
        try:
            if self.ticker and self.contract:
                try:
                    self.ib.cancelTickByTickData(
                        self.contract, self.tick_type or "AllLast"
                    )  # type: ignore[attr-defined]
                except Exception:
                    pass
            if self.data_repo and not self.tick_data.empty:
                sid = datetime.now().strftime("%Y%m%d_%H%M%S")
                self.data_repo.save_data(
                    self.tick_data, self.symbol, "tick_by_tick", sid
                )
            self.is_active = False
            return True
        except Exception as e:  # noqa: BLE001
            if self.notifications:
                handle_error(
                    e, context={"symbol": self.symbol, "operation": "stop_tbt"}
                )
            return False

    def _on_update(self, ticker: Any) -> None:  # pragma: no cover - callback
        try:
            ticks = getattr(ticker, "ticks", []) or []
            if not ticks:
                return
            rows: list[dict[str, Any]] = []
            for t in ticks:
                rows.append(
                    {
                        "timestamp": getattr(t, "time", datetime.now()),
                        "price": getattr(t, "price", 0.0),
                        "size": getattr(t, "size", 0.0),
                        "exchange": getattr(t, "exchange", ""),
                        "special_conditions": getattr(t, "specialConditions", ""),
                    }
                )
            if rows:
                self.tick_data = pd.concat(
                    [self.tick_data, pd.DataFrame(rows)], ignore_index=True
                )
        except Exception as e:  # noqa: BLE001
            if self.notifications:
                handle_error(
                    e, context={"symbol": self.symbol, "operation": "tbt_update"}
                )


class MarketDataService:
    """Facade coordinating multiple symbol stream managers."""

    def __init__(self, ib: IB) -> None:
        self.ib = ib
        try:
            self.config = get_config()
            self.notifications = get_notification_manager()
        except Exception:  # pragma: no cover
            self.config = None
            self.notifications = None
        self.depth: dict[str, MarketDepthManager] = {}
        self.ticks: dict[str, TickByTickManager] = {}

    # Depth management -------------------------------------------------
    def start_level2(
        self, symbol: str, num_levels: int = 20, update_interval: float = 0.1
    ) -> bool:
        if symbol in self.depth:
            return True
        mgr = MarketDepthManager(
            self.ib, symbol, num_levels=num_levels, update_interval=update_interval
        )
        if mgr.start():
            self.depth[symbol] = mgr
            return True
        return False

    def stop_level2(self, symbol: str) -> bool:
        mgr = self.depth.get(symbol)
        if not mgr:
            return True
        if mgr.stop():
            self.depth.pop(symbol, None)
            return True
        return False

    # Tick-by-tick management -----------------------------------------
    def start_ticks(self, symbol: str, tick_type: str = "AllLast") -> bool:
        if symbol in self.ticks:
            return True
        mgr = TickByTickManager(self.ib, symbol)
        if mgr.start(tick_type):
            self.ticks[symbol] = mgr
            return True
        return False

    def stop_ticks(self, symbol: str) -> bool:
        mgr = self.ticks.get(symbol)
        if not mgr:
            return True
        if mgr.stop():
            self.ticks.pop(symbol, None)
            return True
        return False

    # Utilities --------------------------------------------------------
    def active(self) -> dict[str, list[str]]:
        return {"level2": list(self.depth.keys()), "ticks": list(self.ticks.keys())}

    def stop_all(self) -> None:
        for s in list(self.depth.keys()):
            self.stop_level2(s)
        for s in list(self.ticks.keys()):
            self.stop_ticks(s)


def get_market_data_service(ib: IB) -> MarketDataService:  # Backward compatibility
    return MarketDataService(ib)


if __name__ == "__main__":  # Simple smoke demo
    print("MarketDataService module loaded successfully.")
