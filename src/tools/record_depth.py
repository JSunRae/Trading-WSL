# ruff: noqa: E402
"""Level 2 Market Depth Recorder (Interactive Brokers)

Clean implementation after refactor issues. Provides:
- Real-time market depth subscription
- Periodic order book snapshots
- Raw depth message capture
- Parquet/JSON persistence
- Standard --describe metadata (ports & config driven)

Design goals:
- Keep dependencies light for --describe (defer heavy imports where possible)
- Avoid complex control flow (small focused helpers)
- Support running without IB services (graceful failures)
"""

from __future__ import annotations

import json
import logging
import os
import socket as _sock
import threading
import time
from collections import deque
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import click

try:  # Allow --describe to function without full config dependency
    from src.core.config import get_config  # type: ignore
except Exception:  # pragma: no cover

    def get_config():  # type: ignore
        class C:
            host = os.getenv("IB_HOST", "172.17.208.1")
            gateway_paper_port = int(os.getenv("IB_GATEWAY_PAPER_PORT", "4002"))
            gateway_live_port = int(os.getenv("IB_GATEWAY_LIVE_PORT", "4001"))
            paper_port = int(os.getenv("IB_PAPER_PORT", "7497"))
            live_port = int(os.getenv("IB_LIVE_PORT", "7496"))
            client_id = 1

        class D:
            ib_connection = C()

        return D()


# IB API imports (alphabetical)
from ibapi.client import EClient  # type: ignore
from ibapi.common import TickerId  # type: ignore
from ibapi.contract import Contract  # type: ignore
from ibapi.wrapper import EWrapper  # type: ignore

from src.infra.ib_conn import get_ib_connect_plan


# ---------------------------------------------------------------------------
# Data Structures
# ---------------------------------------------------------------------------
@dataclass
class DepthSnapshot:
    timestamp: str
    bid_prices: list[float]
    bid_sizes: list[int]
    ask_prices: list[float]
    ask_sizes: list[int]


@dataclass
class DepthMessage:
    timestamp: str
    operation: str
    side: str
    level: int
    price: float
    size: int
    symbol: str


