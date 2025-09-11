#!/usr/bin/env python3
from __future__ import annotations

"""
Tiny IBKR connectivity probe for WSL→Windows setups (ib_async).

Behavior:
- Reads IB_HOST/IB_PORT/IB_CLIENT_ID/IB_CONNECT_TIMEOUT from env with
  defaults tuned for WSL portproxy (172.17.208.1:4003, client_id=1001).
- Prints a single JSON object: {connected, host, port, clientId, serverVersion, accounts}
- Exit code 0 on success, non-zero on failure.
"""

import asyncio
import json
import os
import sys
from typing import Any

from src.infra.ib_conn import connect_ib, disconnect_ib


def _env_str(key: str, default: str) -> str:
    return os.environ.get(key, default)


def _env_int(key: str, default: int) -> int:
    try:
        return int(os.environ.get(key, str(default)))
    except ValueError:
        return default


def _server_version(ib: Any) -> int | str | None:
    for obj in (ib, getattr(ib, "client", None)):
        if obj is None:
            continue
        sv = getattr(obj, "serverVersion", None)
        try:
            if callable(sv):
                val = sv()
                if isinstance(val, (int, str)):
                    return val
            elif isinstance(sv, (int, str)):
                return sv
        except Exception:
            pass
    return None


def _accounts(ib: Any) -> list[str]:
    for attr in ("managedAccounts", "accounts"):
        val = getattr(ib, attr, None)
        if isinstance(val, str):
            return [a for a in (x.strip() for x in val.split(",")) if a]
        if isinstance(val, (list, tuple)):
            return [str(a) for a in list(val)]
    client = getattr(ib, "client", None)
    if client is not None:
        val = getattr(client, "managedAccounts", None)
        if isinstance(val, str):
            return [a for a in (x.strip() for x in val.split(",")) if a]
    return []


async def main() -> int:
    host = _env_str("IB_HOST", "172.17.208.1")
    port = _env_int("IB_PORT", 4003)
    client_id = _env_int("IB_CLIENT_ID", 1001)
    timeout = _env_int("IB_CONNECT_TIMEOUT", 20)

    try:
        ib = await connect_ib(
            host=host, port=port, client_id=client_id, timeout=timeout
        )
        info = {
            "connected": True,
            "host": host,
            "port": port,
            "clientId": client_id,
            "serverVersion": _server_version(ib),
            "accounts": _accounts(ib),
        }
        print(json.dumps(info, separators=(",", ":")))
        disconnect_ib(ib)
        return 0
    except Exception as e:
        print(
            json.dumps(
                {
                    "connected": False,
                    "error": str(e),
                    "host": host,
                    "port": port,
                    "clientId": client_id,
                },
                separators=(",", ":"),
            )
        )
        return 2


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
