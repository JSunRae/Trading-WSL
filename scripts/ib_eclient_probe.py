#!/usr/bin/env python3
from __future__ import annotations

"""
Minimal IB API probe using ibapi.EClient/EWrapper.

Behavior:
- Use canonical connection plan from ib_conn.get_ib_connect_plan().
- Try each candidate port from plan sequentially.
- Connect to host/port with clientId from plan.
- Start run() thread; on connectAck, call startApi() and reqIds(-1).
- Print markers:
  - [SOCKET_OPEN] when connectAck received.
  - [API_READY] when nextValidId or managedAccounts arrives.
- Exit 0 if API_READY within timeout, else non-zero.

Environment overrides:
- IB_HOST, IB_PORT, IB_CLIENT_ID, IB_CONNECT_TIMEOUT, IB_HOST_AUTODETECT
CLI overrides:
- --host, --port, --clientId, --timeout
"""

import argparse
import json
import os
import sys
import threading
import time

try:
    from ibapi.client import EClient
    from ibapi.wrapper import EWrapper
except Exception:  # pragma: no cover
    IBAPI_AVAILABLE = False
else:
    IBAPI_AVAILABLE = True

try:
    from src.infra.ib_conn import get_ib_connect_plan
except ImportError as e:
    print(f"Cannot import canonical connection functions: {e}", file=sys.stderr)
    sys.exit(2)


def _env_int(key: str, default: int) -> int:
    try:
        return int(os.environ.get(key, str(default)))
    except Exception:
        return default


