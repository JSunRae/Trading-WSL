#!/usr/bin/env python3
"""
Modern async wrapper for Interactive Brokers API
Replaces ib_insync with native asyncio support
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict, deque
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any, cast, override

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
class HistoricalBar:
    """Historical bar data structure"""

    date: datetime
    open: Price
    high: Price
    low: Price
    close: Price
    volume: Volume
    wap: Price  # Weighted average price
    count: int  # Number of trades

    @classmethod
    def from_ib_bar(cls, bar: BarData) -> HistoricalBar:
        """Create from IB BarData"""
        return cls(
            date=pd.to_datetime(bar.date),
            open=bar.open,
            high=bar.high,
            low=bar.low,
            close=bar.close,
            volume=bar.volume,
            wap=getattr(bar, "wap", 0.0),  # Some versions don't have wap
            count=getattr(bar, "count", 0),  # Some versions don't have count
        )


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
    Replaces ib_insync's synchronous event handling with async queues
    """

    def __init__(self) -> None:
        EWrapper.__init__(self)
        self.logger: logging.Logger = logging.getLogger(__name__)

        # Event queues for async communication - properly typed
        self._connection_events: asyncio.Queue[tuple[str, bool]] = asyncio.Queue()
        self._error_events: asyncio.Queue[ErrorContext] = asyncio.Queue()
        self._historical_data_events: asyncio.Queue[
            tuple[RequestId, list[dict[str, Any]]]
        ] = asyncio.Queue()
        self._market_data_events: asyncio.Queue[dict[str, Any]] = (
            asyncio.Queue()
        )  # Simplified for now
        self._market_depth_events: asyncio.Queue[dict[str, Any]] = (
            asyncio.Queue()
        )  # Simplified for now
        self._order_events: asyncio.Queue[Any] = (
            asyncio.Queue()
        )  # TODO: Define proper order event type

        # Data storage - properly typed
        self._historical_data: dict[RequestId, list[dict[str, Any]]] = {}
        self._market_depth: dict[
            Symbol, dict[str, dict[int, dict[str, Price | Volume]]]
        ] = defaultdict(lambda: {"bids": {}, "asks": {}})
        self._last_prices: dict[Symbol, Price] = {}

        # Request tracking - properly typed
        self._pending_requests: dict[RequestId, Symbol] = {}
        self._request_id: RequestId = 1000

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
    @override
    def connectAck(self) -> None:
        """Connection acknowledged"""
        asyncio.create_task(self._connection_events.put(("connected", True)))

    @override
    def connectionClosed(self) -> None:
        """Connection closed"""
        asyncio.create_task(self._connection_events.put(("disconnected", True)))

    # Error handling
    @override
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
        asyncio.create_task(self._error_events.put(error_data))

    # Historical data callbacks
    @override
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

    @override
    def historicalDataEnd(self, reqId: int, start: str, end: str) -> None:
        """Historical data download complete"""
        bars = self._historical_data.get(reqId, [])
        asyncio.create_task(self._historical_data_events.put((reqId, bars)))

    # Market data callbacks
    @override
    def tickPrice(
        self, reqId: TickerId, tickType: int, price: float, attrib: Any
    ) -> None:
        """Real-time price tick"""
        symbol = self._pending_requests.get(reqId, "UNKNOWN")
        tick_data = {
            "symbol": symbol,
            "tick_type": tickType,
            "value": price,
            "timestamp": datetime.now(UTC),
        }

        # Store last price for reference
        if tickType in [1, 2, 4]:  # Bid, Ask, Last
            self._last_prices[symbol] = Price(price)

        asyncio.create_task(self._market_data_events.put(tick_data))

    @override
    def tickSize(self, reqId: TickerId, tickType: int, size: int) -> None:
        """Real-time size tick"""
        symbol = self._pending_requests.get(reqId, "UNKNOWN")
        tick_data = {
            "symbol": symbol,
            "tick_type": tickType,
            "value": float(size),
            "timestamp": datetime.now(UTC),
        }
        asyncio.create_task(self._market_data_events.put(tick_data))

    # Market depth callbacks
    @override
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
        symbol = self._pending_requests.get(reqId, "UNKNOWN")
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
            depth_dict[position] = {"price": Price(price), "size": Volume(size)}
        elif operation == 2:  # Delete
            depth_dict.pop(position, None)

        asyncio.create_task(self._market_depth_events.put(depth_data))

    @override
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
        symbol = self._pending_requests.get(reqId, "UNKNOWN")
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
        asyncio.create_task(self._market_depth_events.put(depth_data))


