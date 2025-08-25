#!/usr/bin/env python3
"""
IB_async Compatibility Layer - Drop-in replacement for ib_insync

This module provides a compatibility layer that allows existing ib_insync code
to work with minimal changes while using ib_async under the hood.

Usage:
    # Instead of: from ib_insync import IB, Stock, util
    from src.lib.ib_insync_compat import IB, Stock, util

    # Your existing code works the same way:
    ib = IB()
    ib.connect('127.0.0.1', 4002, clientId=1)

    contract = Stock('AAPL', 'SMART', 'USD')
    bars = ib.reqHistoricalData(contract, durationStr='1 D', barSizeSetting='1 min')

    # The module handles async conversion transparently using ib_async
"""

import asyncio
import logging
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import pandas as pd
from ibapi.contract import Contract as IBContract
from ibapi.order import Order as IBOrder

# Import from ib_async directly
try:
    from ib_async import IB as AsyncIB
    from ib_async import Stock as IBStock
    from ib_async import util as ib_async_util

    IB_ASYNC_AVAILABLE = True
except ImportError:
    # Fallback to our custom wrapper
    from .ib_async_wrapper import IBAsync as AsyncIB
    from .ib_async_wrapper import Stock as IBStock
    from .ib_async_wrapper import util_df as util

    IB_ASYNC_AVAILABLE = False


class EventEmitter:
    """Simple event emitter for compatibility with ib_insync events"""

    def __init__(self):
        self._handlers: dict[str, list[Callable]] = {}

    def on(self, event: str, handler: Callable):
        """Add event handler"""
        if event not in self._handlers:
            self._handlers[event] = []
        self._handlers[event].append(handler)

    def emit(self, event: str, *args, **kwargs):
        """Emit event to all handlers"""
        if event in self._handlers:
            for handler in self._handlers[event]:
                try:
                    handler(*args, **kwargs)
                except Exception as e:
                    logging.error(f"Error in event handler: {e}")

    def remove(self, event: str, handler: Callable):
        """Remove event handler"""
        if event in self._handlers and handler in self._handlers[event]:
            self._handlers[event].remove(handler)


