"""
Level 2 Market Depth Data Recorder for Interactive Brokers

This module provides real-time Level 2 (order book) data recording capabilities
using the Interactive Brokers API with nanosecond timestamp precision.

Features:
- Records bid/ask prices and sizes at specified levels (default 10 each side)
- Configurable snapshot intervals (default 100ms)
- Stores data in Parquet format partitioned by symbol and date
- Logs individual market depth update messages for future MBO analysis
- CLI interface for easy operation
- Paper trading mode for testing

Author: Trading Project
Date: 2025-07-28
"""

import json
import logging
import os
import socket
import sys
import threading
import time
from collections import deque
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import click
import pandas as pd

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ibapi.client import EClient
from ibapi.common import TickerId
from ibapi.contract import Contract
from ibapi.wrapper import EWrapper


@dataclass
class DepthSnapshot:
    """Structure for Level 2 order book snapshot."""

    timestamp: str
    bid_prices: list[float]
    bid_sizes: list[int]
    ask_prices: list[float]
    ask_sizes: list[int]

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)


@dataclass
class DepthMessage:
    """Structure for individual market depth update message."""

    timestamp: str
    operation: str  # add/update/remove
    side: str  # bid/ask
    level: int
    price: float
    size: int
    symbol: str


class DepthRecorder(EWrapper, EClient):
    """
    Level 2 market depth recorder using IB API.

    This class handles connection to Interactive Brokers, subscribes to market depth,
    and records snapshots at specified intervals.
    """

    def __init__(
        self,
        symbol: str,
        levels: int = 10,
        interval_ms: int = 100,
        output_dir: str = "./data/level2",
        paper_mode: bool = True,
        host: str = "127.0.0.1",
        port: int = 4002,
        client_id: int = 1,
    ):
        EClient.__init__(self, self)

        self.symbol = symbol
        self.levels = levels
        self.interval_ms = interval_ms
        self.output_dir = Path(output_dir)
        self.paper_mode = paper_mode
        self.host = host
        self.port = port
        self.client_id = client_id

        # Market depth data storage
        self.bid_book: dict[int, dict[str, float]] = {}  # level -> {price, size}
        self.ask_book: dict[int, dict[str, float]] = {}  # level -> {price, size}
        self.book_lock = threading.Lock()

        # Snapshot storage
        self.snapshots: deque = deque(maxlen=100000)  # Limit memory usage
        self.messages: deque = deque(maxlen=50000)  # Individual messages

        # State management
        self.connected = False
        self.subscribed = False
        self.recording = False
        self.contract: Contract | None = None
        self.ticker_id = 1001

        # Setup logging
        self.setup_logging()

        # Create output directories
        self.setup_directories()

        # Snapshot thread
        self.snapshot_thread: threading.Thread | None = None
        self.stop_event = threading.Event()

    def setup_logging(self):
        """Setup logging configuration."""
        log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        logging.basicConfig(
            level=logging.INFO,
            format=log_format,
            handlers=[
                logging.FileHandler(f"logs/depth_recorder_{self.symbol}.log"),
                logging.StreamHandler(),
            ],
        )
        self.logger = logging.getLogger(f"DepthRecorder_{self.symbol}")

    def setup_directories(self):
        """Create necessary directories for data storage."""
        symbol_dir = self.output_dir / self.symbol
        symbol_dir.mkdir(parents=True, exist_ok=True)

        # Create logs directory if it doesn't exist
        Path("logs").mkdir(exist_ok=True)

        self.logger.info(f"Output directory: {symbol_dir}")

    def create_contract(self) -> Contract:
        """Create IB contract for the symbol."""
        contract = Contract()
        contract.symbol = self.symbol
        contract.secType = "STK"
        contract.exchange = "SMART"
        contract.currency = "USD"
        return contract

    def connect_to_ib(self):
        """Connect to Interactive Brokers TWS/Gateway."""
        try:
            self.logger.info(
                f"Connecting to IB at {self.host}:{self.port} (Paper: {self.paper_mode})"
            )
            self.connect(self.host, self.port, self.client_id)

            # Wait for connection
            timeout = 10
            start_time = time.time()
            while not self.connected and (time.time() - start_time) < timeout:
                time.sleep(0.1)

            if self.connected:
                self.logger.info("Successfully connected to IB")
                return True
            else:
                self.logger.error("Failed to connect to IB within timeout")
                return False

        except Exception as e:
            self.logger.error(f"Connection error: {e}")
            return False

    def connectAck(self):
        """Callback when connection is established."""
        self.connected = True
        self.logger.info("Connection acknowledged")

    def connectionClosed(self):
        """Callback when connection is closed."""
        self.connected = False
        self.subscribed = False
        self.logger.warning("Connection closed")

    def error(
        self,
        reqId: TickerId,
        errorCode: int,
        errorString: str,
        advancedOrderRejectJson: str = "",
    ):
        """Handle IB API errors."""
        if errorCode in [2104, 2106, 2158]:  # Market data warnings
            self.logger.warning(f"Market data warning: {errorString}")
        elif errorCode in [200, 162]:  # No security definition or data
            self.logger.error(f"Security/Data error for {self.symbol}: {errorString}")
        else:
            self.logger.error(f"Error {errorCode}: {errorString}")

    def subscribe_market_depth(self):
        """Subscribe to Level 2 market depth data."""
        if not self.connected:
            self.logger.error("Not connected to IB")
            return False

        try:
            self.contract = self.create_contract()

            # Request market depth with native order book (not smart depth)
            self.reqMktDepth(
                reqId=self.ticker_id,
                contract=self.contract,
                numRows=self.levels * 2,  # Total rows (bid + ask)
                isSmartDepth=False,  # Use native order book
                mktDepthOptions=[],
            )

            self.subscribed = True
            self.logger.info(f"Subscribed to market depth for {self.symbol}")
            return True

        except Exception as e:
            self.logger.error(f"Failed to subscribe to market depth: {e}")
            return False

    def updateMktDepth(
        self,
        reqId: TickerId,
        position: int,
        operation: int,
        side: int,
        price: float,
        size: int,
    ):
        """
        Handle market depth updates.

        Args:
            reqId: Request ID
            position: Position in the book (0-based)
            operation: 0=insert, 1=update, 2=delete
            side: 0=ask, 1=bid
            price: Price level
            size: Size at this level
        """
        try:
            timestamp = datetime.now(UTC).isoformat()

            # Map operation codes
            op_map = {0: "add", 1: "update", 2: "remove"}
            side_map = {0: "ask", 1: "bid"}

            operation_str = op_map.get(operation, "unknown")
            side_str = side_map.get(side, "unknown")

            # Log the individual message
            message = DepthMessage(
                timestamp=timestamp,
                operation=operation_str,
                side=side_str,
                level=position,
                price=price,
                size=size,
                symbol=self.symbol,
            )
            self.messages.append(message)

            # Update the order book
            with self.book_lock:
                if side == 1:  # Bid side
                    if operation == 2:  # Remove
                        if position in self.bid_book:
                            del self.bid_book[position]
                    else:  # Add or update
                        self.bid_book[position] = {"price": price, "size": size}
                else:  # Ask side
                    if operation == 2:  # Remove
                        if position in self.ask_book:
                            del self.ask_book[position]
                    else:  # Add or update
                        self.ask_book[position] = {"price": price, "size": size}

            # Debug logging for first few messages
            if len(self.messages) <= 20:
                self.logger.debug(
                    f"Depth update: {side_str} L{position} {operation_str} "
                    f"${price} x {size}"
                )

        except Exception as e:
            self.logger.error(f"Error processing market depth update: {e}")

    def create_snapshot(self) -> DepthSnapshot | None:
        """Create a snapshot of the current order book."""
        try:
            with self.book_lock:
                timestamp = datetime.now(UTC).isoformat()

                # Initialize arrays with zeros
                bid_prices = [0.0] * self.levels
                bid_sizes = [0] * self.levels
                ask_prices = [0.0] * self.levels
                ask_sizes = [0] * self.levels

                # Fill bid data (sorted by level)
                for level in sorted(self.bid_book.keys()):
                    if level < self.levels:
                        bid_prices[level] = self.bid_book[level]["price"]
                        bid_sizes[level] = int(self.bid_book[level]["size"])

                # Fill ask data (sorted by level)
                for level in sorted(self.ask_book.keys()):
                    if level < self.levels:
                        ask_prices[level] = self.ask_book[level]["price"]
                        ask_sizes[level] = int(self.ask_book[level]["size"])

                return DepthSnapshot(
                    timestamp=timestamp,
                    bid_prices=bid_prices,
                    bid_sizes=bid_sizes,
                    ask_prices=ask_prices,
                    ask_sizes=ask_sizes,
                )

        except Exception as e:
            self.logger.error(f"Error creating snapshot: {e}")
            return None

    def snapshot_worker(self):
        """Worker thread for taking periodic snapshots."""
        self.logger.info(f"Starting snapshot worker with {self.interval_ms}ms interval")

        while not self.stop_event.is_set():
            try:
                if self.recording and self.subscribed:
                    snapshot = self.create_snapshot()
                    if snapshot:
                        self.snapshots.append(snapshot)

                        # Log progress every 100 snapshots
                        if len(self.snapshots) % 100 == 0:
                            self.logger.info(
                                f"Recorded {len(self.snapshots)} snapshots"
                            )

                # Wait for the specified interval
                self.stop_event.wait(self.interval_ms / 1000.0)

            except Exception as e:
                self.logger.error(f"Error in snapshot worker: {e}")
                time.sleep(1)  # Prevent tight loop on errors

    def start_recording(self):
        """Start recording market depth snapshots."""
        if not self.subscribed:
            self.logger.error("Not subscribed to market depth")
            return False

        self.recording = True
        self.stop_event.clear()

        # Start snapshot worker thread
        self.snapshot_thread = threading.Thread(target=self.snapshot_worker)
        self.snapshot_thread.daemon = True
        self.snapshot_thread.start()

        self.logger.info("Started recording market depth snapshots")
        return True

    def stop_recording(self):
        """Stop recording and save data."""
        self.logger.info("Stopping recording...")

        self.recording = False
        self.stop_event.set()

        if self.snapshot_thread:
            self.snapshot_thread.join(timeout=5)

        # Save data
        self.save_data()

        self.logger.info("Recording stopped")

    def save_data(self):
        """Save recorded snapshots and messages to files."""
        try:
            if not self.snapshots:
                self.logger.warning("No snapshots to save")
                return

            # Create filename with current date
            date_str = datetime.now().strftime("%Y-%m-%d")
            timestamp_str = datetime.now().strftime("%H%M%S")

            # Save snapshots to Parquet
            snapshots_data = [snapshot.to_dict() for snapshot in self.snapshots]
            df_snapshots = pd.DataFrame(snapshots_data)

            snapshots_file = (
                self.output_dir
                / self.symbol
                / f"{date_str}_snapshots_{timestamp_str}.parquet"
            )
            df_snapshots.to_parquet(snapshots_file, compression="snappy")

            self.logger.info(
                f"Saved {len(snapshots_data)} snapshots to {snapshots_file}"
            )

            # Save messages to JSON for detailed analysis
            if self.messages:
                messages_data = [asdict(msg) for msg in self.messages]
                messages_file = (
                    self.output_dir
                    / self.symbol
                    / f"{date_str}_messages_{timestamp_str}.json"
                )

                with open(messages_file, "w") as f:
                    json.dump(messages_data, f, indent=2)

                self.logger.info(
                    f"Saved {len(messages_data)} messages to {messages_file}"
                )

            # Save summary statistics
            self.save_summary_stats(len(snapshots_data), len(self.messages))

        except Exception as e:
            self.logger.error(f"Error saving data: {e}")

    def save_summary_stats(self, num_snapshots: int, num_messages: int):
        """Save summary statistics of the recording session."""
        try:
            stats = {
                "symbol": self.symbol,
                "recording_date": datetime.now().isoformat(),
                "levels": self.levels,
                "interval_ms": self.interval_ms,
                "num_snapshots": num_snapshots,
                "num_messages": num_messages,
                "paper_mode": self.paper_mode,
            }

            stats_file = (
                self.output_dir
                / self.symbol
                / f"session_stats_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            )

            with open(stats_file, "w") as f:
                json.dump(stats, f, indent=2)

            self.logger.info(f"Saved session statistics to {stats_file}")

        except Exception as e:
            self.logger.error(f"Error saving statistics: {e}")

    def run(self, duration_minutes: int | None = None):
        """
        Run the recorder for specified duration.

        Args:
            duration_minutes: How long to record (None = indefinite)
        """
        try:
            # Connect to IB
            if not self.connect_to_ib():
                return False

            # Subscribe to market depth
            if not self.subscribe_market_depth():
                return False

            # Wait for initial data
            self.logger.info("Waiting for initial market depth data...")
            time.sleep(2)

            # Start recording
            if not self.start_recording():
                return False

            # Run for specified duration or until interrupted
            if duration_minutes:
                self.logger.info(f"Recording for {duration_minutes} minutes...")
                time.sleep(duration_minutes * 60)
            else:
                self.logger.info("Recording indefinitely. Press Ctrl+C to stop...")
                try:
                    while self.recording:
                        time.sleep(1)
                except KeyboardInterrupt:
                    self.logger.info("Received interrupt signal")

            # Stop recording and cleanup
            self.stop_recording()
            self.disconnect()

            return True

        except Exception as e:
            self.logger.error(f"Error during recording: {e}")
            return False


def check_available_ports() -> tuple[list, bool, bool]:
    """Check which IB ports are accessible"""
    ports = {
        4002: "IB Gateway Paper Trading",
        4001: "IB Gateway Live Trading",
        7497: "TWS Paper Trading",
        7496: "TWS Live Trading",
    }

    accessible: list[int] = []
    gateway_available = False
    tws_available = False

    for port, name in ports.items():
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            result = sock.connect_ex(("127.0.0.1", port))
            sock.close()

            if result == 0:
                accessible.append(port)
                if port in [4001, 4002]:
                    gateway_available = True
                else:
                    tws_available = True
        except Exception:
            pass

    return accessible, gateway_available, tws_available


def get_preferred_port(paper_mode: bool) -> int:
    """Get user's preferred connection port"""
    print("\n🔌 IB CONNECTION SETUP")
    print("=" * 50)

    # Check what's available
    accessible_ports, gateway_available, tws_available = check_available_ports()

    if accessible_ports:
        print("✅ Available connections:")
        for port in accessible_ports:
            if port == 4002:
                print("   1. IB Gateway Paper Trading (port 4002) ⭐ RECOMMENDED")
            elif port == 4001:
                print("   2. IB Gateway Live Trading (port 4001)")
            elif port == 7497:
                print("   3. TWS Paper Trading (port 7497)")
            elif port == 7496:
                print("   4. TWS Live Trading (port 7496)")
    else:
        print("❌ No IB services detected. Available options:")
        print("   1. IB Gateway Paper Trading (port 4002) ⭐ RECOMMENDED")
        print("   2. IB Gateway Live Trading (port 4001)")
        print("   3. TWS Paper Trading (port 7497)")
        print("   4. TWS Live Trading (port 7496)")

    # Default recommendations
    if paper_mode:
        default_port = 4002 if gateway_available or not accessible_ports else (7497 if tws_available else 4002)
        default_name = "IB Gateway Paper" if default_port == 4002 else "TWS Paper"
    else:
        default_port = 4001 if gateway_available or not accessible_ports else (7496 if tws_available else 4001)
        default_name = "IB Gateway Live" if default_port == 4001 else "TWS Live"

    print(f"\n💡 Recommended for {'paper' if paper_mode else 'live'} trading: {default_name} (port {default_port})")

    # Ask user preference
    while True:
        print("\nConnection options:")
        print("1. IB Gateway Paper Trading (4002) ⭐")
        print("2. IB Gateway Live Trading (4001)")
        print("3. TWS Paper Trading (7497)")
        print("4. TWS Live Trading (7496)")
        print("5. Use recommended default")

        try:
            choice = input("\nChoose connection (1-5) [default: 5]: ").strip()

            if choice == "1" or choice == "":
                return 4002
            elif choice == "2":
                return 4001
            elif choice == "3":
                return 7497
            elif choice == "4":
                return 7496
            elif choice == "5" or choice == "":
                print(f"Using recommended: {default_name} (port {default_port})")
                return default_port
            else:
                print("Please enter 1, 2, 3, 4, or 5")

        except KeyboardInterrupt:
            print(f"\nUsing default: {default_name} (port {default_port})")
            return default_port
        except Exception:
            print("Invalid input. Please try again.")


@click.command()
@click.option("--describe", is_flag=True, help="Show tool description")
@click.option(
    "--symbol", "-s", help="Stock symbol to record (e.g., AAPL)"
)
@click.option(
    "--levels", "-l", default=10, help="Number of price levels per side (default: 10)"
)
@click.option(
    "--interval",
    "-i",
    default=100,
    help="Snapshot interval in milliseconds (default: 100)",
)
@click.option(
    "--output", "-o", default="./data/level2", help="Output directory for data files"
)
@click.option(
    "--duration",
    "-d",
    type=int,
    help="Recording duration in minutes (default: indefinite)",
)
@click.option(
    "--host", default="127.0.0.1", help="IB TWS/Gateway host (default: 127.0.0.1)"
)
@click.option(
    "--port",
    default=None,
    type=int,
    help="IB connection port. If not specified, will auto-detect or ask user preference. " +
         "Gateway: 4002 (paper) / 4001 (live), TWS: 7497 (paper) / 7496 (live)"
)
@click.option("--client-id", default=1, help="IB API client ID (default: 1)")
@click.option(
    "--paper/--live", default=True, help="Use paper trading account (default: True)"
)
def main(describe, symbol, levels, interval, output, duration, host, port, client_id, paper):
    """
    Record Level 2 market depth data from Interactive Brokers.

    Example usage:
    python record_depth.py --symbol AAPL --levels 10 --interval 100 --duration 60
    """

    if describe:
        describe_info = {
            "name": "record_depth.py",
            "description": "Record Level 2 market depth data from Interactive Brokers with nanosecond precision",
            "inputs": ["--symbol", "--levels", "--interval", "--output", "--duration", "--host", "--port", "--client-id", "--paper/--live"],
            "outputs": ["parquet files in partitioned structure", "JSON message logs"],
            "dependencies": ["click", "pandas", "ibapi"]
        }
        print(json.dumps(describe_info, indent=2))
        return

    if not symbol:
        print("Error: --symbol is required when not using --describe")
        return

    # Auto-detect or ask for port if not specified
    if port is None:
        port = get_preferred_port(paper)

    print("=" * 60)
    print("📊 LEVEL 2 MARKET DEPTH RECORDER")
    print("=" * 60)
    print(f"Symbol: {symbol}")
    print(f"Levels: {levels} per side")
    print(f"Interval: {interval}ms")
    print(f"Output: {output}")
    print(f"Mode: {'Paper Trading' if paper else 'Live Trading'}")
    print(f"Connection: {host}:{port}")

    # Show connection type
    if port == 4002:
        print("🔗 Connection: IB Gateway Paper Trading ⭐ RECOMMENDED")
    elif port == 4001:
        print("🔗 Connection: IB Gateway Live Trading")
    elif port == 7497:
        print("🔗 Connection: TWS Paper Trading")
    elif port == 7496:
        print("🔗 Connection: TWS Live Trading")
    else:
        print(f"🔗 Connection: Custom (port {port})")

    print("=" * 60)

    # Create recorder
    recorder = DepthRecorder(
        symbol=symbol.upper(),
        levels=levels,
        interval_ms=interval,
        output_dir=output,
        paper_mode=paper,
        host=host,
        port=port,
        client_id=client_id,
    )

    # Run recording
    success = recorder.run(duration_minutes=duration)

    if success:
        print("\n✅ Recording completed successfully!")
        print(f"💾 Data saved to: {output}/{symbol.upper()}/")
    else:
        print("\n❌ Recording failed!")
        print("💡 Troubleshooting tips:")
        if port in [4001, 4002]:
            print("   • Make sure IB Gateway is running and logged in")
            print("   • Check API settings in Gateway (Configuration → API)")
            print("   • Ensure API is enabled and port is correct")
        else:
            print("   • Make sure TWS is running and logged in")
            print("   • Go to Configuration → API → Settings")
            print("   • Enable 'Enable ActiveX and Socket Clients'")
            print(f"   • Set Socket Port to {port}")
            print("   • Add 127.0.0.1 to trusted IPs")
        sys.exit(1)


if __name__ == "__main__":
    main()
