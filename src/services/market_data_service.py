#!/usr/bin/env python3
"""
Market Data Service

This service handles real-time market data streams from Interactive Brokers
with modern architecture patterns: error handling, connection pooling,
and high-performance data processing.

This modernizes market data functionality from the monolithic system.
"""

import logging
import sys
import threading
import time
from collections import defaultdict, deque
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from queue import Empty, Full, Queue
from typing import Any

import pandas as pd

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.config import get_config
from src.core.integrated_error_handling import with_error_handling
from src.data.parquet_repository import ParquetRepository


class MarketDataType(Enum):
    """Types of market data"""

    TICK_PRICE = "tick_price"
    TICK_SIZE = "tick_size"
    TICK_GENERIC = "tick_generic"
    TICK_STRING = "tick_string"
    TICK_EFP = "tick_efp"
    TICK_TIMESTAMP = "tick_timestamp"
    TICK_RT_VOLUME = "tick_rt_volume"
    TICK_HALTED = "tick_halted"
    TICK_BID_ASK = "tick_bid_ask"
    TICK_LAST = "tick_last"


class TickType(Enum):
    """IB Tick types"""

    BID_SIZE = 0
    BID_PRICE = 1
    ASK_PRICE = 2
    ASK_SIZE = 3
    LAST_PRICE = 4
    LAST_SIZE = 5
    HIGH = 6
    LOW = 7
    VOLUME = 8
    CLOSE = 9
    BID_OPTION = 10
    ASK_OPTION = 11
    LAST_OPTION = 12
    MODEL_OPTION = 13
    OPEN = 14
    LOW_13_WEEK = 15
    HIGH_13_WEEK = 16
    LOW_26_WEEK = 17
    HIGH_26_WEEK = 18
    LOW_52_WEEK = 19
    HIGH_52_WEEK = 20
    AVG_VOLUME = 21


@dataclass
class MarketDataTick:
    """Single market data tick"""

    symbol: str
    tick_type: TickType
    value: float
    timestamp: datetime = field(default_factory=datetime.now)
    size: int | None = None
    exchange: str | None = None


@dataclass
class MarketDataSnapshot:
    """Current market data snapshot for a symbol"""

    symbol: str
    bid_price: float | None = None
    bid_size: int | None = None
    ask_price: float | None = None
    ask_size: int | None = None
    last_price: float | None = None
    last_size: int | None = None
    volume: int | None = None
    high: float | None = None
    low: float | None = None
    open: float | None = None
    close: float | None = None
    timestamp: datetime = field(default_factory=datetime.now)

    @property
    def spread(self) -> float | None:
        """Calculate bid-ask spread"""
        if self.bid_price and self.ask_price:
            return self.ask_price - self.bid_price
        return None

    @property
    def mid_price(self) -> float | None:
        """Calculate mid price"""
        if self.bid_price and self.ask_price:
            return (self.bid_price + self.ask_price) / 2
        return None


@dataclass
class StreamConfig:
    """Configuration for market data stream"""

    symbol: str
    tick_types: list[TickType] = field(
        default_factory=lambda: [
            TickType.BID_PRICE,
            TickType.BID_SIZE,
            TickType.ASK_PRICE,
            TickType.ASK_SIZE,
            TickType.LAST_PRICE,
            TickType.LAST_SIZE,
            TickType.VOLUME,
        ]
    )
    snapshot: bool = False  # True for snapshot, False for streaming
    regulatory_snapshot: bool = False
    timeout: float = 30.0