# ---------------------------------------------------------------------------
# Recorder Implementation
# ---------------------------------------------------------------------------
class DepthRecorder(EWrapper, EClient):
    def __init__(
        self,
        symbol: str,
        levels: int = 10,
        interval_ms: int = 100,
        output_dir: str = "./data/level2",
        paper_mode: bool = True,
        host: str | None = None,
        port: int | None = None,
        client_id: int = 1,
    ) -> None:
        EClient.__init__(self, self)
        cfg = get_config().ib_connection
        self.symbol = symbol.upper()
        self.levels = levels
        self.interval_ms = interval_ms
        self.output_dir = Path(output_dir)
        self.paper_mode = paper_mode
        # Prefer env-first plan (WSL portproxy aware) unless explicit host/port provided
        plan = get_ib_connect_plan()
        self.host = host or str(plan.get("host", cfg.host))
        # Choose first candidate by default; allow override via port arg
        plan_ports = [int(p) for p in plan.get("candidates", [])]
        default_port = (
            plan_ports[0]
            if plan_ports
            else (cfg.gateway_paper_port if paper_mode else cfg.gateway_live_port)
        )
        self.port = int(port) if port is not None else int(default_port)
        self.client_id = client_id

        # Order book state
        self.bid_book: dict[int, dict[str, float]] = {}
        self.ask_book: dict[int, dict[str, float]] = {}
        self.book_lock = threading.Lock()

        # Buffers
        self.snapshots: deque[DepthSnapshot] = deque(maxlen=100_000)
        self.messages: deque[DepthMessage] = deque(maxlen=50_000)

        # Session state
        self.connected = False
        self.subscribed = False
        self.recording = False
        self.contract: Contract | None = None
        self.ticker_id = 1001

        # Infra
        self._setup_logging()
        self._ensure_dirs()
        self.snapshot_thread: threading.Thread | None = None
        self.stop_event = threading.Event()
        self.api_thread: threading.Thread | None = None
        # Handshake readiness flag
        self._api_ready: bool = False

    # ----- Setup --------------------------------------------------
    def _setup_logging(self) -> None:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(levelname)s %(message)s",
        )
        self.logger = logging.getLogger(f"DepthRecorder.{self.symbol}")

    def _ensure_dirs(self) -> None:
        (self.output_dir / self.symbol).mkdir(parents=True, exist_ok=True)

    # Handshake readiness events
    def nextValidId(self, orderId: int):  # noqa: N802
        self._api_ready = True
        try:
            self.logger.info("[API_READY] nextValidId=%s", orderId)
        except Exception:
            pass

    def managedAccounts(self, accountsList: str):  # noqa: N802
        self._api_ready = True
        try:
            accounts = [a.strip() for a in accountsList.split(",") if a.strip()]
            self.logger.info("[API_READY] managedAccounts=%s", accounts)
        except Exception:
            pass

    # ----- Connection ---------------------------------------------
    def connect_to_ib(self) -> bool:  # noqa: C901 - Intentional detailed handshake gating
        try:
            plan = get_ib_connect_plan()
            host = self.host or str(plan.get("host", self.host))
            candidates = [int(self.port)]
            # Append plan candidates ensuring uniqueness
            for p in [int(p) for p in plan.get("candidates", [])]:
                if p not in candidates:
                    candidates.append(p)
            self.logger.info(
                "Connecting depth recorder host=%s candidates=%s clientId=%s paper=%s",
                host,
                candidates,
                self.client_id,
                self.paper_mode,
            )
            account_hint = os.getenv("IB_ACCOUNT") or os.getenv("ACCOUNT")
            # Try each candidate until connected
            for port in candidates:
                try:
                    # Attempt connect
                    self._api_ready = False
                    self.connect(host, port, self.client_id)
                    if not self.api_thread or not self.api_thread.is_alive():
                        self.api_thread = threading.Thread(
                            target=super().run, daemon=True
                        )
                        self.api_thread.start()
                    # Wait for socket open (connectAck)
                    start = time.time()
                    while not self.connected and time.time() - start < 10:
                        time.sleep(0.05)
                    if not self.connected:
                        self.logger.warning(
                            "Timeout waiting for [SOCKET_OPEN] %s:%s; trying next",
                            host,
                            port,
                        )
                        continue
                    # Handshake gating: wait for nextValidId or managedAccounts
                    ready = False
                    t0 = time.time()
                    while time.time() - t0 < 20.0:
                        if self._api_ready:
                            ready = True
                            break
                        time.sleep(0.05)
                    if ready or account_hint:
                        if not ready and account_hint:
                            self.logger.info(
                                "[API_READY] assumed via account_hint=%s after timeout",
                                account_hint,
                            )
                        else:
                            self.logger.info("[API_READY] %s:%s", host, port)
                        self.port = port
                        return True
                    # Warmup retry on same port with clientId+1
                    self.logger.warning(
                        "Handshake not ready within timeout; retrying once on same port with clientId+1"
                    )
                    try:
                        self.disconnect()
                    except Exception:
                        pass
                    self.client_id = int(self.client_id) + 1
                    self._api_ready = False
                    self.connect(host, port, self.client_id)
                    if not self.api_thread or not self.api_thread.is_alive():
                        self.api_thread = threading.Thread(
                            target=super().run, daemon=True
                        )
                        self.api_thread.start()
                    t1 = time.time()
                    while not self.connected and time.time() - t1 < 10:
                        time.sleep(0.05)
                    if not self.connected:
                        self.logger.warning(
                            "Handshake retry failed on %s:%s; trying next candidate",
                            host,
                            port,
                        )
                        continue
                    # Wait shortly for API_READY on retry
                    ready2 = False
                    t2 = time.time()
                    while time.time() - t2 < 10.0:
                        if self._api_ready:
                            ready2 = True
                            break
                        time.sleep(0.05)
                    if ready2 or account_hint:
                        if not ready2 and account_hint:
                            self.logger.info(
                                "[API_READY] assumed via account_hint=%s after retry timeout",
                                account_hint,
                            )
                        else:
                            self.logger.info("[API_READY] %s:%s (retry)", host, port)
                        self.port = port
                        return True
                    self.logger.warning(
                        "Handshake retry did not reach API_READY on %s:%s; trying next",
                        host,
                        port,
                    )
                except Exception as e:
                    self.logger.warning(
                        "Connect error on %s:%s (clientId=%s) -> %s",
                        host,
                        port,
                        self.client_id,
                        e,
                    )
            self.logger.error(
                "Unable to connect to any candidate ports: %s", candidates
            )
            return False
        except Exception as e:  # pragma: no cover
            self.logger.error(f"Connect error: {e}")
            return False

    def connectAck(self):  # noqa: N802
        self.connected = True
        self.logger.info(
            "[SOCKET_OPEN] Connection acknowledged (clientId=%s)", self.client_id
        )
        # Required for asynchronous connection path
        try:
            self.startApi()  # type: ignore[attr-defined]
            # Nudge server for nextValidId
            try:
                self.reqIds(-1)  # type: ignore[attr-defined]
            except Exception:
                time.sleep(0.05)
                self.reqIds(-1)  # type: ignore[attr-defined]
        except Exception as e:
            self.logger.error("connectAck handling error: %s", e)

    def connectionClosed(self):  # noqa: N802
        self.connected = False
        self.subscribed = False
        self.logger.warning("Connection closed")

    def error(  # noqa: N802
        self,
        reqId: TickerId,
        errorCode: int,
        errorString: str,
        advancedOrderRejectJson: str = "",
    ) -> None:
        if errorCode in {2104, 2106, 2158}:
            self.logger.warning(f"Market data notice: {errorString}")
        elif errorCode in {200, 162}:
            self.logger.error(f"Security/Data error {errorCode}: {errorString}")
        else:
            self.logger.error(f"Error {errorCode}: {errorString}")

    # ----- Depth Subscription -------------------------------------
    def _contract(self) -> Contract:
        c = Contract()
        c.symbol = self.symbol
        c.secType = "STK"
        c.exchange = "SMART"
        c.currency = "USD"
        return c

    def subscribe_market_depth(self) -> bool:
        try:
            self.contract = self._contract()
            self.reqMktDepth(
                reqId=self.ticker_id,
                contract=self.contract,
                numRows=self.levels * 2,
                isSmartDepth=False,
                mktDepthOptions=[],
            )
            self.subscribed = True
            self.logger.info("Subscribed to market depth")
            return True
        except Exception as e:  # pragma: no cover
            self.logger.error(f"Subscribe error: {e}")
            return False

    def updateMktDepth(  # noqa: N802
        self,
        reqId: TickerId,
        position: int,
        operation: int,
        side: int,
        price: float,
        size: int,
    ) -> None:
        ts = datetime.now(UTC).isoformat()
        op_map = {0: "add", 1: "update", 2: "remove"}
        side_map = {0: "ask", 1: "bid"}
        self.messages.append(
            DepthMessage(
                timestamp=ts,
                operation=op_map.get(operation, "?"),
                side=side_map.get(side, "?"),
                level=position,
                price=price,
                size=size,
                symbol=self.symbol,
            )
        )
        with self.book_lock:
            book = self.bid_book if side == 1 else self.ask_book
            if operation == 2:
                book.pop(position, None)
            else:
                book[position] = {"price": price, "size": size}

    # ----- Snapshot Logic -----------------------------------------
    def _snapshot(self) -> DepthSnapshot | None:
        try:
            with self.book_lock:
                bid_prices = [0.0] * self.levels
                bid_sizes = [0] * self.levels
                ask_prices = [0.0] * self.levels
                ask_sizes = [0] * self.levels
                for lvl in sorted(self.bid_book):
                    if lvl < self.levels:
                        bid_prices[lvl] = self.bid_book[lvl]["price"]
                        bid_sizes[lvl] = int(self.bid_book[lvl]["size"])
                for lvl in sorted(self.ask_book):
                    if lvl < self.levels:
                        ask_prices[lvl] = self.ask_book[lvl]["price"]
                        ask_sizes[lvl] = int(self.ask_book[lvl]["size"])
            return DepthSnapshot(
                timestamp=datetime.now(UTC).isoformat(),
                bid_prices=bid_prices,
                bid_sizes=bid_sizes,
                ask_prices=ask_prices,
                ask_sizes=ask_sizes,
            )
        except Exception as e:  # pragma: no cover
            self.logger.error(f"Snapshot error: {e}")
            return None

    def _snapshot_loop(self) -> None:
        while not self.stop_event.is_set():
            if self.recording and self.subscribed:
                snap = self._snapshot()
                if snap:
                    self.snapshots.append(snap)
            self.stop_event.wait(self.interval_ms / 1000.0)

    def start_recording(self) -> bool:
        if not self.subscribed:
            self.logger.error("Not subscribed")
            return False
        self.recording = True
        self.stop_event.clear()
        self.snapshot_thread = threading.Thread(target=self._snapshot_loop, daemon=True)
        self.snapshot_thread.start()
        return True

    def stop_recording(self) -> None:
        self.recording = False
        self.stop_event.set()
        if self.snapshot_thread:
            self.snapshot_thread.join(timeout=5)
        self._persist()

    # ----- Persistence --------------------------------------------
    def _persist(self) -> None:
        if not self.snapshots:
            self.logger.warning("No snapshots captured")
            return
        date_str = datetime.now().strftime("%Y-%m-%d")
        ts = datetime.now().strftime("%H%M%S")
        dest = self.output_dir / self.symbol
        dest.mkdir(parents=True, exist_ok=True)
        try:
            import pandas as pd  # local import

            snap_file = dest / f"{date_str}_snapshots_{ts}.parquet"
            data_rows = [s.__dict__ for s in self.snapshots]
            pd.DataFrame(data_rows).to_parquet(snap_file, compression="snappy")
            if self.messages:
                msg_file = dest / f"{date_str}_messages_{ts}.json"
                msg_file.write_text(
                    json.dumps([m.__dict__ for m in self.messages], indent=2)
                )
            stats_file = (
                dest / f"session_stats_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            )
            stats_file.write_text(
                json.dumps(
                    {
                        "symbol": self.symbol,
                        "levels": self.levels,
                        "interval_ms": self.interval_ms,
                        "num_snapshots": len(self.snapshots),
                        "num_messages": len(self.messages),
                        "paper_mode": self.paper_mode,
                        "recording_date": datetime.now().isoformat(),
                    },
                    indent=2,
                )
            )
        except Exception as e:  # pragma: no cover
            self.logger.error(f"Persist error: {e}")

    # ----- Orchestration -----------------------------------------
    def run_session(self, duration_minutes: int | None = None) -> bool:
        try:
            if not self.connect_to_ib():
                return False
            if not self.subscribe_market_depth():
                return False
            time.sleep(2)  # warm-up
            if not self.start_recording():
                return False
            if duration_minutes:
                time.sleep(duration_minutes * 60)
            else:
                while self.recording:
                    time.sleep(1)
            self.stop_recording()
            self.disconnect()
            return True
        except KeyboardInterrupt:  # pragma: no cover
            self.stop_recording()
            self.disconnect()
            return True
        except Exception as e:  # pragma: no cover
            self.logger.error(f"Session error: {e}")
            return False


# ---------------------------------------------------------------------------
# Port utilities
# ---------------------------------------------------------------------------


def check_available_ports() -> tuple[list[int], bool, bool]:
    cfg = get_config().ib_connection
    ports = [
        cfg.gateway_paper_port,
        cfg.gateway_live_port,
        cfg.paper_port,
        cfg.live_port,
    ]
    accessible: list[int] = []
    gateway = False
    tws = False
    for p in ports:
        try:
            s = _sock.socket(_sock.AF_INET, _sock.SOCK_STREAM)
            s.settimeout(0.4)
            if s.connect_ex(("127.0.0.1", p)) == 0:
                accessible.append(p)
                if p in (cfg.gateway_paper_port, cfg.gateway_live_port):
                    gateway = True
                else:
                    tws = True
            s.close()
        except Exception:
            pass
    return accessible, gateway, tws


def get_preferred_port(paper_mode: bool) -> int:
    cfg = get_config().ib_connection
    gp, gl, tp, tl = (
        cfg.gateway_paper_port,
        cfg.gateway_live_port,
        cfg.paper_port,
        cfg.live_port,
    )
    accessible, gateway_avail, tws_avail = check_available_ports()
    if paper_mode:
        default_port = (
            gp if gateway_avail or not accessible else (tp if tws_avail else gp)
        )
        default_name = "Gateway Paper" if default_port == gp else "TWS Paper"
    else:
        default_port = (
            gl if gateway_avail or not accessible else (tl if tws_avail else gl)
        )
        default_name = "Gateway Live" if default_port == gl else "TWS Live"
    print("\n🔌 IB CONNECTION SETUP\n" + "=" * 50)
    if accessible:
        print("Detected:")
        for p in accessible:
            label = {
                gp: f"1. Gateway Paper ({gp})",
                gl: f"2. Gateway Live ({gl})",
                tp: f"3. TWS Paper ({tp})",
                tl: f"4. TWS Live ({tl})",
            }.get(p, f"? {p}")
            print("  " + label)
    else:
        print("No running IB services detected")
    print(f"\nRecommended: {default_name} (port {default_port})")
    mapping = {"1": gp, "2": gl, "3": tp, "4": tl, "5": default_port}
    while True:
        try:
            sel = input("Select connection (1-5) [5]: ").strip() or "5"
            if sel in mapping:
                if sel == "5":
                    print(f"Using recommended {default_name} ({default_port})")
                return mapping[sel]
            print("Enter 1-5")
        except KeyboardInterrupt:  # pragma: no cover
            print(f"\nUsing default {default_name} ({default_port})")
            return default_port


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
@click.command()
@click.option("--describe", is_flag=True, help="Show tool description and exit")
@click.option("--symbol", "-s", help="Stock symbol (e.g., AAPL)")
@click.option("--levels", "-l", default=10, show_default=True, help="Levels per side")
@click.option(
    "--interval", "-i", default=100, show_default=True, help="Snapshot interval ms"
)
@click.option(
    "--output",
    "-o",
    default="./data/level2",
    show_default=True,
    help="Output directory",
)
@click.option(
    "--duration", "-d", type=int, help="Duration minutes (omit for indefinite)"
)
@click.option("--host", default=None, help="IB host (default from config)")
@click.option("--port", type=int, default=None, help="IB port (auto-detect / prompt)")
@click.option("--client-id", default=1, show_default=True, help="IB API client id")
@click.option(
    "--paper/--live", default=True, show_default=True, help="Paper vs live mode"
)
def main(
    describe: bool,
    symbol: str | None,
    levels: int,
    interval: int,
    output: str,
    duration: int | None,
    host: str | None,
    port: int | None,
    client_id: int,
    paper: bool,
) -> None:
    if describe:
        cfg = get_config().ib_connection
        desc: dict[str, Any] = {
            "name": "record_depth",
            "description": "Record Level 2 market depth snapshots and raw messages (nanosecond timestamps).",
            "inputs": {
                "--symbol": {"type": "str", "required": True},
                "--levels": {"type": "int", "default": levels},
                "--interval": {"type": "int", "default": interval},
                "--output": {"type": "path", "default": output},
                "--duration": {"type": "int", "default": duration},
                "--host": {"type": "str", "default": host or cfg.host},
                "--port": {"type": "int", "default": None},
                "--client-id": {"type": "int", "default": client_id},
                "--paper/--live": {"type": "flag", "default": paper},
            },
            "outputs": {
                "stdout": "Progress + summary logs",
                "files": [
                    "data/level2/<SYMBOL>/*_snapshots_*.parquet",
                    "data/level2/<SYMBOL>/*_messages_*.json",
                    "data/level2/<SYMBOL>/session_stats_*.json",
                ],
            },
            "dependencies": [
                "config:IB_HOST",
                "config:IB_GATEWAY_PAPER_PORT",
                "config:IB_GATEWAY_LIVE_PORT",
                "config:IB_PAPER_PORT",
                "config:IB_LIVE_PORT",
                "optional:ibapi",
            ],
            "examples": [
                "python -m src.tools.record_depth --symbol AAPL --duration 60",
                "python -m src.tools.record_depth --symbol MSFT --paper --levels 5",
            ],
            "ports": {
                "gateway_paper": cfg.gateway_paper_port,
                "gateway_live": cfg.gateway_live_port,
                "tws_paper": cfg.paper_port,
                "tws_live": cfg.live_port,
            },
            "version": "1.0.0",
        }
        print(json.dumps(desc, indent=2))
        return

    if not symbol:
        print("Error: --symbol is required (or use --describe)")
        return
    cfg = get_config().ib_connection
    host = host or cfg.host
    if port is None:
        port = get_preferred_port(paper)

    print("=" * 60)
    print("📊 LEVEL 2 MARKET DEPTH RECORDER")
    print("=" * 60)
    print(f"Symbol: {symbol.upper()}")
    print(f"Levels: {levels}")
    print(f"Interval: {interval}ms")
    print(f"Output: {output}")
    print(f"Mode: {'Paper' if paper else 'Live'}")
    print(f"Connection: {host}:{port}")
    print("=" * 60)

    rec = DepthRecorder(
        symbol=symbol,
        levels=levels,
        interval_ms=interval,
        output_dir=output,
        paper_mode=paper,
        host=host,
        port=port,
        client_id=client_id,
    )
    ok = rec.run_session(duration_minutes=duration)
    if ok:
        print("\n✅ Recording completed successfully!")
        print(f"💾 Data saved to: {output}/{symbol.upper()}/")
        raise SystemExit(0)
    print("\n❌ Recording failed!")
    print("💡 Troubleshooting:")
    if port in {cfg.gateway_live_port, cfg.gateway_paper_port}:
        print("   • Ensure IB Gateway is running & logged in")
        print("   • Check Configuration → API settings")
        print(
            "   • Confirm port & trusted IP (127.0.0.1) or use WSL proxy 172.17.208.1:4003"
        )
    else:
        print("   • Ensure TWS is running & logged in")
        print("   • Enable 'Enable ActiveX and Socket Clients'")
        print(f"   • Socket Port must be {port}")
    print("   • Add 127.0.0.1 to trusted IPs (or keep proxy on 172.17.208.1:4003)")
    raise SystemExit(1)


if __name__ == "__main__":  # pragma: no cover
    main()
