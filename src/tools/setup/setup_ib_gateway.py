#!/usr/bin/env python3
"""IB Gateway Setup & Configuration (config-driven).

Ports and host are resolved from the central configuration manager so there
are no hardcoded numeric literals. Supports --describe metadata output.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

try:  # Optional import; keep describe resilient
    from src.core.config import get_config  # type: ignore[import]
except Exception:  # pragma: no cover

    def get_config():  # type: ignore
        class DummyIBConnection:
            host = os.getenv("IB_HOST", "172.17.208.1")
            gateway_paper_port = int(os.getenv("IB_GATEWAY_PAPER_PORT", "4002"))
            gateway_live_port = int(os.getenv("IB_GATEWAY_LIVE_PORT", "4001"))
            paper_port = int(os.getenv("IB_PAPER_PORT", "7497"))
            live_port = int(os.getenv("IB_LIVE_PORT", "7496"))
            client_id = 1
            timeout = 30

        class Dummy:
            ib_connection = DummyIBConnection()

        return Dummy()


class IBGatewaySetup:
    """Create helper scripts and show guidance for IB Gateway."""

    def __init__(self) -> None:
        cfg = get_config().ib_connection
        self.cfg = cfg
        self.host = cfg.host
        self.gateway_config: dict[str, dict[str, Any]] = {
            "paper": {"port": cfg.gateway_paper_port, "desc": "Gateway Paper"},
            "live": {"port": cfg.gateway_live_port, "desc": "Gateway Live"},
        }
        self.tws_ports = {"paper": cfg.paper_port, "live": cfg.live_port}

    # ------------------ Guide ------------------
    def print_setup_guide(self) -> None:  # pragma: no cover
        paper_p = self.gateway_config["paper"]["port"]
        live_p = self.gateway_config["live"]["port"]
        tws_paper = self.tws_ports["paper"]
        tws_live = self.tws_ports["live"]
        host = self.host
        print("=" * 72)
        print("🚀 IB GATEWAY SETUP GUIDE")
        print("=" * 72)
        print("\nBenefits: stable, low resource, headless, reconnection capable.")
        print("\nGateway Ports (paper/live):", paper_p, "/", live_p)
        print("TWS Ports (paper/live):", tws_paper, "/", tws_live)
        print("Host:", host)
        print(
            "\nAPI Settings -> Enable ActiveX/Socket, allow localhost, disable Read-Only."
        )
        print("Client ID: choose unique integer (default 1).")
        print("\nTesting one-liner:")
        print(
            f'python -c "import asyncio; from src.lib.ib_async_wrapper import IBAsync, Stock; '
            f"async def t(): ib=IBAsync(); ok=await ib.connect('{host}', {paper_p}, 1); "
            "print('Conn:', 'OK' if ok else 'Fail'); "
            "if ok: c=Stock('AAPL'); d=await ib.req_historical_data(c,'1 D','5 min'); "
            "print('Data:', 'Yes' if d is not None else 'No'); await ib.disconnect(); "
            'asyncio.run(t())"'
        )
        print(
            "\nTroubleshooting: ensure gateway running, API enabled, correct port, host trusted."
        )

    # ------------------ Generators ------------------
    def create_gateway_config(self) -> Path:
        cfg = self.cfg
        data = {
            "ib_gateway": {
                "paper_trading": {
                    "host": cfg.host,
                    "port": cfg.gateway_paper_port,
                    "client_id": cfg.client_id,
                    "timeout": cfg.timeout,
                    "enabled": True,
                },
                "live_trading": {
                    "host": cfg.host,
                    "port": cfg.gateway_live_port,
                    "client_id": cfg.client_id + 1,
                    "timeout": cfg.timeout,
                    "enabled": False,
                },
            }
        }
        path = Path("config/ib_gateway_config.json")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2))
        print(f"✅ Wrote {path}")
        return path

    def create_startup_script(self) -> Path:  # pragma: no cover
        cfg = self.cfg
        script = f"""#!/bin/bash
