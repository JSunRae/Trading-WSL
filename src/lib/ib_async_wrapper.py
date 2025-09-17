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
        self._connection_events: asyncio.Queue[tuple[str, bool]] = asyncio.Queue()
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
    def get_connection_events(self) -> asyncio.Queue[tuple[str, bool]]:
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
        self._enqueue(self._connection_events, ("connected", True))

    def connectionClosed(self) -> None:
        """Connection closed"""
        self._enqueue(self._connection_events, ("disconnected", True))

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
            self._historical_data.pop(reqId, None)
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

    async def connect_async(
        self, host: str, port: int, clientId: int, timeout: float = 30
    ) -> bool:
        """
        Async connection to IB Gateway/TWS
        Key improvement: Non-blocking connection with timeout
        """
        async with self._connection_lock:
            try:
                self.state = ConnectionState.CONNECTING

                # Start connection in thread (IB API is not async)
                loop = asyncio.get_event_loop()

                # Properly typed connection function
                def connect_func() -> None:
                    cast(Any, self.connect)(host, port, clientId)

                connect_task = loop.run_in_executor(None, connect_func)

                # Wait for connection with timeout
                try:
                    await asyncio.wait_for(connect_task, timeout=timeout)
                except TimeoutError:
                    self.state = ConnectionState.FAILED
                    return False

                # Wait for connection acknowledgment
                try:
                    event, _ = await asyncio.wait_for(
                        self.wrapper.get_connection_events().get(), timeout=10
                    )
                    if event == "connected":
                        self.state = ConnectionState.CONNECTED
                        return True
                except TimeoutError:
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

        # Connection parameters - Env-first (WSL→Windows portproxy friendly)
        self.host = _sanitize_host(os.environ.get("IB_HOST", "172.17.208.1"))
        try:
            self.port = int(os.environ.get("IB_PORT", "4003"))
        except ValueError:
            self.port = 4003
        try:
            self.client_id = int(os.environ.get("IB_CLIENT_ID", "2011"))
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
    ) -> bool:
        """
        Connect to IB Gateway/TWS with automatic reconnection.

        Highlights:
        - Explicit timeout handling
        - Better error reporting
        - Automatic pacing setup
        """

        # Resolve env-first defaults when not explicitly provided
        # Sanitize env/arg-sourced host to avoid inline comments causing DNS errors
        def _sanitize_host(val: str) -> str:
            try:
                s = val.strip()
                if "#" in s:
                    s = s.split("#", 1)[0].rstrip()
                return s.split()[0] if s else s
            except Exception:
                return val

        h = (
            _sanitize_host(host)
            if host
            else _sanitize_host(os.environ.get("IB_HOST", "172.17.208.1"))
        )
        try:
            p = int(port if port is not None else os.environ.get("IB_PORT", "4003"))
        except ValueError:
            p = 4003
        try:
            cid = int(
                clientId
                if clientId is not None
                else os.environ.get("IB_CLIENT_ID", "2011")
            )
        except ValueError:
            cid = 2011

        self.host = h
        self.port = p
        self.client_id = cid

        # Primary attempt
        success = await self.client.connect_async(h, p, cid, timeout)

        if success:
            self.connected = True
            self.reconnect_attempts = 0
            # Capture current event loop for thread-safe wrapper enqueues
            try:
                self.wrapper.set_event_loop(asyncio.get_running_loop())
            except RuntimeError:
                # If no running loop, try default loop
                self.wrapper.set_event_loop(asyncio.get_event_loop())

            # Start background tasks
            self._message_processing_task = asyncio.create_task(
                self._process_messages()
            )
            self._error_handling_task = asyncio.create_task(self._handle_errors())

            self.logger.info(
                f"Connected to IB at {self.host}:{self.port} (Client ID: {self.client_id})"
            )
        else:
            if not fallback:
                # Caller requested no platform fallback; return immediate failure
                return False
            self.logger.error(f"Failed to connect to IB at {h}:{p}")
            # WSL fallback: if running inside WSL, try Windows host IPs and common ports.
            # Also include an early TCP probe to give actionable hints when the port is open
            # but the API handshake is rejected by settings (e.g., Trusted IPs).
            import socket
            from pathlib import Path

            # Helper: enumerate Windows IPv4 addresses from WSL via PowerShell (best-effort)
            def _windows_ipv4_addrs() -> list[str]:
                addrs: list[str] = []
                try:
                    import re
                    import subprocess

                    out = subprocess.check_output(
                        [
                            "powershell.exe",
                            "-NoProfile",
                            "-Command",
                            "Get-NetIPAddress -AddressFamily IPv4 | Select-Object -ExpandProperty IPAddress",
                        ],
                        timeout=3,
                    )
                    # Decode possibly CRLF and Windows-1252; fallback to utf-8
                    text = out.decode(errors="ignore").replace("\r", "")
                    for line in text.splitlines():
                        line = line.strip()
                        if re.match(r"^\d+\.\d+\.\d+\.\d+$", line):
                            addrs.append(line)
                except Exception:
                    pass
                return addrs

            # Detect WSL
            wsl = False
            try:
                text = Path("/proc/version").read_text(
                    encoding="utf-8", errors="ignore"
                )
                if "microsoft" in text.lower():
                    wsl = True
            except Exception:
                wsl = False

            candidates: list[tuple[str, int]] = []
            port_order: list[int] = []
            # Prefer the requested port first
            if p not in port_order:
                port_order.append(p)
            # Then common ports (include WSL portproxy 4003 early)
            for _pp in [4003, 4002, 4001, 7497, 7496]:
                if _pp not in port_order:
                    port_order.append(_pp)

            if wsl:
                # 1) Nameserver IP (Windows host in many WSL distros)
                try:
                    import re as _re

                    ns_ip = None
                    for line in (
                        Path("/etc/resolv.conf")
                        .read_text(encoding="utf-8", errors="ignore")
                        .splitlines()
                    ):
                        m = _re.match(r"^nameserver\s+(\S+)", line)
                        if m:
                            ns_ip = m.group(1)
                            break
                    if ns_ip:
                        for p in port_order:
                            candidates.append((ns_ip, p))
                except Exception:
                    pass

                # 2) Any Windows IPv4 addresses (covers Wi-Fi/Ethernet/vEthernet)
                for addr in _windows_ipv4_addrs():
                    for p in port_order:
                        candidates.append((addr, p))

                # 3) Loopback with alternate ports (if Gateway was forwarded to localhost)
                for p in port_order:
                    candidates.append(("127.0.0.1", p))

            # De-duplicate preserving order and skip the original attempt
            seen: set[tuple[str, int]] = set()
            uniq: list[tuple[str, int]] = []
            for c in candidates:
                if c not in seen and not (c[0] == h and c[1] == p):
                    uniq.append(c)
                    seen.add(c)

            # Try candidates with a short timeout; if TCP is open but API handshake fails,
            # emit a targeted hint about IB API settings.
            for h, p in uniq:
                # Quick TCP probe
                tcp_open = False
                s: socket.socket | None = None
                try:
                    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    s.settimeout(1.5)
                    tcp_open = s.connect_ex((h, p)) == 0
                except Exception:
                    tcp_open = False
                finally:
                    try:
                        if s is not None:
                            s.close()
                    except Exception:
                        pass

                self.logger.info("Retrying IB connect via candidate %s:%s", h, p)
                if await self.client.connect_async(h, p, cid, 10):
                    self.host, self.port = h, p
                    self.connected = True
                    try:
                        self.wrapper.set_event_loop(asyncio.get_running_loop())
                    except RuntimeError:
                        self.wrapper.set_event_loop(asyncio.get_event_loop())
                    self._message_processing_task = asyncio.create_task(
                        self._process_messages()
                    )
                    self._error_handling_task = asyncio.create_task(
                        self._handle_errors()
                    )
                    self.logger.info(
                        "Connected to IB at %s:%s (Client ID: %s)", h, p, cid
                    )
                    return True
                else:
                    if tcp_open:
                        # Port is open but handshake failed: provide actionable guidance
                        self.logger.error(
                            "TCP %s:%s is reachable but API handshake failed. "
                            "Check IB Gateway/TWS API settings: enable 'ActiveX and Socket Clients', "
                            "uncheck 'Allow connections from localhost only' or add your WSL/host IP to Trusted IPs, "
                            "and allow the port through Windows Firewall.",
                            h,
                            p,
                        )

        return success

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
    # Demo usage
    async def main() -> None:
        import os

        ib = IBAsync()

        # Connect (env-first with WSL defaults)
    h = os.environ.get("IB_HOST", "172.17.208.1")
    p = int(os.environ.get("IB_PORT", "4003"))
    cid = int(os.environ.get("IB_CLIENT_ID", "2011"))
        connected = await ib.connect(h, p, cid)
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