class MarketDataService:
    """Modern market data service with enterprise features"""

    def __init__(self):
        self.config = get_config()
        self.parquet_repo = ParquetRepository()
        self.logger = logging.getLogger(__name__)

        # Streaming infrastructure
        self.active_streams: dict[str, StreamConfig] = {}
        self.market_data_queue = Queue(maxsize=10000)
        self.snapshots: dict[str, MarketDataSnapshot] = {}
        self.tick_history: dict[str, deque] = defaultdict(lambda: deque(maxlen=1000))

        # Event handlers
        self.tick_handlers: list[Callable[[MarketDataTick], None]] = []
        self.snapshot_handlers: list[Callable[[MarketDataSnapshot], None]] = []

        # Performance tracking
        self.stream_stats = {
            "active_streams": 0,
            "total_ticks_received": 0,
            "ticks_per_second": 0.0,
            "last_tick_time": None,
            "stream_start_time": None,
            "errors": 0,
            "reconnections": 0,
        }

        # Threading
        self.processing_thread = None
        self.running = False
        self._lock = threading.Lock()

    @with_error_handling("market_data")
    def start_market_data_stream(self, connection, stream_config: StreamConfig) -> bool:
        """Start market data stream for a symbol"""

        try:
            # Validate symbol
            if not stream_config.symbol:
                raise ValueError("Symbol is required")

            # Create IB contract
            contract = self._create_contract(stream_config.symbol)
            if contract is None:
                raise ValueError(
                    f"Failed to create contract for {stream_config.symbol}"
                )

            # Start streaming thread if not running
            if not self.running:
                self._start_processing_thread()

            # Register stream
            with self._lock:
                self.active_streams[stream_config.symbol] = stream_config
                self.snapshots[stream_config.symbol] = MarketDataSnapshot(
                    symbol=stream_config.symbol
                )
                self.stream_stats["active_streams"] = len(self.active_streams)

            # Request market data from IB
            success = self._request_market_data(connection, contract, stream_config)

            if success:
                self.logger.info(
                    f"Started market data stream for {stream_config.symbol}"
                )
                if self.stream_stats["stream_start_time"] is None:
                    self.stream_stats["stream_start_time"] = datetime.now()
                return True
            else:
                # Clean up on failure
                with self._lock:
                    self.active_streams.pop(stream_config.symbol, None)
                    self.snapshots.pop(stream_config.symbol, None)
                    self.stream_stats["active_streams"] = len(self.active_streams)
                return False

        except Exception as e:
            self.stream_stats["errors"] += 1
            self.logger.error(
                f"Failed to start market data stream for {stream_config.symbol}: {e}"
            )
            raise

    @with_error_handling("market_data")
    def stop_market_data_stream(self, connection, symbol: str) -> bool:
        """Stop market data stream for a symbol"""

        try:
            if symbol not in self.active_streams:
                self.logger.warning(f"No active stream for {symbol}")
                return False

            # Cancel market data from IB
            success = self._cancel_market_data(connection, symbol)

            # Clean up
            with self._lock:
                self.active_streams.pop(symbol, None)
                self.snapshots.pop(symbol, None)
                self.tick_history.pop(symbol, None)
                self.stream_stats["active_streams"] = len(self.active_streams)

            # Stop processing thread if no active streams
            if not self.active_streams and self.running:
                self._stop_processing_thread()

            if success:
                self.logger.info(f"Stopped market data stream for {symbol}")
                return True
            else:
                self.stream_stats["errors"] += 1
                return False

        except Exception as e:
            self.stream_stats["errors"] += 1
            self.logger.error(f"Failed to stop market data stream for {symbol}: {e}")
            raise

    def get_market_data_snapshot(self, symbol: str) -> MarketDataSnapshot | None:
        """Get current market data snapshot for symbol"""

        with self._lock:
            return self.snapshots.get(symbol)

    def get_multiple_snapshots(
        self, symbols: list[str]
    ) -> dict[str, MarketDataSnapshot | None]:
        """Get snapshots for multiple symbols"""

        snapshots = {}
        with self._lock:
            for symbol in symbols:
                snapshots[symbol] = self.snapshots.get(symbol)

        return snapshots

    def get_tick_history(
        self, symbol: str, max_ticks: int = 100
    ) -> list[MarketDataTick]:
        """Get recent tick history for symbol"""

        with self._lock:
            history = self.tick_history.get(symbol, deque())
            return list(history)[-max_ticks:]

    def add_tick_handler(self, handler: Callable[[MarketDataTick], None]):
        """Add callback for tick events"""
        self.tick_handlers.append(handler)

    def add_snapshot_handler(self, handler: Callable[[MarketDataSnapshot], None]):
        """Add callback for snapshot updates"""
        self.snapshot_handlers.append(handler)

    def _start_processing_thread(self):
        """Start the market data processing thread"""

        if not self.running:
            self.running = True
            self.processing_thread = threading.Thread(
                target=self._process_market_data, daemon=True
            )
            self.processing_thread.start()
            self.logger.info("Market data processing thread started")

    def _stop_processing_thread(self):
        """Stop the market data processing thread"""

        if self.running:
            self.running = False
            if self.processing_thread:
                self.processing_thread.join(timeout=5.0)
            self.logger.info("Market data processing thread stopped")

    def _process_market_data(self):
        """Main processing loop for market data"""

        last_stats_update = time.time()
        tick_count_window = []

        while self.running:
            try:
                # Process queued ticks
                try:
                    tick = self.market_data_queue.get(timeout=0.1)
                    self._process_tick(tick)

                    # Update statistics
                    self.stream_stats["total_ticks_received"] += 1
                    self.stream_stats["last_tick_time"] = datetime.now()

                    # Track ticks per second
                    current_time = time.time()
                    tick_count_window.append(current_time)

                    # Update TPS every second
                    if current_time - last_stats_update >= 1.0:
                        # Count ticks in last second
                        cutoff_time = current_time - 1.0
                        tick_count_window = [
                            t for t in tick_count_window if t > cutoff_time
                        ]
                        self.stream_stats["ticks_per_second"] = len(tick_count_window)
                        last_stats_update = current_time

                except Empty:
                    continue  # No ticks to process

            except Exception as e:
                self.stream_stats["errors"] += 1
                self.logger.error(f"Error processing market data: {e}")
                time.sleep(0.1)  # Brief pause on error

    def _process_tick(self, tick: MarketDataTick):
        """Process a single market data tick"""

        try:
            # Update snapshot
            with self._lock:
                snapshot = self.snapshots.get(tick.symbol)
                if snapshot:
                    self._update_snapshot(snapshot, tick)

                    # Store in tick history
                    self.tick_history[tick.symbol].append(tick)

            # Call tick handlers
            for handler in self.tick_handlers:
                try:
                    handler(tick)
                except Exception as e:
                    self.logger.error(f"Error in tick handler: {e}")

            # Call snapshot handlers
            if snapshot:
                for handler in self.snapshot_handlers:
                    try:
                        handler(snapshot)
                    except Exception as e:
                        self.logger.error(f"Error in snapshot handler: {e}")

        except Exception as e:
            self.logger.error(f"Error processing tick for {tick.symbol}: {e}")

    def _update_snapshot(self, snapshot: MarketDataSnapshot, tick: MarketDataTick):
        """Update market data snapshot with new tick"""

        # Update timestamp
        snapshot.timestamp = tick.timestamp

        # Update based on tick type
        if tick.tick_type == TickType.BID_PRICE:
            snapshot.bid_price = tick.value
        elif tick.tick_type == TickType.BID_SIZE:
            snapshot.bid_size = int(tick.value) if tick.value else None
        elif tick.tick_type == TickType.ASK_PRICE:
            snapshot.ask_price = tick.value
        elif tick.tick_type == TickType.ASK_SIZE:
            snapshot.ask_size = int(tick.value) if tick.value else None
        elif tick.tick_type == TickType.LAST_PRICE:
            snapshot.last_price = tick.value
        elif tick.tick_type == TickType.LAST_SIZE:
            snapshot.last_size = int(tick.value) if tick.value else None
        elif tick.tick_type == TickType.VOLUME:
            snapshot.volume = int(tick.value) if tick.value else None
        elif tick.tick_type == TickType.HIGH:
            snapshot.high = tick.value
        elif tick.tick_type == TickType.LOW:
            snapshot.low = tick.value
        elif tick.tick_type == TickType.OPEN:
            snapshot.open = tick.value
        elif tick.tick_type == TickType.CLOSE:
            snapshot.close = tick.value

    def _create_contract(self, symbol: str):
        """Create IB contract for symbol"""

        # Mock contract creation - in real implementation, this would use IB API
        mock_contract = {
            "symbol": symbol,
            "secType": "STK",
            "exchange": "SMART",
            "currency": "USD",
            "conId": hash(symbol) % 100000,  # Mock contract ID
        }

        return mock_contract

    def _request_market_data(
        self, connection, contract, stream_config: StreamConfig
    ) -> bool:
        """Request market data from IB"""

        # Mock implementation - in real code, this would use IB API
        # For demonstration, simulate market data ticks

        def generate_mock_ticks():
            import random
            import threading

            def tick_generator():
                base_price = 100.0 + random.uniform(-10, 10)

                while stream_config.symbol in self.active_streams:
                    try:
                        # Generate bid/ask
                        spread = random.uniform(0.01, 0.10)
                        mid_price = base_price + random.uniform(-0.50, 0.50)
                        bid_price = mid_price - spread / 2
                        ask_price = mid_price + spread / 2

                        # Create ticks
                        ticks = [
                            MarketDataTick(
                                symbol=stream_config.symbol,
                                tick_type=TickType.BID_PRICE,
                                value=bid_price,
                            ),
                            MarketDataTick(
                                symbol=stream_config.symbol,
                                tick_type=TickType.ASK_PRICE,
                                value=ask_price,
                            ),
                            MarketDataTick(
                                symbol=stream_config.symbol,
                                tick_type=TickType.BID_SIZE,
                                value=random.randint(100, 1000),
                            ),
                            MarketDataTick(
                                symbol=stream_config.symbol,
                                tick_type=TickType.ASK_SIZE,
                                value=random.randint(100, 1000),
                            ),
                        ]

                        # Queue ticks
                        for tick in ticks:
                            try:
                                self.market_data_queue.put_nowait(tick)
                            except Full:
                                # Fallback to blocking put with short timeout; drop if still full
                                try:
                                    self.market_data_queue.put(tick, timeout=0.01)
                                except Full:
                                    pass

                        # Update base price slowly
                        base_price += random.uniform(-0.01, 0.01)
                        base_price = max(1.0, base_price)

                        time.sleep(0.1)  # 10 ticks per second

                    except Exception as e:
                        self.logger.error(f"Error generating mock ticks: {e}")
                        break

            # Start tick generation in background thread
            generator_thread = threading.Thread(target=tick_generator, daemon=True)
            generator_thread.start()

        # Start mock data generation
        generate_mock_ticks()

        return True

    def _cancel_market_data(self, connection, symbol: str) -> bool:
        """Cancel market data from IB"""

        # Mock implementation
        self.logger.info(f"Cancelled market data for {symbol}")
        return True

    def save_snapshots_to_parquet(self, filename: str | None = None) -> bool:
        """Save current snapshots to Parquet file"""

        try:
            with self._lock:
                if not self.snapshots:
                    self.logger.warning("No snapshots to save")
                    return False

                # Convert snapshots to DataFrame
                snapshot_data = []
                for _symbol, snapshot in self.snapshots.items():
                    snapshot_data.append(
                        {
                            "symbol": snapshot.symbol,
                            "bid_price": snapshot.bid_price,
                            "bid_size": snapshot.bid_size,
                            "ask_price": snapshot.ask_price,
                            "ask_size": snapshot.ask_size,
                            "last_price": snapshot.last_price,
                            "last_size": snapshot.last_size,
                            "volume": snapshot.volume,
                            "high": snapshot.high,
                            "low": snapshot.low,
                            "open": snapshot.open,
                            "close": snapshot.close,
                            "spread": snapshot.spread,
                            "mid_price": snapshot.mid_price,
                            "timestamp": snapshot.timestamp,
                        }
                    )

                df = pd.DataFrame(snapshot_data)

                # Save to Parquet
                if filename is None:
                    filename = f"market_snapshots_{datetime.now().strftime('%Y%m%d_%H%M%S')}.parquet"

                save_path = self.config.data_paths.base_path / "market_data" / filename
                save_path.parent.mkdir(parents=True, exist_ok=True)

                df.to_parquet(save_path, index=False)
                self.logger.info(f"Saved {len(df)} snapshots to {save_path}")
                return True

        except Exception as e:
            self.logger.error(f"Failed to save snapshots: {e}")
            return False

    def get_stream_statistics(self) -> dict[str, Any]:
        """Get comprehensive streaming statistics"""

        stats = self.stream_stats.copy()

        # Add derived metrics
        if stats["stream_start_time"]:
            uptime = (datetime.now() - stats["stream_start_time"]).total_seconds()
            stats["uptime_seconds"] = uptime
            stats["uptime_minutes"] = uptime / 60

            if uptime > 0:
                stats["average_ticks_per_second"] = (
                    stats["total_ticks_received"] / uptime
                )

        # Add active stream info
        with self._lock:
            stats["active_symbols"] = list(self.active_streams.keys())
            stats["snapshot_count"] = len(self.snapshots)

        return stats

    def get_status_report(self) -> str:
        """Generate human-readable status report"""

        stats = self.get_stream_statistics()

        report_lines = [
            "📡 Market Data Service Status",
            "=" * 40,
            f"🌐 Active Streams: {stats['active_streams']}",
            f"📊 Snapshots: {stats['snapshot_count']}",
            f"📈 Total Ticks: {stats['total_ticks_received']:,}",
            f"⚡ Current TPS: {stats['ticks_per_second']:.1f}",
            f"📋 Queue Size: {self.market_data_queue.qsize()}",
            f"❌ Errors: {stats['errors']}",
        ]

        if stats.get("uptime_minutes"):
            report_lines.extend(
                [
                    f"⏱️ Uptime: {stats['uptime_minutes']:.1f} minutes",
                    f"📊 Avg TPS: {stats.get('average_ticks_per_second', 0):.1f}",
                ]
            )

        if stats.get("active_symbols"):
            report_lines.extend(
                ["", "📈 Active Symbols:", ", ".join(stats["active_symbols"])]
            )

        return "\n".join(report_lines)

    def shutdown(self):
        """Gracefully shutdown the market data service"""

        self.logger.info("Shutting down market data service...")

        # Stop all streams
        with self._lock:
            active_symbols = list(self.active_streams.keys())

        for symbol in active_symbols:
            try:
                self.stop_market_data_stream(
                    None, symbol
                )  # Connection would be real in production
            except Exception as e:
                self.logger.error(f"Error stopping stream for {symbol}: {e}")

        # Stop processing thread
        self._stop_processing_thread()

        # Save final snapshots
        self.save_snapshots_to_parquet("final_snapshots.parquet")

        self.logger.info("Market data service shutdown complete")


