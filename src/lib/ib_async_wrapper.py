#!/usr/bin/env python3
# ruff: noqa: N802, N803, N806, N817  # Preserve public API names/args for compatibility
"""Async wrapper utilities for IB with legacy compatibility.

Modern async wrapper for Interactive Brokers API with native asyncio support and
no legacy dependencies.
"""

import asyncio
import logging
import os
import time
from collections import defaultdict, deque
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any, cast

import numpy as np
import pandas as pd

# IB API imports (must be installed: pip install ibapi)
from ibapi.client import EClient
from ibapi.common import BarData, TickerId
from ibapi.contract import Contract
from ibapi.wrapper import EWrapper

# Type imports from our custom types
from ..types import ErrorContext, Price, RequestId, Symbol, Volume

# TickType is just an int, define it for compatibility
TickType = int


class ConnectionState(Enum):
    """Connection states"""

    DISCONNECTED = "DISCONNECTED"
    CONNECTING = "CONNECTING"
    CONNECTED = "CONNECTED"
    RECONNECTING = "RECONNECTING"
    FAILED = "FAILED"


class DataType(Enum):
    """Market data types"""

    LIVE = 1
    FROZEN = 2
    DELAYED = 3
    DELAYED_FROZEN = 4


@dataclass
class MarketDepthData:
    """Market depth (Level 2) data"""

    symbol: Symbol
    position: int
    operation: int  # 0=insert, 1=update, 2=delete
    side: int  # 0=ask, 1=bid
    price: Price
    size: Volume
    market_maker: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class TickData:
    """Real-time tick data"""

    symbol: Symbol
    tick_type: int
    value: float
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