def main() -> int:
    ap = argparse.ArgumentParser(description="Minimal IB API EClient probe")
    ap.add_argument("--host", default=os.environ.get("IB_HOST", "127.0.0.1"))
    ap.add_argument("--port", type=int, default=_env_int("IB_PORT", 4002))
    ap.add_argument("--clientId", type=int, default=_env_int("IB_CLIENT_ID", 60001))
    ap.add_argument(
        "--timeout", type=float, default=float(_env_int("IB_CONNECT_TIMEOUT", 30))
    )
    ap.add_argument(
        "--describe",
        action="store_true",
        help="Print JSON description of this tool and exit",
    )
    args, _ = (
        ap.parse_known_args()
    )  # Parse but ignore most - using canonical plan instead

    # Handle --describe before checking ibapi availability
    if args.describe:
        desc = {
            "name": "ib_eclient_probe",
            "description": "Minimal IB API probe using ibapi.EClient/EWrapper. Tests connection to IB Gateway/TWS by attempting to establish a socket connection and complete the API handshake.",
            "inputs": [
                {
                    "name": "IB_HOST",
                    "type": "string",
                    "description": "IB Gateway/TWS host (default: 127.0.0.1, overridden by autodetect if IB_HOST_AUTODETECT=1)",
                    "required": False,
                },
                {
                    "name": "IB_PORT",
                    "type": "integer",
                    "description": "IB Gateway/TWS port (default: 4002)",
                    "required": False,
                },
                {
                    "name": "IB_CLIENT_ID",
                    "type": "integer",
                    "description": "IB API client ID (default: 60001)",
                    "required": False,
                },
                {
                    "name": "IB_CONNECT_TIMEOUT",
                    "type": "integer",
                    "description": "Connection timeout in seconds (default: 25)",
                    "required": False,
                },
                {
                    "name": "IB_HOST_AUTODETECT",
                    "type": "string",
                    "description": "Enable host autodetection (1=yes, 0=no, default: 0)",
                    "required": False,
                },
            ],
            "outputs": [
                {
                    "name": "exit_code",
                    "type": "integer",
                    "description": "0 on success, non-zero on failure",
                },
                {
                    "name": "stdout",
                    "type": "string",
                    "description": "Connection status messages and [SUMMARY] on success",
                },
            ],
            "examples": [
                {
                    "description": "Test connection with default settings",
                    "command": "python scripts/ib_eclient_probe.py",
                },
                {
                    "description": "Test with autodetect enabled",
                    "command": "IB_HOST_AUTODETECT=1 python scripts/ib_eclient_probe.py",
                },
                {
                    "description": "Get tool description",
                    "command": "python scripts/ib_eclient_probe.py --describe",
                },
            ],
        }
        print(json.dumps(desc, indent=2))
        return 0

    # Check ibapi availability after --describe
    if not IBAPI_AVAILABLE:
        print("ibapi not available", file=sys.stderr)
        return 2

    class ProbeApp(EWrapper, EClient):
        def __init__(self, client_id: int) -> None:
            EWrapper.__init__(self)
            EClient.__init__(self, wrapper=self)
            self._socket_open = threading.Event()
            self._api_ready = threading.Event()
            self._client_id = client_id
            self._last_order_id: int | None = None
            self._connect_ack_time: float | None = None
            self._api_ready_time: float | None = None
            self._warmup_used = False

        # Connection lifecycle
        def connectAck(self) -> None:  # noqa: N802 - IB API naming
            self._connect_ack_time = time.perf_counter()
            try:
                print(
                    f"[SOCKET_OPEN] connectAck received (clientId={self._client_id})",
                    flush=True,
                )
            except Exception:
                pass
            try:
                self._socket_open.set()
                # Required for asynchronous connection path
                self.startApi()  # type: ignore[attr-defined]
                # Nudge server for nextValidId
                try:
                    self.reqIds(-1)  # type: ignore[attr-defined]
                except Exception:
                    # Some stacks require startApi to settle first
                    time.sleep(0.05)
                    self.reqIds(-1)  # type: ignore[attr-defined]
            except Exception as e:
                print(f"connectAck handling error: {e}", file=sys.stderr, flush=True)

        def nextValidId(self, orderId: int) -> None:  # noqa: N802,N803 - IB API naming
            self._api_ready_time = time.perf_counter()
            self._last_order_id = orderId
            if not self._api_ready.is_set():
                print(
                    f"[API_READY] nextValidId={orderId} (clientId={self._client_id})",
                    flush=True,
                )
                self._api_ready.set()

        def managedAccounts(self, accountsList: str) -> None:  # noqa: N802,N803
            self._api_ready_time = time.perf_counter()
            if not self._api_ready.is_set():
                print(
                    f"[API_READY] managedAccounts={accountsList} (clientId={self._client_id})",
                    flush=True,
                )
                self._api_ready.set()

        # Error logging (non-fatal for probe)
        def error(
            self, reqId: int, errorCode: int, errorString: str, *args, **kwargs
        ) -> None:  # noqa: N802,N803
            print(
                f"[IB_ERROR] reqId={reqId} code={errorCode} msg={errorString}",
                file=sys.stderr,
                flush=True,
            )

    # Get canonical connection plan
    try:
        plan = get_ib_connect_plan()
    except Exception as e:
        print(f"Failed to get canonical connection plan: {e}", file=sys.stderr)
        return 2

    print(
        f"[PLAN] host={plan['host']} candidates={plan['candidates']} client_id={plan['client_id']} timeout={plan['timeout']} method={plan['method']} host_type={plan['host_type']}",
        flush=True,
    )

    # Try each candidate port
    for port in plan["candidates"]:
        current_client_id = plan["client_id"]
        retry_attempt = 0
        max_retries = 1  # One warmup retry

        while retry_attempt <= max_retries:
            if retry_attempt > 0:
                current_client_id += 1
                print(
                    f"[RETRY] Warming up with clientId={current_client_id} (attempt {retry_attempt + 1})",
                    flush=True,
                )

            print(
                f"[TRYING] {plan['host']}:{port} (clientId={current_client_id})",
                flush=True,
            )

            app = ProbeApp(client_id=current_client_id)
            start_time = time.perf_counter()

            # Start network loop thread
            t = threading.Thread(target=app.run, name="ibapi.run", daemon=True)
            t.start()

            # Initiate connect
            try:
                app.connect(plan["host"], int(port), current_client_id)
            except Exception as e:
                print(
                    f"connect() error for {plan['host']}:{port}: {e}", file=sys.stderr
                )
                break  # Don't retry on connect error

            # Wait for connectAck with increased timeout
            connect_ack_timeout = 15.0 if retry_attempt == 0 else 10.0
            if not app._socket_open.wait(timeout=connect_ack_timeout):
                print(
                    f"[TIMEOUT] No connectAck within {connect_ack_timeout}s for {plan['host']}:{port} (clientId={current_client_id})",
                    file=sys.stderr,
                    flush=True,
                )
                try:
                    app.disconnect()
                except Exception:
                    pass
                break  # Don't retry if no connectAck

            # Wait for API_READY markers
            api_timeout = max(5.0, float(plan["timeout"]) - 10.0)
            if app._api_ready.wait(timeout=api_timeout):
                # Success; print a tiny summary
                time_to_ack = (
                    app._connect_ack_time - start_time if app._connect_ack_time else 0
                )
                time_to_api = (
                    app._api_ready_time - app._connect_ack_time
                    if app._api_ready_time and app._connect_ack_time
                    else 0
                )
                print(
                    f"[SUMMARY] host={plan['host']} port={port} clientId={current_client_id} orderId={app._last_order_id} host_type={plan['host_type']} time_to_ack={time_to_ack:.3f}s time_to_api={time_to_api:.3f}s",
                    flush=True,
                )
                try:
                    app.disconnect()
                except Exception:
                    pass
                return 0

            # API not ready - check if we should retry
            time_to_ack = (
                app._connect_ack_time - start_time if app._connect_ack_time else 0
            )
            current_time = time.perf_counter()
            time_to_api_timeout = current_time - (app._connect_ack_time or start_time)

            print(
                f"[HANG_DIAG] tcp_ok=Y connectAck=Y apiReady=N host={plan['host']} port={port} clientId={current_client_id} time_to_ack={time_to_ack:.3f}s time_to_api={time_to_api_timeout:.3f}s",
                file=sys.stderr,
                flush=True,
            )

            try:
                app.disconnect()
            except Exception:
                pass

            if retry_attempt < max_retries:
                retry_attempt += 1
                time.sleep(0.5)  # Brief pause before retry
                continue
            else:
                print(
                    f"[TIMEOUT] API not ready within timeout for {plan['host']}:{port} (clientId={current_client_id})",
                    file=sys.stderr,
                    flush=True,
                )
                break

    # All candidates failed
    print(
        f"[FAILED] All candidates failed: {plan['host']}:{plan['candidates']}",
        file=sys.stderr,
        flush=True,
    )
    return 4


if __name__ == "__main__":
    sys.exit(main())
