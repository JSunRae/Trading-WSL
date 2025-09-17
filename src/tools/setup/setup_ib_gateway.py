#!/usr/bin/env python3
#!/usr/bin/env python3
"""IB Gateway setup & helper script generator (enhanced Option D).

Features:
- Generate config with paper/live ports
- Generate enhanced start script supporting IB_GATEWAY_START_CMD autostart and API smoke test
- Optional status-checker script

Safe generation: shell content uses simple placeholders (__HOST__, __PORT__, __CID__)
replaced post-assembly to avoid f-string or Template collisions.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

try:  # pragma: no cover
    from src.core.config import get_config  # type: ignore
except Exception:  # pragma: no cover
    def get_config():  # type: ignore
        class DummyIBConnection:
            host = os.getenv("IB_HOST", "172.17.208.1")
            gateway_paper_port = int(os.getenv("IB_GATEWAY_PAPER_PORT", "4002"))
            gateway_live_port = int(os.getenv("IB_GATEWAY_LIVE_PORT", "4001"))
            paper_port = int(os.getenv("IB_PAPER_PORT", "7497"))
            live_port = int(os.getenv("IB_LIVE_PORT", "7496"))
            client_id = int(os.getenv("IB_CLIENT_ID", "1"))
            timeout = 30
        class Dummy:
            ib_connection = DummyIBConnection()
        return Dummy()


class IBGatewaySetup:
    def __init__(self) -> None:
        cfg = get_config().ib_connection
        self.cfg = cfg

    # -------------------- Config --------------------
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
        p = Path("config/ib_gateway_config.json")
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(data, indent=2))
        print(f"✅ Wrote {p}")
        return p

    # -------------------- Start Script --------------------
    def create_startup_script(self, *, enhanced: bool = True, force: bool = False) -> Path:
        cfg = self.cfg
        host, port, cid = cfg.host, cfg.gateway_paper_port, cfg.client_id
        path = Path("start_gateway.sh")
        if path.exists() and not force:
            print(f"ℹ️  {path} exists; not overwriting (use --force to replace).")
            return path

        if not enhanced:
            content = (
                "#!/bin/bash\n"
                f"HOST=\"{host}\"\nPORT={port}\nCID={cid}\n"
                "echo 'IB Gateway minimal startup helper'\n"
                "python - <<'PY'\n"
                f"import socket,sys\nHOST='{host}'; PORT={port}\n"
                "s=socket.socket(); s.settimeout(2); r=s.connect_ex((HOST,PORT)); s.close();\n"
                "print('Port status:', 'open' if r==0 else 'closed')\n"
                "sys.exit(0)\nPY\n"
            )
        else:
            template = r"""#!/bin/bash
set -euo pipefail

HOST="__HOST__"
PORT=__PORT__
CID=__CID__

echo '🚀 start_gateway.sh (enhanced Option D)'

check_port() {
  python - <<'PY'
import socket, sys
HOST='__HOST__'; PORT=__PORT__
s=socket.socket(); s.settimeout(1)
try:
    rc=s.connect_ex((HOST, PORT))
finally:
    s.close()
sys.exit(0 if rc==0 else 1)
PY
}

if check_port; then
  echo "✅ Gateway already running on ${HOST}:${PORT}"
else
  if [[ -n "${IB_GATEWAY_START_CMD:-}" ]]; then
    echo "🔄 Port closed; attempting autostart via IB_GATEWAY_START_CMD"
    ( eval "$IB_GATEWAY_START_CMD" >/dev/null 2>&1 & ) || true
    sleep 5
  else
    echo "ℹ️  IB_GATEWAY_START_CMD not set; waiting for manual start..."
  fi
  for i in $(seq 1 60); do
    if check_port; then echo "✅ Gateway detected (after $i attempts)"; break; fi
    sleep 2
  done
fi

python - <<'PY'
import asyncio, sys
HOST='__HOST__'; PORT=__PORT__; CID=__CID__
async def main():
    try:
        from src.lib.ib_async_wrapper import IBAsync
        ib=IBAsync()
        ok=await ib.connect(HOST, PORT, CID, timeout=10)
        print('API connect:', '✅ OK' if ok else '❌ FAIL')
        if ok:
            await ib.disconnect()
        return 0 if ok else 1
    except Exception as e:
        print('Exception during API test:', e)
        return 1