class AsyncIBClient(EClient):
    """
    Async client for IB API
    Replaces ib_insync's connection management with pure asyncio
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

    async def disconnect_async(self):
        """Async disconnect"""
        if self.state == ConnectionState.CONNECTED:
            self.disconnect()
            self.state = ConnectionState.DISCONNECTED


class IBAsync:
    """
    Main async IB interface - replaces ib_insync.IB

    Key improvements over ib_insync:
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

        # Connection parameters - Updated for IB Gateway
        self.host = "127.0.0.1"
        self.port = 4002  # IB Gateway Paper Trading (4001 for Live)
        self.client_id = 1

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

    async def connect(
        self,
        host: str = "127.0.0.1",
        port: int = 4002,
        clientId: int = 1,
        timeout: float = 30,
    ) -> bool:
        """
        Connect to IB Gateway/TWS with automatic reconnection

        Key improvements over ib_insync:
        - Explicit timeout handling
        - Better error reporting
        - Automatic pacing setup
        """
        self.host = host
        self.port = port
        self.client_id = clientId

        success = await self.client.connect_async(host, port, clientId, timeout)

        if success:
            self.connected = True
            self.reconnect_attempts = 0

            # Start background tasks
            self._message_processing_task = asyncio.create_task(
                self._process_messages()
            )
            self._error_handling_task = asyncio.create_task(self._handle_errors())

            self.logger.info(
                f"Connected to IB at {host}:{port} (Client ID: {clientId})"
            )
        else:
            self.logger.error(f"Failed to connect to IB at {host}:{port}")

        return success

    async def disconnect(self):
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

    async def _process_messages(self):
        """Background task to process IB messages"""
        while self.connected:
            try:
                # Process IB messages (non-blocking)
                self.client.run()
                await asyncio.sleep(0.01)  # Small delay to prevent CPU spinning
            except Exception as e:
                self.logger.error(f"Error processing messages: {e}")
                await asyncio.sleep(1)

    async def _handle_errors(self):
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

    async def _attempt_reconnect(self):
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
        jitter = np.random.uniform(0.8, 1.2)  # ±20% jitter
        wait_time *= jitter

        self.logger.info(
            f"Reconnection attempt {self.reconnect_attempts}/{self.max_reconnect_attempts} in {wait_time:.1f}s"
        )
        await asyncio.sleep(wait_time)

        success = await self.connect(self.host, self.port, self.client_id)
        if not success:
            await self._attempt_reconnect()

    async def _enforce_historical_pacing(self, contract_key: str):
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
        """Create stock contract - replaces ib_insync.Stock"""
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
    ) -> pd.DataFrame | None:
        """
        Request historical data with pacing control

        Key improvements over ib_insync:
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
            self.wrapper.set_pending_request(req_id, contract.symbol)

            # Request historical data with proper typing
            cast(Any, self.client.reqHistoricalData)(
                reqId=req_id,
                contract=contract,
                endDateTime="",  # Current time
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

        Key improvements over ib_insync:
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
            self.wrapper.set_pending_request(req_id, contract.symbol)

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

    async def cancel_market_data(self, req_id: int):
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

        Key improvements over ib_insync:
        - Smart depth support
        - Better subscription tracking
        - Enhanced error handling
        """
        if not self.connected:
            self.logger.error("Not connected to IB")
            return -1

        try:
            req_id = self.wrapper.get_next_request_id()
            self.wrapper.set_pending_request(req_id, contract.symbol)

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

    async def cancel_market_depth(self, req_id: int, is_smart_depth: bool = False):
        """Cancel market depth subscription"""
        pending_requests = self.wrapper.get_pending_requests()
        if req_id in pending_requests:
            symbol = pending_requests[req_id]
            self.client.cancelMktDepth(req_id, is_smart_depth)
            self.wrapper.remove_pending_request(req_id)
            self.logger.info(f"Cancelled market depth for {symbol} (ReqId: {req_id})")

    def get_market_depth(self, symbol: str) -> dict[str, Any]:
        """Get current market depth for symbol"""
        return self.wrapper.get_market_depth(symbol)

    def get_last_price(self, symbol: str) -> float | None:
        """Get last known price for symbol"""
        return self.wrapper.get_last_price(symbol)

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
            async def tick_processor():
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
            async def depth_processor():
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
    """Create stock contract - direct replacement for ib_insync.Stock"""
    contract = Contract()
    contract.symbol = symbol
    contract.secType = "STK"
    contract.exchange = exchange
    contract.currency = currency
    return contract


def util_df(bars: list[dict[str, Any]]) -> pd.DataFrame:
    """Convert bars to DataFrame - replacement for ib_insync.util.df"""
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
    async def main():
        ib = IBAsync()

        # Connect
        connected = await ib.connect("127.0.0.1", 7497, 1)
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