HOST={cfg.host}
PORT={cfg.gateway_paper_port}
CID={cfg.client_id}
echo '🚀 IB Gateway Startup'
check() {{ python - <<'PY'
import socket,sys
HOST='{cfg.host}'; PORT={cfg.gateway_paper_port}
s=socket.socket(); s.settimeout(2); r=s.connect_ex((HOST,PORT)); s.close(); sys.exit(0 if r==0 else 1)
PY
}}
if check; then echo "✅ Running on $HOST:$PORT"; else echo "⏳ Waiting for Gateway"; for i in {{1..60}}; do check && echo "✅ Up" && break; sleep 5; done; fi
python - <<'PY'
import asyncio,sys
HOST='{cfg.host}'; PORT={cfg.gateway_paper_port}; CID={cfg.client_id}
async def main():
    try:
        from src.lib.ib_async_wrapper import IBAsync
        ib=IBAsync(); ok=await ib.connect(HOST,PORT,CID,timeout=10)
        print('Connection:', '✅ OK' if ok else '❌ Failed')
        if ok: await ib.disconnect(); return 0 if ok else 1
    except Exception as e: print('Error:', e)
    return 1
raise SystemExit(asyncio.run(main()))
PY
"""
        path = Path("start_gateway.sh")
        path.write_text(script)
        path.chmod(0o755)
        print(f"✅ Wrote {path}")
        return path

    def create_status_checker(self) -> Path:  # pragma: no cover
        cfg = self.cfg
        code = f"""#!/usr/bin/env python3
import socket, asyncio
HOST='{cfg.host}'
PORTS={{
    {cfg.gateway_paper_port}:'Gateway Paper', {cfg.gateway_live_port}:'Gateway Live',
    {cfg.paper_port}:'TWS Paper', {cfg.live_port}:'TWS Live'
}}
def check(p,n):
    s=socket.socket(); s.settimeout(2); r=s.connect_ex((HOST,p)); s.close();
    print(f" {{n}} ({{p}}):", '✅ Online' if r==0 else '❌ Offline'); return r==0
async def api(p):
    try:
        from src.lib.ib_async_wrapper import IBAsync
        ib=IBAsync(); ok=await ib.connect(HOST,p,{cfg.client_id},timeout=5)
        if ok: await ib.disconnect(); return True
    except Exception: return False
    return False
available=[p for p,n in PORTS.items() if check(p,n)]
if available:
    print('\nAPI tests:')
    for port in available:
        try:
            import asyncio as a
            ok=a.run(api(port))
            print(f"  Port {{port}}:", '✅ Success' if ok else '❌ Fail')
        except Exception as e: print('  Error', e)
"""
        path = Path("check_gateway_status.py")
        path.write_text(code)
        path.chmod(0o755)
        print(f"✅ Wrote {path}")
        return path

    def run_setup(self) -> None:  # pragma: no cover
        print("🛠️  Generating gateway helper files...")
        self.create_gateway_config()
        self.create_startup_script()
        self.create_status_checker()
        print("🎯 Done. Use ./start_gateway.sh then python check_gateway_status.py")


def _describe() -> dict[str, Any]:
    cfg = get_config().ib_connection
    return {
        "name": "setup_ib_gateway",
        "description": "IB Gateway setup helper (config-driven ports/host).",
        "inputs": ["--guide", "--create-files"],
        "outputs": [
            "config/ib_gateway_config.json",
            "start_gateway.sh",
            "check_gateway_status.py",
        ],
        "env_keys": [
            "IB_HOST",
            "IB_GATEWAY_PAPER_PORT",
            "IB_GATEWAY_LIVE_PORT",
            "IB_PAPER_PORT",
            "IB_LIVE_PORT",
            "IB_CLIENT_ID",
        ],
        "defaults": {
            "host": cfg.host,
            "gateway_paper_port": cfg.gateway_paper_port,
            "gateway_live_port": cfg.gateway_live_port,
            "tws_paper_port": cfg.paper_port,
            "tws_live_port": cfg.live_port,
            "client_id": cfg.client_id,
        },
        "examples": [
            "python -m src.tools.setup.setup_ib_gateway --guide",
            "python -m src.tools.setup.setup_ib_gateway --create-files",
            "python -m src.tools.setup.setup_ib_gateway --guide --create-files",
        ],
        "version": "1.0.0",
    }


def run_cli() -> int:  # pragma: no cover
    parser = argparse.ArgumentParser(description="IB Gateway setup utility")
    parser.add_argument("--guide", action="store_true", help="Show setup guide")
    parser.add_argument(
        "--create-files", action="store_true", help="Generate helper scripts"
    )
    parser.add_argument("--describe", action="store_true", help="Describe JSON")
    args = parser.parse_args()
    if args.describe:
        print(json.dumps(_describe(), indent=2))
        return 0
    setup = IBGatewaySetup()
    did = False
    if args.guide:
        setup.print_setup_guide()
        did = True
    if args.create_files:
        setup.run_setup()
        did = True
    if not did:
        setup.print_setup_guide()
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(run_cli())