class AsyncIBWrapper(EWrapper):
    """
    Async wrapper for IB API events
    Uses asyncio-based queues for non-blocking event handling
    """

    def __init__(self) -> None:
        EWrapper.__init__(self)
        self.logger: logging.Logger = logging.getLogger(__name__)
        # Event loop reference for thread-safe scheduling from IB callbacks
        self._loop: asyncio.AbstractEventLoop | None = None

        # Event queues for async communication - properly typed
        # Events: (event_name, payload)
        # event_name in {"socket_open", "api_ready", "disconnected"}
        self._connection_events: asyncio.Queue[tuple[str, Any]] = asyncio.Queue()
        self._error_events: asyncio.Queue[ErrorContext] = asyncio.Queue()
        self._historical_data_events: asyncio.Queue[
            tuple[RequestId, list[dict[str, Any]]]
        ] = asyncio.Queue()
        self._market_data_events: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._market_depth_events: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._order_events: asyncio.Queue[Any] = asyncio.Queue()

        # Data storage - properly typed
        self._historical_data: dict[RequestId, list[dict[str, Any]]] = {}
        self._market_depth: dict[
            Symbol, dict[str, dict[int, dict[str, Price | Volume]]]
        ] = defaultdict(lambda: {"bids": {}, "asks": {}})
        self._last_prices: dict[Symbol, Price] = {}

        # Request tracking - properly typed
        self._pending_requests: dict[RequestId, Symbol] = {}
        self._request_id: RequestId = 1000

        # Handshake state
        self._api_ready: bool = False
        self._managed_accounts: list[str] = []

    # Loop wiring
    def set_event_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Record the asyncio loop to post events into.

        IB API callbacks often arrive on non-async threads. We must schedule
        queue operations onto the main loop in a thread-safe way.
        """
        self._loop = loop

    def _enqueue(self, q: asyncio.Queue[Any], item: Any) -> None:
        """Thread-safe enqueue into an asyncio.Queue without creating orphaned coroutines.

        Prefer run_coroutine_threadsafe when we have a target loop. If we're
        already on the loop thread, use create_task. As a last-resort fallback
        (no loop yet), try put_nowait to avoid dropping data and avoid creating
        an un-awaited coroutine. This path is best-effort and should be rare.
        """
        try:
            # If we know the loop and it's running, schedule thread-safe
            if self._loop is not None and self._loop.is_running():
                asyncio.run_coroutine_threadsafe(q.put(item), self._loop)
                return
            # If we're on a running loop thread, schedule normally
            loop = asyncio.get_running_loop()
            loop.create_task(q.put(item))
        except RuntimeError:
            # No running loop context; best-effort immediate enqueue
            try:
                q.put_nowait(item)
            except Exception:
                # As a last resort, drop with a debug log to avoid crashing callbacks
                try:
                    self.logger.debug("Dropping event; no loop to enqueue")
                except Exception:
                    pass

    def get_next_request_id(self) -> int:
        """Get next available request ID"""
        self._request_id += 1
        return self._request_id

    # Public accessors for protected data - Type-safe access from client
    def get_connection_events(self) -> asyncio.Queue[tuple[str, Any]]:
        """Get connection events queue"""
        return self._connection_events

    def get_error_events(self) -> asyncio.Queue[ErrorContext]:
        """Get error events queue"""
        return self._error_events

    def get_historical_data_events(
        self,
    ) -> asyncio.Queue[tuple[RequestId, list[dict[str, Any]]]]:
        """Get historical data events queue"""
        return self._historical_data_events

    def get_market_data_events(self) -> asyncio.Queue[dict[str, Any]]:
        """Get market data events queue"""
        return self._market_data_events

    def get_market_depth_events(self) -> asyncio.Queue[dict[str, Any]]:
        """Get market depth events queue"""
        return self._market_depth_events

    def get_pending_requests(self) -> dict[RequestId, Symbol]:
        """Get pending requests dictionary"""
        return self._pending_requests

    def set_pending_request(self, req_id: RequestId, symbol: Symbol) -> None:
        """Set a pending request"""
        self._pending_requests[req_id] = symbol

    def remove_pending_request(self, req_id: RequestId) -> Symbol | None:
        """Remove and return pending request"""
        return self._pending_requests.pop(req_id, None)

    def get_historical_data(self, req_id: RequestId) -> list[dict[str, Any]] | None:
        """Get historical data for request ID"""
        return self._historical_data.get(req_id)

    def remove_historical_data(self, req_id: RequestId) -> list[dict[str, Any]] | None:
        """Remove and return historical data for request ID"""
        return self._historical_data.pop(req_id, None)

    def get_market_depth(
        self, symbol: Symbol
    ) -> dict[str, dict[int, dict[str, Price | Volume]]]:
        """Get market depth for symbol"""
        return self._market_depth.get(symbol, {"bids": {}, "asks": {}})

    def get_last_prices(self) -> dict[Symbol, Price]:
        """Get last prices dictionary"""
        return self._last_prices

    def get_last_price(self, symbol: Symbol) -> Price | None:
        """Get last known price for symbol"""
        return self._last_prices.get(symbol)

    # Connection callbacks
    def connectAck(self) -> None:
        """Connection acknowledged"""
        # TCP socket is open and API acknowledged
        try:
            self.logger.info("[SOCKET_OPEN] IB socket acknowledged by API")
        except Exception:
            pass
        # Required for asynchronous connection path
        try:
            self.startApi()  # type: ignore[attr-defined]
            # Nudge server for nextValidId
            try:
                self.reqIds(-1)  # type: ignore[attr-defined]
            except Exception:
                import time

                time.sleep(0.05)
                self.reqIds(-1)  # type: ignore[attr-defined]
        except Exception as e:
            try:
                self.logger.error("connectAck handling error: %s", e)
            except Exception:
                pass
        self._enqueue(self._connection_events, ("socket_open", True))

    def connectionClosed(self) -> None:
        """Connection closed"""
        self._enqueue(self._connection_events, ("disconnected", True))
        self._api_ready = False

    # Handshake readiness events
    def nextValidId(self, orderId: int) -> None:  # noqa: N802
        """API handshake event indicating readiness (first valid order id)."""
        self._api_ready = True
        try:
            self.logger.info("[API_READY] nextValidId=%s", orderId)
        except Exception:
            pass
        self._enqueue(
            self._connection_events,
            ("api_ready", {"source": "nextValidId", "orderId": orderId}),
        )

    def managedAccounts(self, accountsList: str) -> None:  # noqa: N802
        """Accounts list received; another indicator of API readiness."""
        try:
            accounts = [a.strip() for a in accountsList.split(",") if a.strip()]
        except Exception:
            accounts = []
        self._managed_accounts = accounts
        self._api_ready = True
        try:
            self.logger.info("[API_READY] managedAccounts=%s", accounts)
        except Exception:
            pass
        self._enqueue(
            self._connection_events,
            ("api_ready", {"source": "managedAccounts", "accounts": accounts}),
        )

    # Introspection helpers
    def is_api_ready(self) -> bool:
        return self._api_ready

    def get_managed_accounts(self) -> list[str]:
        return list(self._managed_accounts)

    # Error handling
    def error(
        self,
        reqId: TickerId,
        errorCode: int,
        errorString: str,
        advancedOrderRejectJson: str = "",
    ) -> None:
        """Handle API errors"""
        error_data: ErrorContext = {
            "reqId": reqId,
            "errorCode": errorCode,
            "errorString": errorString,
            "timestamp": datetime.now(UTC),
        }
        self._enqueue(self._error_events, error_data)

    # Historical data callbacks
    def historicalData(self, reqId: TickerId, bar: BarData) -> None:
        """Receive historical bar data"""
        if reqId not in self._historical_data:
            self._historical_data[reqId] = []

        # Convert BarData to dict format
        historical_bar = {
            "date": bar.date,
            "open": bar.open,
            "high": bar.high,
            "low": bar.low,
            "close": bar.close,
            "volume": bar.volume,
            "wap": getattr(bar, "wap", 0.0),
            "count": getattr(bar, "count", 0),
        }
        self._historical_data[reqId].append(historical_bar)

    def historicalDataEnd(self, reqId: int, start: str, end: str) -> None:
        """Historical data download complete"""
        bars = self._historical_data.get(reqId, [])
        try:
            self.logger.info(
                "Historical data complete reqId=%s bars=%d range=%s->%s",
                reqId,
                len(bars),
                start,
                end,
            )
        except Exception:
            # Logging must not break the callback
            pass
        # Enqueue result for async consumers
        self._enqueue(self._historical_data_events, (reqId, bars))
        # Proactively free memory; finalizer will pop again safely (pop with default)
        try:
            self._pending_requests.pop(reqId, None)
        except Exception:
            pass

    # Market data callbacks
    def tickPrice(
        self, reqId: TickerId, tickType: int, price: float, attrib: Any
    ) -> None:
        """Real-time price tick"""
        symbol: Symbol = self._pending_requests.get(reqId, Symbol("UNKNOWN"))
        tick_data = {
            "symbol": symbol,
            "tick_type": tickType,
            "value": price,
            "timestamp": datetime.now(UTC),
        }

        # Store last price for reference
        if tickType in [1, 2, 4]:  # Bid, Ask, Last
            self._last_prices[symbol] = float(price)

        self._enqueue(self._market_data_events, tick_data)

    def tickSize(self, reqId: TickerId, tickType: int, size: int) -> None:
        """Real-time size tick"""
        symbol: Symbol = self._pending_requests.get(reqId, Symbol("UNKNOWN"))
        tick_data = {
            "symbol": symbol,
            "tick_type": tickType,
            "value": float(size),
            "timestamp": datetime.now(UTC),
        }
        self._enqueue(self._market_data_events, tick_data)

    # Market depth callbacks
    def updateMktDepth(
        self,
        reqId: TickerId,
        position: int,
        operation: int,
        side: int,
        price: float,
        size: int,
    ) -> None:
        """Level 2 market depth update"""
        symbol: Symbol = self._pending_requests.get(reqId, Symbol("UNKNOWN"))
        depth_data = {
            "symbol": symbol,
            "position": position,
            "operation": operation,
            "side": side,
            "price": price,
            "size": size,
            "timestamp": datetime.now(UTC),
        }

        # Update internal depth tracking
        side_key = "bids" if side == 1 else "asks"
        depth_dict = self._market_depth[symbol][side_key]

        if operation == 0 or operation == 1:  # Insert or update
            depth_dict[position] = {
                "price": float(price),
                "size": int(size),
            }
        elif operation == 2:  # Delete
            depth_dict.pop(position, None)

        self._enqueue(self._market_depth_events, depth_data)

    def updateMktDepthL2(
        self,
        reqId: TickerId,
        position: int,
        marketMaker: str,
        operation: int,
        side: int,
        price: float,
        size: int,
        isSmartDepth: bool,
    ) -> None:
        """Level 2 market depth update with market maker"""
        symbol: Symbol = self._pending_requests.get(reqId, Symbol("UNKNOWN"))
        depth_data = {
            "symbol": symbol,
            "position": position,
            "operation": operation,
            "side": side,
            "price": price,
            "size": size,
            "market_maker": marketMaker,
            "timestamp": datetime.now(UTC),
        }

        self._enqueue(self._market_depth_events, depth_data)


class AsyncIBClient(EClient):
    """
    Async client for IB API
    Pure asyncio-friendly connection management
    """

    def __init__(self, wrapper: AsyncIBWrapper):
        # Properly call parent constructor with explicit type annotation
        super().__init__(wrapper)
        self.wrapper: AsyncIBWrapper = wrapper
        self.logger: logging.Logger = logging.getLogger(__name__)

        # Connection state
        self.state: ConnectionState = ConnectionState.DISCONNECTED
        self._connection_lock: asyncio.Lock = asyncio.Lock()

    async def connect_async(  # noqa: C901 - Connection handshake logic intentionally verbose
        self,
        host: str,
        port: int,
        clientId: int,
        timeout: float = 30,
        *,
        first_attempt: bool = True,
        account_hint: str | None = None,
        host_type: str | None = None,
    ) -> bool:
        """
        Async connection to IB Gateway/TWS
        Key improvement: Non-blocking connection with timeout
        """
        import socket
        import subprocess
        import time

        def _tcp_probe(h: str, p: int, t: float = 2.0) -> bool:
            s: socket.socket | None = None
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(t)
                return s.connect_ex((h, int(p))) == 0
            except Exception:
                return False
            finally:
                if s is not None:
                    try:
                        s.close()
                    except Exception:
                        pass

        def _detect_gw_pid() -> str:
            """Best-effort discovery of GW Java PID (stringified)."""
            try:
                out = subprocess.check_output(
                    ["bash", "-lc", "pgrep -f install4j.ibgateway.GWClient | tail -n1"],
                    stderr=subprocess.DEVNULL,
                    timeout=1.5,
                )
                pid = out.decode("utf-8", "ignore").strip()
                return pid or "?"
            except Exception:
                return "?"

        async with self._connection_lock:
            try:
                self.state = ConnectionState.CONNECTING

                # Start connection in thread (IB API is not async)
                loop = asyncio.get_event_loop()

                # Properly typed connection function
                def connect_func() -> None:
                    cast(Any, self.connect)(host, port, clientId)

                t0 = time.perf_counter()
                tcp_ok = _tcp_probe(host, port, t=2.0)
                gw_pid = _detect_gw_pid()
                self.logger.info(
                    "[TELEMETRY] attempt host=%s port=%s clientId=%s tcp_probe_ok=%s gw_pid=%s host_type=%s",
                    host,
                    port,
                    clientId,
                    bool(tcp_ok),
                    gw_pid,
                    host_type or "unknown",
                )

                connect_task = loop.run_in_executor(None, connect_func)

                # Wait for connection with timeout
                try:
                    await asyncio.wait_for(connect_task, timeout=timeout)
                except TimeoutError:
                    self.state = ConnectionState.FAILED
                    self.logger.warning(
                        "[HANG_DIAG] tcp_ok=%s connectAck=N apiReady=N gw_pid=%s port=%s note=connect() timeout",
                        bool(tcp_ok),
                        gw_pid,
                        port,
                    )
                    return False

                # Wait for socket acknowledgment ([SOCKET_OPEN])
                t_connect_return = time.perf_counter()
                try:
                    event, _payload = await asyncio.wait_for(
                        self.wrapper.get_connection_events().get(), timeout=10
                    )
                except TimeoutError:
                    self.state = ConnectionState.FAILED
                    t_ack_to = time.perf_counter()
                    self.logger.warning(
                        "[HANG_DIAG] tcp_ok=%s connectAck=N apiReady=N gw_pid=%s port=%s time_to_ack=%.3fs",
                        bool(tcp_ok),
                        gw_pid,
                        port,
                        (t_ack_to - t0),
                    )
                    return False
                if event != "socket_open":
                    # Unexpected event order; treat as failure for safety
                    self.state = ConnectionState.FAILED
                    return False

                # Handshake gating: wait for API_READY (nextValidId/managedAccounts)
                handshake_timeout = 30.0 if first_attempt else max(5.0, float(timeout))
                try:
                    # Fast-path: if wrapper already marked ready
                    if not self.wrapper.is_api_ready():
                        # Allow account hint shortcut: if provided, reduce wait threshold
                        effective_timeout = (
                            5.0
                            if (account_hint and account_hint.strip())
                            else handshake_timeout
                        )
                        while True:
                            evt, _payload = await asyncio.wait_for(
                                self.wrapper.get_connection_events().get(),
                                timeout=effective_timeout,
                            )
                            if evt == "api_ready":
                                break
                    # If we got here, API is ready
                    t_api = time.perf_counter()
                    self.logger.info(
                        "[TELEMETRY] ack->api time_to_ack=%.3fs time_to_api=%.3fs host=%s port=%s clientId=%s gw_pid=%s host_type=%s",
                        (t_connect_return - t0),
                        (t_api - t_connect_return),
                        host,
                        port,
                        clientId,
                        gw_pid,
                        host_type or "unknown",
                    )
                    self.state = ConnectionState.CONNECTED
                    return True
                except TimeoutError:
                    # Handshake did not complete
                    t_api_to = time.perf_counter()
                    self.logger.warning(
                        "[HANG_DIAG] tcp_ok=%s connectAck=Y apiReady=N gw_pid=%s port=%s time_to_ack=%.3fs time_to_api=%.3fs hint=Possible hidden modal/first-run gate; try foreground launch.",
                        bool(tcp_ok),
                        gw_pid,
                        port,
                        (t_connect_return - t0),
                        (t_api_to - t_connect_return),
                    )
                    if account_hint and account_hint.strip():
                        # Optional bypass: assume ready when a single known account is configured
                        try:
                            self.logger.info(
                                "[API_READY] assumed via account_hint after warmup"
                            )
                        except Exception:
                            pass
                        self.state = ConnectionState.CONNECTED
                        return True
                    self.state = ConnectionState.FAILED
                    return False

            except Exception as e:
                self.logger.error(f"Connection failed: {e}")
                self.state = ConnectionState.FAILED
                return False

        return False

    async def disconnect_async(self) -> None:
        """Async disconnect"""
        if self.state == ConnectionState.CONNECTED:
            self.disconnect()
            self.state = ConnectionState.DISCONNECTED


class IBAsync:
    """
    Main async IB interface for the IB API

    Highlights:
    - Pure asyncio implementation
    - Built-in rate limiting and pacing
    - Enhanced error handling and reconnection
    - Optimized for ML data collection
    """

    def __init__(self) -> None:
        super().__init__()  # Call parent class __init__ if needed
        self.wrapper: AsyncIBWrapper = AsyncIBWrapper()
        self.client: AsyncIBClient = AsyncIBClient(self.wrapper)
        self.logger: logging.Logger = logging.getLogger(__name__)

        # Helper to sanitize host strings (strip inline comments/whitespace)
        def _sanitize_host(val: str) -> str:
            try:
                h = val.strip()
                if "#" in h:
                    h = h.split("#", 1)[0].rstrip()
                return h.split()[0] if h else h
            except Exception:
                return val

        # Connection parameters - Env-first (Linux-first defaults)
        self.host: str = _sanitize_host(os.environ.get("IB_HOST", "127.0.0.1"))
        try:
            self.port: int = int(os.environ.get("IB_PORT", "4002"))
        except ValueError:
            self.port = 4002
        try:
            self.client_id: int = int(os.environ.get("IB_CLIENT_ID", "2011"))
        except ValueError:
            self.client_id = 2011

        # State management
        self.connected = False
        self.reconnect_attempts = 0
        self.max_reconnect_attempts = 5

        # Pacing control - implements IB rate limits from your checklist
        self.historical_requests: deque[float] = deque(
            maxlen=60
        )  # Track last 60 requests
        self.identical_request_cache: dict[str, float] = {}  # Track identical requests
        self.market_data_subscriptions = 0
        self.max_market_data_subscriptions = 100

        # Event handlers
        self.error_handlers: list[Callable[[dict[str, Any]], None]] = []
        self.disconnect_handlers: list[Callable[[], None]] = []

        # Background tasks
        self._message_processing_task: asyncio.Task[None] | None = None
        self._error_handling_task: asyncio.Task[None] | None = None

    async def connect(  # noqa: C901 - Contains platform/port fallback logic; keep inline for clarity
        self,
        host: str | None = None,
        port: int | None = None,
        clientId: int | None = None,
        timeout: float = 30,
        *,
        fallback: bool = True,
        account_hint: str | None = None,
        autostart: bool = False,
    ) -> bool:
        """
        Connect to IB Gateway/TWS using the canonical connection path.

        Highlights:
        - Uses canonical ib_conn.get_ib_connect_plan() and try_connect_candidates()
        - Explicit timeout handling
        - Better error reporting
        - Automatic pacing setup
        - Optional autostart of Gateway/TWS via project helper when candidates fail
        """

        # Import canonical connection functions
        try:
            from src.infra.ib_conn import get_ib_connect_plan, try_connect_candidates
        except ImportError as e:
            self.logger.error("Cannot import canonical connection functions: %s", e)
            return False

        # If explicit host/port provided, use them directly (bypass canonical plan)
        if host is not None or port is not None or clientId is not None:
            # Sanitize env/arg-sourced host to avoid inline comments causing DNS errors
            def _sanitize_host(val: str) -> str:
                try:
                    s = val.strip()
                    if "#" in s:
                        s = s.split("#", 1)[0].rstrip()
                    return s.split()[0] if s else s
                except Exception:
                    return val

            h = str(_sanitize_host(host)) if host else str(self.host)
            p = int(port) if port is not None else int(self.port)
            cid = int(clientId) if clientId is not None else int(self.client_id)

            # Validate port range to avoid invalid values like 0
            if not (1 <= int(p) <= 65535):
                self.logger.error(f"Invalid port resolved: {p}; refusing to connect")
                return False

            # Single attempt with explicit parameters (no fallback)
            # First attempt: longer handshake timeout (30s default)
            success = await self.client.connect_async(
                h,
                p,
                cid,
                timeout,
                first_attempt=True,
                account_hint=account_hint,
                host_type=None,
            )

            if success:
                self.host, self.port, self.client_id = h, p, cid
                self.connected = True
                self.reconnect_attempts = 0
                try:
                    self.wrapper.set_event_loop(asyncio.get_running_loop())
                except RuntimeError:
                    self.wrapper.set_event_loop(asyncio.get_event_loop())
                self._message_processing_task = asyncio.create_task(
                    self._process_messages()
                )
                self._error_handling_task = asyncio.create_task(self._handle_errors())
                self.logger.info(
                    f"Connected to IB at {self.host}:{self.port} (Client ID: {self.client_id})"
                )
                return True
            # Warmup retry: same host/port with clientId+1 when handshake fails
            self.logger.warning(
                "Handshake did not complete; retrying once with clientId+1 on same socket"
            )
            try:
                await self.disconnect()
            except Exception:
                pass
            cid2 = cid + 1
            success2 = await self.client.connect_async(
                h,
                p,
                cid2,
                max(5.0, timeout),
                first_attempt=False,
                account_hint=account_hint,
                host_type=None,
            )
            if success2:
                self.host, self.port, self.client_id = h, p, cid2
                self.connected = True
                self.reconnect_attempts = 0
                try:
                    self.wrapper.set_event_loop(asyncio.get_running_loop())
                except RuntimeError:
                    self.wrapper.set_event_loop(asyncio.get_event_loop())
                self._message_processing_task = asyncio.create_task(
                    self._process_messages()
                )
                self._error_handling_task = asyncio.create_task(self._handle_errors())
                self.logger.info(
                    f"Connected to IB at {self.host}:{self.port} (Client ID: {self.client_id})"
                )
                return True
            self.logger.error(f"Failed to complete handshake at {h}:{p}")
            return False

        # Use canonical connection plan
        try:
            plan = get_ib_connect_plan()
        except Exception as e:
            self.logger.error("Failed to get canonical connection plan: %s", e)
            return False

        # Respect fallback flag for Windows/portproxy candidates
        if not fallback:
            # Filter out Windows candidates
            plan["candidates"] = [
                p for p in plan["candidates"] if p not in {4003, 4004}
            ]

        self.logger.info(
            "Using canonical connection plan: host=%s, candidates=%s, method=%s",
            plan["host"],
            plan["candidates"],
            plan.get("method", "unknown"),
        )

        # Connect callback for try_connect_candidates
        async def connect_cb(h: str, p: int, cid: int) -> bool:
            # First attempt per port uses first_attempt=True; internal warmup retry handled by connect_async
            return await self.client.connect_async(
                h,
                p,
                cid,
                timeout,
                first_attempt=True,
                account_hint=account_hint,
                host_type=plan.get("host_type"),
            )

        # Try connection using canonical candidate logic
        events: list[dict[str, Any]] = []
        try:
            ok, used_port = await try_connect_candidates(
                connect_cb,
                plan["host"],
                plan["candidates"],
                plan["client_id"],
                autostart=autostart,  # allow caller to opt-in to autostart
                events=events,
            )
        except Exception as e:
            self.logger.error("Connection attempt failed: %s", e)
            return False

        if ok and used_port is not None:
            # Extract the successful clientId from events
            successful_client_id = plan["client_id"]
            for event in events:
                if (
                    event.get("event") == "ib_connected"
                    and event.get("port") == used_port
                ):
                    successful_client_id = event.get("client_id", plan["client_id"])
                    break

            self.host = plan["host"]
            self.port = used_port
            self.client_id = successful_client_id
            self.connected = True
            self.reconnect_attempts = 0

            try:
                self.wrapper.set_event_loop(asyncio.get_running_loop())
            except RuntimeError:
                self.wrapper.set_event_loop(asyncio.get_event_loop())

            self._message_processing_task = asyncio.create_task(
                self._process_messages()
            )
            self._error_handling_task = asyncio.create_task(self._handle_errors())

            self.logger.info(
                f"Connected to IB at {self.host}:{self.port} (Client ID: {self.client_id})"
            )
            return True
        else:
            self.logger.error(
                "Failed to connect using canonical plan: host=%s, candidates=%s",
                plan["host"],
                plan["candidates"],
            )
            return False

    async def disconnect(self) -> None:
        """Graceful disconnect"""
        if self.connected:
            # Cancel background tasks
            if self._message_processing_task:
                self._message_processing_task.cancel()
            if self._error_handling_task:
                self._error_handling_task.cancel()

            await self.client.disconnect_async()
            self.connected = False
            self.logger.info("Disconnected from IB")

    async def _process_messages(self) -> None:
        """Background task to process IB messages"""
        while self.connected:
            try:
                # Process IB messages (non-blocking)
                self.client.run()
                await asyncio.sleep(0.01)  # Small delay to prevent CPU spinning
            except Exception as e:
                self.logger.error(f"Error processing messages: {e}")
                await asyncio.sleep(1)

    async def _handle_errors(self) -> None:
        """Background task to handle IB errors"""
        while self.connected:
            try:
                error_data = await self.wrapper.get_error_events().get()
                await self._process_error(error_data)
            except Exception as e:
                self.logger.error(f"Error in error handler: {e}")

    async def _process_error(self, error_data: ErrorContext) -> None:
        """
        Process IB API errors with smart handling
        Implements error handling from your checklist
        """
        req_id = error_data.get("reqId", -1)
        error_code = error_data.get("errorCode", -1)
        error_string = error_data.get("errorString", "Unknown error")

        self.logger.error(f"IB Error {error_code}: {error_string} (ReqId: {req_id})")

        # Handle specific error codes based on your checklist
        if error_code == 1100:  # Connectivity lost
            self.connected = False
            await self._attempt_reconnect()
        elif error_code == 1102:  # Connectivity restored
            self.connected = True
            self.reconnect_attempts = 0
        elif error_code == 162:  # Pacing violation
            self.logger.warning("Pacing violation - implementing backoff")
            await asyncio.sleep(60)  # 1 minute backoff
        elif error_code == 200:  # No security definition
            self.logger.error(f"Invalid contract for request {req_id}")
        elif error_code == 354:  # Not subscribed to market depth
            self.logger.error(
                f"Market depth subscription required for request {req_id}"
            )
        elif error_code in [10167, 10168]:  # Market data not subscribed
            self.logger.warning(f"Market data subscription issue for request {req_id}")

        # Call registered error handlers (non-async) - convert to dict for compatibility
        error_dict = dict(error_data)  # Convert TypedDict to dict
        for handler in self.error_handlers:
            try:
                handler(error_dict)
            except Exception as e:
                self.logger.error(f"Error in custom error handler: {e}")

    async def _attempt_reconnect(self) -> None:
        """
        Automatic reconnection with exponential backoff
        Implements reconnection strategy from your checklist
        """
        if self.reconnect_attempts >= self.max_reconnect_attempts:
            self.logger.error(
                f"Max reconnection attempts ({self.max_reconnect_attempts}) reached"
            )
            return

        self.reconnect_attempts += 1
        self.client.state = ConnectionState.RECONNECTING

        # Exponential backoff with jitter
        wait_time = min(300, 30 * (2 ** (self.reconnect_attempts - 1)))
        rng = np.random.default_rng()
        jitter = rng.uniform(0.8, 1.2)  # ±20% jitter
        wait_time *= jitter

        self.logger.info(
            f"Reconnection attempt {self.reconnect_attempts}/{self.max_reconnect_attempts} in {wait_time:.1f}s"
        )
        await asyncio.sleep(wait_time)

        success = await self.connect(self.host, self.port, self.client_id)
        if not success:
            await self._attempt_reconnect()

    async def _enforce_historical_pacing(self, contract_key: str) -> None:
        """
        Enforce IB historical data pacing rules from your checklist:
        - Max 60 requests per 10 minutes
        - No identical requests within 15 seconds
        """
        current_time = time.time()

        # Remove old requests (older than 10 minutes)
        cutoff_time = current_time - 600  # 10 minutes
        while self.historical_requests and self.historical_requests[0] < cutoff_time:
            self.historical_requests.popleft()

        # Check 60 requests per 10 minutes limit
        if len(self.historical_requests) >= 60:
            wait_time = 600 - (current_time - self.historical_requests[0])
            if wait_time > 0:
                self.logger.info(
                    f"Historical data pacing limit reached. Waiting {wait_time:.1f}s"
                )
                await asyncio.sleep(wait_time)

        # Check identical request rule (15 seconds)
        last_request_time = self.identical_request_cache.get(contract_key, 0)
        if current_time - last_request_time < 15:
            wait_time = 15 - (current_time - last_request_time)
            self.logger.info(f"Identical request too recent. Waiting {wait_time:.1f}s")
            await asyncio.sleep(wait_time)

        # Record this request
        self.historical_requests.append(current_time)
        self.identical_request_cache[contract_key] = current_time

    def create_stock_contract(
        self, symbol: str, exchange: str = "SMART", currency: str = "USD"
    ) -> Contract:
        """Create stock contract"""
        contract = Contract()
        contract.symbol = symbol
        contract.secType = "STK"
        contract.exchange = exchange
        contract.currency = currency
        return contract

    async def req_historical_data(
        self,
        contract: Contract,
        duration: str = "1 D",
        bar_size: str = "1 min",
        what_to_show: str = "TRADES",
        use_rth: bool = True,
        format_date: int = 1,
        keep_up_to_date: bool = False,
        end_datetime: str | None = None,
    ) -> pd.DataFrame | None:
        """
            Request historical data with pacing control

        Highlights:
            - Automatic pacing enforcement
            - Better error handling
            - Returns pandas DataFrame directly
        """
        if not self.connected:
            self.logger.error("Not connected to IB")
            return None

        req_id = -1  # Initialize to handle cleanup in finally block
        try:
            # Generate contract key for pacing
            contract_key = (
                f"{contract.symbol}_{contract.exchange}_{duration}_{bar_size}"
            )

            # Enforce pacing rules
            await self._enforce_historical_pacing(contract_key)

            # Get request ID and make request
            req_id = self.wrapper.get_next_request_id()
            self.wrapper.set_pending_request(req_id, Symbol(contract.symbol))

            # Request historical data with proper typing
            cast(Any, self.client.reqHistoricalData)(
                reqId=req_id,
                contract=contract,
                endDateTime=end_datetime
                or "",  # Allow targeting a specific session end
                durationStr=duration,
                barSizeSetting=bar_size,
                whatToShow=what_to_show,
                useRTH=use_rth,
                formatDate=format_date,
                keepUpToDate=keep_up_to_date,
                chartOptions=[],
            )

            # Wait for data with timeout
            try:
                response_req_id, bars = await asyncio.wait_for(
                    self.wrapper.get_historical_data_events().get(),
                    timeout=60,  # 60 second timeout
                )

                if response_req_id != req_id:
                    self.logger.warning(
                        f"Request ID mismatch: expected {req_id}, got {response_req_id}"
                    )

                if not bars:
                    self.logger.warning(
                        f"No historical data returned for {contract.symbol}"
                    )
                    return None

                # Convert to DataFrame
                data: list[dict[str, Any]] = []
                for bar in bars:
                    data.append(
                        {
                            "datetime": bar["date"],
                            "open": bar["open"],
                            "high": bar["high"],
                            "low": bar["low"],
                            "close": bar["close"],
                            "volume": bar["volume"],
                            "wap": bar.get("wap", 0.0),
                            "count": bar.get("count", 0),
                        }
                    )

                df = pd.DataFrame(data)
                if not df.empty:
                    df["datetime"] = pd.to_datetime(df["datetime"])
                    df.set_index("datetime", inplace=True)
                    df.sort_index(inplace=True)  # Ensure chronological order

                self.logger.info(f"Retrieved {len(df)} bars for {contract.symbol}")
                return df

            except TimeoutError:
                self.logger.error(
                    f"Historical data request timeout for {contract.symbol}"
                )
                return None

        except Exception as e:
            self.logger.error(f"Historical data request failed: {e}")
            return None
        finally:
            # Clean up
            self.wrapper.remove_pending_request(req_id)
            self.wrapper.remove_historical_data(req_id)

    async def req_market_data(
        self, contract: Contract, generic_tick_list: str = "", snapshot: bool = False
    ) -> int:
        """
            Request real-time market data

        Highlights:
            - Subscription limit checking
            - Better error handling
            - Returns request ID for tracking
        """
        if not self.connected:
            self.logger.error("Not connected to IB")
            return -1

        # Check subscription limits
        if self.market_data_subscriptions >= self.max_market_data_subscriptions:
            self.logger.error(
                f"Market data subscription limit reached ({self.max_market_data_subscriptions})"
            )
            return -1

        try:
            req_id = self.wrapper.get_next_request_id()
            self.wrapper.set_pending_request(req_id, Symbol(contract.symbol))

            # Request market data with proper typing
            cast(Any, self.client.reqMktData)(
                reqId=req_id,
                contract=contract,
                genericTickList=generic_tick_list,
                snapshot=snapshot,
                regulatorySnapshot=False,
                mktDataOptions=[],
            )

            if not snapshot:
                self.market_data_subscriptions += 1

            self.logger.info(
                f"Requested market data for {contract.symbol} (ReqId: {req_id})"
            )
            return req_id

        except Exception as e:
            self.logger.error(f"Market data request failed: {e}")
            return -1

    async def cancel_market_data(self, req_id: int) -> None:
        """Cancel market data subscription"""
        pending_requests = self.wrapper.get_pending_requests()
        if req_id in pending_requests:
            symbol = pending_requests[req_id]
            self.client.cancelMktData(req_id)
            self.wrapper.remove_pending_request(req_id)
            self.market_data_subscriptions = max(0, self.market_data_subscriptions - 1)
            self.logger.info(f"Cancelled market data for {symbol} (ReqId: {req_id})")

    async def req_market_depth(
        self, contract: Contract, num_rows: int = 10, is_smart_depth: bool = False
    ) -> int:
        """
            Request Level 2 market depth data

        Highlights:
            - Smart depth support
            - Better subscription tracking
            - Enhanced error handling
        """
        if not self.connected:
            self.logger.error("Not connected to IB")
            return -1

        try:
            req_id = self.wrapper.get_next_request_id()
            self.wrapper.set_pending_request(req_id, Symbol(contract.symbol))

            # Request market depth with proper typing
            cast(Any, self.client.reqMktDepth)(
                reqId=req_id,
                contract=contract,
                numRows=num_rows,
                isSmartDepth=is_smart_depth,
                mktDepthOptions=[],
            )

            self.logger.info(
                f"Requested market depth for {contract.symbol} (ReqId: {req_id}, Rows: {num_rows})"
            )
            return req_id

        except Exception as e:
            self.logger.error(f"Market depth request failed: {e}")
            return -1

    async def cancel_market_depth(
        self, req_id: int, is_smart_depth: bool = False
    ) -> None:
        """Cancel market depth subscription"""
        pending_requests = self.wrapper.get_pending_requests()
        if req_id in pending_requests:
            symbol = pending_requests[req_id]
            self.client.cancelMktDepth(req_id, is_smart_depth)
            self.wrapper.remove_pending_request(req_id)
            self.logger.info(f"Cancelled market depth for {symbol} (ReqId: {req_id})")

    def get_market_depth(self, symbol: Symbol | str) -> dict[str, Any]:
        """Get current market depth for symbol"""
        sym: Symbol = Symbol(str(symbol))
        return self.wrapper.get_market_depth(sym)

    def get_last_price(self, symbol: Symbol | str) -> float | None:
        """Get last known price for symbol"""
        sym: Symbol = Symbol(str(symbol))
        return self.wrapper.get_last_price(sym)

    async def stream_market_data(
        self, contract: Contract, callback: Callable[[dict[str, Any]], None]
    ) -> int:
        """
        Stream real-time market data with callback
        Convenience method for continuous data processing
        """
        req_id = await self.req_market_data(contract)

        if req_id > 0:
            # Start background task to process ticks
            async def tick_processor() -> None:
                pending_requests = self.wrapper.get_pending_requests()
                while req_id in pending_requests:
                    try:
                        tick_data = await self.wrapper.get_market_data_events().get()
                        if tick_data["symbol"] == contract.symbol:
                            callback(tick_data)
                    except Exception as e:
                        self.logger.error(f"Error in tick processor: {e}")

            asyncio.create_task(tick_processor())

        return req_id

    async def stream_market_depth(
        self,
        contract: Contract,
        callback: Callable[[dict[str, Any]], None],
        num_rows: int = 10,
    ) -> int:
        """
        Stream Level 2 market depth with callback
        Optimized for ML feature extraction
        """
        req_id = await self.req_market_depth(contract, num_rows)

        if req_id > 0:
            # Start background task to process depth updates
            async def depth_processor() -> None:
                pending_requests = self.wrapper.get_pending_requests()
                while req_id in pending_requests:
                    try:
                        depth_data = await self.wrapper.get_market_depth_events().get()
                        if depth_data["symbol"] == contract.symbol:
                            callback(depth_data)
                    except Exception as e:
                        self.logger.error(f"Error in depth processor: {e}")

            asyncio.create_task(depth_processor())

        return req_id

    def add_error_handler(self, handler: Callable[[dict[str, Any]], None]) -> None:
        """Add custom error handler"""
        self.error_handlers.append(handler)

    def add_disconnect_handler(self, handler: Callable[[], None]) -> None:
        """Add custom disconnect handler"""
        self.disconnect_handlers.append(handler)


# Convenience functions for compatibility with existing code
def Stock(symbol: str, exchange: str = "SMART", currency: str = "USD") -> Contract:
    """Create stock contract"""
    contract = Contract()
    contract.symbol = symbol
    contract.secType = "STK"
    contract.exchange = exchange
    contract.currency = currency
    return contract


def util_df(bars: list[dict[str, Any]]) -> pd.DataFrame:
    """Convert bars to DataFrame"""
    data: list[dict[str, Any]] = []
    for bar in bars:
        data.append(
            {
                "date": bar["date"],
                "open": bar["open"],
                "high": bar["high"],
                "low": bar["low"],
                "close": bar["close"],
                "volume": bar["volume"],
                "wap": bar.get("wap", 0.0),
                "count": bar.get("count", 0),
            }
        )

    df = pd.DataFrame(data)
    if not df.empty:
        df["date"] = pd.to_datetime(df["date"])
        df.set_index("date", inplace=True)

    return df


# Main class alias for easy migration
IB = IBAsync

if __name__ == "__main__":
    # Demo usage using canonical connection path
    async def main() -> None:
        ib = IBAsync()

        # Connect using canonical connection path (no explicit parameters)
        connected = await ib.connect()
        if not connected:
            print("Failed to connect")
            return

        # Create contract
        contract = Stock("AAPL")

        # Get historical data
        df = await ib.req_historical_data(contract, "1 D", "1 min")
        if df is not None:
            print(f"Retrieved {len(df)} bars")
            print(df.head())

        # Start market data stream
        def tick_handler(tick_data: dict[str, Any]) -> None:
            print(
                f"Tick: {tick_data['symbol']} {tick_data['tick_type']} {tick_data['value']}"
            )

        req_id = await ib.stream_market_data(contract, tick_handler)

        # Let it run for a bit
        await asyncio.sleep(10)

        # Cleanup
        await ib.cancel_market_data(req_id)
        await ib.disconnect()

    # Run demo
    asyncio.run(main())