# Convenient functions for common use cases


def start_single_stream(symbol: str, connection=None) -> MarketDataService:
    """Start market data stream for single symbol"""

    service = MarketDataService()

    config = StreamConfig(symbol=symbol)

    success = service.start_market_data_stream(connection, config)

    if success:
        print(f"✅ Started market data stream for {symbol}")
    else:
        print(f"❌ Failed to start market data stream for {symbol}")

    return service


def start_multiple_streams(symbols: list[str], connection=None) -> MarketDataService:
    """Start market data streams for multiple symbols"""

    service = MarketDataService()

    for symbol in symbols:
        config = StreamConfig(symbol=symbol)

        success = service.start_market_data_stream(connection, config)

        if success:
            print(f"✅ Started stream for {symbol}")
        else:
            print(f"❌ Failed to start stream for {symbol}")

        time.sleep(0.1)  # Brief delay between requests

    return service


def main():
    """Demo the market data service"""

    print("📡 Market Data Service Demo")
    print("=" * 50)

    # Create service
    service = MarketDataService()

    # Add some event handlers
    def tick_printer(tick: MarketDataTick):
        print(f"🔹 {tick.symbol}: {tick.tick_type.name} = {tick.value}")

    def snapshot_printer(snapshot: MarketDataSnapshot):
        if snapshot.bid_price and snapshot.ask_price:
            print(
                f"📊 {snapshot.symbol}: Bid={snapshot.bid_price:.2f} Ask={snapshot.ask_price:.2f} Spread={snapshot.spread:.4f}"
            )

    # service.add_tick_handler(tick_printer)  # Uncomment for verbose output
    service.add_snapshot_handler(snapshot_printer)

    # Start some streams
    print("📥 Starting market data streams...")

    symbols = ["AAPL", "MSFT", "GOOGL"]

    for symbol in symbols:
        config = StreamConfig(symbol=symbol)
        success = service.start_market_data_stream(
            None, config
        )  # Connection would be real

        if success:
            print(f"✅ Started stream for {symbol}")
        else:
            print(f"❌ Failed to start stream for {symbol}")

    # Let it run for a few seconds
    print("\n🕐 Running streams for 10 seconds...")
    time.sleep(10)

    # Show some snapshots
    print("\n📊 Current Market Snapshots:")
    for symbol in symbols:
        snapshot = service.get_market_data_snapshot(symbol)
        if snapshot and snapshot.bid_price:
            print(
                f"  {symbol}: ${snapshot.bid_price:.2f} x ${snapshot.ask_price:.2f} (${snapshot.spread:.4f})"
            )

    # Show statistics
    print(f"\n{service.get_status_report()}")

    # Save snapshots
    print("\n💾 Saving snapshots...")
    save_success = service.save_snapshots_to_parquet()
    if save_success:
        print("✅ Snapshots saved to Parquet")

    # Shutdown
    print("\n🛑 Shutting down...")
    service.shutdown()

    print("\n🎉 Market Data Service demo complete!")


if __name__ == "__main__":
    main()