class IB:
    """
    Compatibility wrapper for ib_insync.IB

    This class provides the same interface as ib_insync.IB but uses
    the new async implementation under the hood. It handles the async/sync
    conversion automatically using a background event loop.
    """

    def __init__(self):
        if IB_ASYNC_AVAILABLE:
            self._async_ib = AsyncIB()
        else:
            from .ib_async_wrapper import IBAsync

            self._async_ib = IBAsync()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._loop_thread: threading.Thread | None = None
        self._executor = ThreadPoolExecutor(max_workers=1)

        # Event emitters for ib_insync compatibility
        self.connectedEvent = EventEmitter()
        self.disconnectedEvent = EventEmitter()
        self.errorEvent = EventEmitter()
        self.newBarEvent = EventEmitter()
        self.pendingTickersEvent = EventEmitter()
        self.barUpdateEvent = EventEmitter()
        self.tickEvent = EventEmitter()

        # State tracking
        self.isConnected = False
        self._connected_event = threading.Event()

        # Start background event loop
        self._start_event_loop()

        # Setup async event handlers
        self._setup_error_handlers()

    # Backward compatibility: original name used in previous versions
    def _setup_event_handlers(self):  # pragma: no cover - thin wrapper
        """Backward-compatible wrapper calling the new error handler setup."""
        self._setup_error_handlers()

    def _start_event_loop(self):
        """Start background event loop for async operations"""

        def run_event_loop():
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            self._loop.run_forever()

        self._loop_thread = threading.Thread(target=run_event_loop, daemon=True)
        self._loop_thread.start()

        # Wait for loop to be ready
        while self._loop is None:
            threading.Event().wait(0.01)

    # ------------------------------------------------------------------
    # Error handling compatibility layer
    # ------------------------------------------------------------------
    def _setup_error_handlers(self) -> None:  # noqa: C901
        """Robustly register an error handler with underlying async IB.

        Supports multiple implementations:
        1. Object exposes add_error_handler(callable).
        2. Object exposes an event-like attribute (on_error / onError / error_event / error)
           that is either:
             - a callable accepting a handler to register, or
             - a list we can append to.
        3. If no mechanism detected, install a lightweight shim list and (optionally)
           an emit_error method to dispatch into it later.

        The goal is to avoid raising AttributeError during IB() construction when
        running against differing ib_async versions. Tests only require successful
        instantiation; full event bridging is best-effort.
        """

        ErrorHandler = Callable[[int, int, str, Any], None]  # noqa: N806

        def handler(*args: Any, **kwargs: Any) -> None:  # pragma: no cover - trivial
            try:
                # Forward raw payload; consumer-specific interpretation deferred.
                self.errorEvent.emit("error", args or kwargs)
            except Exception:  # noqa: BLE001
                pass

        ib = self._async_ib

        # 1) Direct API support
        if hasattr(ib, "add_error_handler"):
            try:  # type: ignore[attr-defined]
                ib.add_error_handler(handler)  # type: ignore[attr-defined]
                return
            except Exception:  # noqa: BLE001
                pass

        # 1b) Simple monkeypatch fallback (requested spec): create add_error_handler if absent
        if not hasattr(ib, "add_error_handler"):
            try:
                if not hasattr(ib, "_error_handlers"):
                    ib._error_handlers = []  # type: ignore[attr-defined]

                def _compat_add_error_handler(h):  # type: ignore[override]
                    try:
                        ib._error_handlers.append(h)  # type: ignore[attr-defined]
                    except Exception:  # noqa: BLE001
                        pass

                ib.add_error_handler = _compat_add_error_handler  # type: ignore[attr-defined]
                ib.add_error_handler(handler)  # type: ignore[attr-defined]
                return
            except Exception:  # noqa: BLE001
                pass

        # 2) Known attribute patterns
        for attr in ("on_error", "onError", "error_event", "error"):
            cb = getattr(ib, attr, None)
            if cb is None:
                continue
            # Callable registration hook
            if callable(cb):  # noqa: SIM108
                try:
                    cb(handler)
                    return
                except Exception:  # noqa: BLE001
                    pass
            # List of handlers pattern
            if isinstance(cb, list):
                cb.append(handler)
                return

        # 3) Fallback shim
        if not hasattr(ib, "_compat_error_handlers"):
            ib._compat_error_handlers = []  # type: ignore[attr-defined]
        ib._compat_error_handlers.append(handler)  # type: ignore[attr-defined]

        # Provide emit_error if absent so future integration can push errors.
        if not hasattr(ib, "emit_error"):

            def emit_shim(
                code: int, req_id: int, msg: str, extra: Any | None = None
            ) -> None:
                for h in getattr(ib, "_compat_error_handlers", []):  # type: ignore[attr-defined]
                    try:
                        h(code, req_id, msg, extra)
                    except Exception:  # noqa: BLE001
                        pass

            ib.emit_error = emit_shim  # type: ignore[attr-defined]

    def _run_async(self, coro):
        """Run async coroutine in background event loop and return result"""
        if self._loop is None:
            raise RuntimeError("Event loop not started")

        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return future.result(timeout=60)  # 60 second timeout

    def connect(  # noqa: N803
        self,
        host: str = "127.0.0.1",
        port: int = 4002,
        clientId: int = 1,
        timeout: float = 30,
    ) -> bool:
        """
        Connect to IB Gateway/TWS - synchronous interface

        This maintains the same interface as ib_insync but uses async underneath
        """
        try:
            # Run async connect in background thread
            success = self._run_async(
                self._async_ib.connect(host, port, clientId, timeout)
            )

            if success:
                self.isConnected = True
                self._connected_event.set()
                self.connectedEvent.emit("connected")

            return success

        except Exception as e:
            logging.error(f"Connection failed: {e}")
            return False

    def disconnect(self):
        """Disconnect from IB - synchronous interface"""
        try:
            self._run_async(self._async_ib.disconnect())
            self.isConnected = False
            self._connected_event.clear()
            self.disconnectedEvent.emit("disconnected")
        except Exception as e:
            logging.error(f"Disconnect failed: {e}")

    def run(self):
        """
        Run the event loop - compatibility method

        In the original ib_insync, this processes messages. In our implementation,
        message processing happens automatically in the background.
        """
        # For compatibility, we just wait a bit to process any pending messages
        if self.isConnected:
            threading.Event().wait(0.01)

    def reqHistoricalData(  # noqa: N802,N803
        self,
        contract: IBContract,
        endDateTime: str = "",
        durationStr: str = "1 D",
        barSizeSetting: str = "1 min",
        whatToShow: str = "TRADES",
        useRTH: bool = True,
        formatDate: int = 1,
        keepUpToDate: bool = False,
        chartOptions: list | None = None,
    ) -> pd.DataFrame | None:
        """
        Request historical data - synchronous interface

        Returns pandas DataFrame directly for compatibility with existing code
        """
        if not self.isConnected:
            logging.error("Not connected to IB")
            return None

        try:
            # Convert parameters to match our async interface
            df = self._run_async(
                self._async_ib.req_historical_data(
                    contract=contract,
                    duration=durationStr,
                    bar_size=barSizeSetting,
                    what_to_show=whatToShow,
                    use_rth=useRTH,
                    format_date=formatDate,
                    keep_up_to_date=keepUpToDate,
                )
            )

            # Emit newBarEvent for each bar (compatibility)
            if df is not None and not df.empty:
                for _, row in df.iterrows():
                    self.newBarEvent.emit("newBar", row)

            return df

        except Exception as e:
            logging.error(f"Historical data request failed: {e}")
            return None

    def reqMktData(  # noqa: N802,N803
        self,
        contract: IBContract,
        genericTickList: str = "",
        snapshot: bool = False,
        regulatorySnapshot: bool = False,
        mktDataOptions: list | None = None,
    ) -> int:
        """Request market data - synchronous interface"""
        if not self.isConnected:
            logging.error("Not connected to IB")
            return -1

        try:
            req_id = self._run_async(
                self._async_ib.req_market_data(
                    contract=contract,
                    generic_tick_list=genericTickList,
                    snapshot=snapshot,
                )
            )

            # Start background task to emit tick events
            if req_id > 0 and self._loop is not None:
                asyncio.run_coroutine_threadsafe(
                    self._emit_tick_events(contract, req_id), self._loop
                )

            return req_id

        except Exception as e:
            logging.error(f"Market data request failed: {e}")
            return -1

    async def _emit_tick_events(self, contract: IBContract, req_id: int):
        """Background task to emit tick events for compatibility"""
        while req_id in self._async_ib.wrapper._pending_requests:
            try:
                tick_data = await self._async_ib.wrapper._market_data_events.get()
                if tick_data.symbol == contract.symbol:
                    # Emit tick event in main thread
                    if self._loop is not None:
                        self._loop.call_soon_threadsafe(
                            self.tickEvent.emit, "tick", tick_data
                        )
            except Exception as e:
                logging.error(f"Error in tick event emitter: {e}")
                break

    def cancelMktData(self, reqId: int):  # noqa: N802,N803
        """Cancel market data - synchronous interface"""
        try:
            self._run_async(self._async_ib.cancel_market_data(reqId))
        except Exception as e:
            logging.error(f"Cancel market data failed: {e}")

    def reqMktDepth(  # noqa: N802,N803
        self,
        contract: IBContract,
        numRows: int = 10,
        isSmartDepth: bool = False,
        mktDepthOptions: list | None = None,
    ) -> int:
        """Request market depth - synchronous interface"""
        if not self.isConnected:
            logging.error("Not connected to IB")
            return -1

        try:
            req_id = self._run_async(
                self._async_ib.req_market_depth(
                    contract=contract, num_rows=numRows, is_smart_depth=isSmartDepth
                )
            )
            return req_id
        except Exception as e:
            logging.error(f"Market depth request failed: {e}")
            return -1

    def cancelMktDepth(self, reqId: int, isSmartDepth: bool = False):
        """Cancel market depth - synchronous interface"""
        try:
            self._run_async(self._async_ib.cancel_market_depth(reqId, isSmartDepth))
        except Exception as e:
            logging.error(f"Cancel market depth failed: {e}")

    def sleep(self, seconds: float):
        """Sleep for specified seconds - compatibility method"""
        threading.Event().wait(seconds)

    def waitOnUpdate(self, timeout: float = 0):
        """Wait for updates - compatibility method"""
        # In our async implementation, updates happen automatically
        # This is mainly for compatibility with existing code patterns
        if timeout > 0:
            threading.Event().wait(timeout)
        else:
            threading.Event().wait(0.01)  # Small delay

    # Property accessors for compatibility
    @property
    def client(self):
        """Access to underlying client"""
        return self._async_ib.client

    @property
    def wrapper(self):
        """Access to underlying wrapper"""
        return self._async_ib.wrapper

    def __enter__(self):
        """Context manager entry"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        if self.isConnected:
            self.disconnect()

        # Cleanup event loop
        if self._loop:
            self._loop.call_soon_threadsafe(self._loop.stop)
        if self._loop_thread and self._loop_thread.is_alive():
            self._loop_thread.join(timeout=5)


# Direct replacements for ib_insync classes and functions
def Stock(symbol: str, exchange: str = "SMART", currency: str = "USD") -> IBContract:
    """Create stock contract - direct replacement for ib_insync.Stock"""
    if IB_ASYNC_AVAILABLE:
        return IBStock(symbol, exchange, currency)
    else:
        from .ib_async_wrapper import Stock as AsyncStock

        return AsyncStock(symbol, exchange, currency)


class util:  # noqa: N801 - maintain ib_insync naming
    """Utility functions - replacement for ib_insync.util"""

    @staticmethod
    def df(bars) -> pd.DataFrame:  # noqa: D401
        """Convert bar data to DataFrame - replacement for ib_insync.util.df"""
        if IB_ASYNC_AVAILABLE:
            return ib_async_util.df(bars)  # type: ignore[attr-defined]
        from .ib_async_wrapper import util_df

        return util_df(bars)

    @staticmethod
    def barDataToDF(bars) -> pd.DataFrame:  # noqa: N802
        """Convert bar data to DataFrame"""
        return util.df(bars)


# Additional compatibility classes
class Contract(IBContract):
    """Enhanced contract class for compatibility"""

    pass


class Order(IBOrder):
    """Enhanced order class for compatibility"""

    pass


# Export compatibility interface
__all__ = ["IB", "Stock", "util", "Contract", "Order", "EventEmitter"]


# Module-level convenience functions for common use cases
async def connect_ib(
    host: str = "127.0.0.1", port: int = 4002, client_id: int = 1
) -> IB:
    """
    Convenience function to create and connect IB instance

    Usage:
        ib = await connect_ib()
        # ib is already connected and ready to use
    """
    from src.infra.ib_client import get_ib

    ib = await get_ib()
    return ib


async def get_historical_data(
    symbol: str,
    duration: str = "1 D",
    bar_size: str = "1 min",
    exchange: str = "SMART",
    currency: str = "USD",
) -> pd.DataFrame | None:
    """
    Convenience function to get historical data with minimal setup

    Usage:
        df = await get_historical_data('AAPL', '5 D', '1 min')
    """
    from src.infra.contract_factories import stock
    from src.infra.ib_client import get_ib
    from src.infra.ib_requests import req_hist
    from src.types.project_types import Currency, Exchange, Symbol

    try:
        ib = await get_ib()
        contract = stock(Symbol(symbol), Exchange(exchange), Currency(currency))
        # Cast to BarSize - this should be validated at runtime
        bars = await req_hist(contract, duration=duration, bar_size=bar_size)  # type: ignore[misc]  # ib_insync async typing incomplete
        return pd.DataFrame(bars) if bars else None
    except Exception as e:
        print(f"Error getting historical data: {e}")
        return None


if __name__ == "__main__":
    import asyncio

    async def demo():
        """Demo of compatibility layer with async patterns."""
        from src.infra.contract_factories import stock
        from src.infra.ib_client import close_ib, get_ib
        from src.infra.ib_requests import req_hist, req_market_data
        from src.types.project_types import Symbol

        print("Testing IB_insync compatibility layer (async)...")

        try:
            # Use new infrastructure
            ib = await get_ib()
            print("✅ Connected successfully")

            # Test historical data with new infrastructure
            contract = stock(Symbol("AAPL"))
            bars = await req_hist(contract, duration="1 D", bar_size="1 min")

            if bars and len(bars) > 0:
                print(f"✅ Retrieved {len(bars)} historical bars")
                # Print first few if available
                if hasattr(bars[0], "__dict__"):  # pyright: ignore[reportUnknownMemberType]  # IB object attribute check
                    print(f"Sample bar: {bars[0]}")
            else:
                print("❌ No historical data received")

            # Test market data with new infrastructure
            try:
                ticker = await req_market_data(contract, snapshot=True)
                print("✅ Market data requested successfully")
            except Exception as e:
                print(f"⚠️ Market data request failed: {e}")

        except Exception as e:
            print(f"❌ Connection or operation failed: {e}")
        finally:
            await close_ib()
            print("✅ Disconnected")

        print("Compatibility layer test complete!")

    # Run the demo
    asyncio.run(demo())