raise SystemExit(asyncio.run(main()))
PY
"""
            content = (
                template
                .replace("__HOST__", str(host))
                .replace("__PORT__", str(port))
                .replace("__CID__", str(cid))
            )

        path.write_text(content)
        path.chmod(0o755)
        print(f"✅ Wrote {path}")
        return path

    # -------------------- Status Checker --------------------
    def create_status_checker(self, *, force: bool = False) -> Path:
        cfg = self.cfg
        path = Path("check_gateway_status.py")
        if path.exists() and not force:
            print(f"ℹ️  {path} exists; not overwriting (use --force to replace).")
            return path
        code = (
            "#!/usr/bin/env python3\n"
            "import socket, asyncio\n"
            f"HOST='{cfg.host}'\n"
            "PORTS = {\n"
            f"    {cfg.gateway_paper_port}: 'Gateway Paper',\n"
            f"    {cfg.gateway_live_port}: 'Gateway Live',\n"
            f"    {cfg.paper_port}: 'TWS Paper',\n"
            f"    {cfg.live_port}: 'TWS Live',\n"
            "}\n\n"
            "def check(port, name):\n"
            "    s = socket.socket(); s.settimeout(2)\n"
            "    try:\n        rc = s.connect_ex((HOST, port))\n    finally:\n        s.close()\n"
            "    up = rc == 0\n"
            "    print(f'{name:<14} ({port}):', '✅ Online' if up else '❌ Offline')\n"
            "    return up\n\n"
            "async def api_test(port: int) -> bool:\n"
            "    try:\n        from src.lib.ib_async_wrapper import IBAsync\n        ib = IBAsync()\n        ok = await ib.connect(HOST, port, "
            f"{cfg.client_id}"
            ", timeout=5)\n        if ok:\n            await ib.disconnect()\n        return ok\n"
            "    except Exception:\n        return False\n\n"
            "active = [p for p,n in PORTS.items() if check(p,n)]\n"
            "if active:\n    print('\\nAPI tests:')\n    for p in active:\n        try:\n            ok = asyncio.run(api_test(p))\n            print('  Port', p, '->', '✅ Success' if ok else '❌ Fail')\n        except Exception as e:\n            print('  Error:', e)\n"
        )
        path.write_text(code)
        path.chmod(0o755)
        print(f"✅ Wrote {path}")
        return path

    # -------------------- Guide --------------------
    def print_setup_guide(self) -> None:  # pragma: no cover
        cfg = self.cfg
        print("=" * 70)
        print("🚀 IB GATEWAY SETUP GUIDE")
        print("=" * 70)
        print("Host:", cfg.host)
        print("Gateway Ports (paper/live):", cfg.gateway_paper_port, "/", cfg.gateway_live_port)
        print("TWS     Ports (paper/live):", cfg.paper_port, "/", cfg.live_port)
        print("\nAutostart: export IB_GATEWAY_START_CMD=\"<launch cmd>\"; then run ./start_gateway.sh")

    def run_setup(self, *, enhanced: bool, force: bool, with_status: bool) -> None:  # pragma: no cover
        self.create_gateway_config()
        self.create_startup_script(enhanced=enhanced, force=force)
        if with_status:
            self.create_status_checker(force=force)


def _describe() -> dict[str, Any]:
    cfg = get_config().ib_connection
    return {
        "name": "setup_ib_gateway",
    "description": "Generate IB Gateway config and helper scripts (enhanced Option D).",
    "inputs": ["--guide", "--create-files", "--enhanced", "--force", "--with-status"],
    "outputs": ["config/ib_gateway_config.json", "start_gateway.sh", "check_gateway_status.py"],
        "env_keys": [
            "IB_HOST",
            "IB_GATEWAY_PAPER_PORT",
            "IB_GATEWAY_LIVE_PORT",
            "IB_PAPER_PORT",
            "IB_LIVE_PORT",
            "IB_CLIENT_ID",
            "IB_GATEWAY_START_CMD",
            "IB_USE_TWS",
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
            "python -m src.tools.setup.setup_ib_gateway --create-files --enhanced",
            "python -m src.tools.setup.setup_ib_gateway --create-files --enhanced --with-status --force",
        ],
        "version": "1.2.0",
    }


def run_cli() -> int:  # pragma: no cover
    ap = argparse.ArgumentParser(description="IB Gateway setup utility")
    ap.add_argument("--guide", action="store_true", help="Show setup guide")
    ap.add_argument("--create-files", action="store_true", help="Generate helper scripts")
    ap.add_argument("--enhanced", action="store_true", help="Generate enhanced start script (Option D)")
    ap.add_argument("--with-status", action="store_true", help="Also generate status checker")
    ap.add_argument("--force", action="store_true", help="Overwrite existing files")
    ap.add_argument("--describe", action="store_true", help="Describe JSON")
    args = ap.parse_args()
    if args.describe:
        print(json.dumps(_describe(), indent=2))
        return 0
    setup = IBGatewaySetup()
    did = False
    if args.guide:
        setup.print_setup_guide()
        did = True
    if args.create_files:
        setup.run_setup(enhanced=args.enhanced, force=args.force, with_status=args.with_status)
        did = True
    if not did:
        setup.print_setup_guide()
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(run_cli())
