#!/usr/bin/env python3
from __future__ import annotations

"""
Tiny IBKR connectivity probe (Linux-first; Windows portproxy fallback).

Behavior:
- Reads IB_HOST/IB_PORT/IB_CLIENT_ID/IB_CONNECT_TIMEOUT from env with
    Linux-first defaults (127.0.0.1:4002). Windows portproxy remains supported
    via env overrides.
- Prints a single JSON object: {connected, host, port, clientId, method, candidates, serverVersion, accounts}
- Exit code 0 on success, non-zero on failure.
"""

import asyncio
import json
import os
import sys
from collections.abc import Iterable
from typing import Any, cast

from src.infra.ib_conn import (
    connect_ib,
    disconnect_ib,
    get_ib_connect_plan,
)


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
                if isinstance(val, int | str):
                    return val
            elif isinstance(sv, int | str):
                return sv
        except Exception:
            pass
    return None


def _accounts(ib: Any) -> list[str]:
    for attr in ("managedAccounts", "accounts"):
        val = getattr(ib, attr, None)
        if isinstance(val, str):
            return [a for a in (x.strip() for x in val.split(",")) if a]
        if isinstance(val, list | tuple):
            it = cast(Iterable[object], val)
            return [str(a) for a in it]
    client = getattr(ib, "client", None)
    if client is not None:
        val = getattr(client, "managedAccounts", None)
        if isinstance(val, str):
            return [a for a in (x.strip() for x in val.split(",")) if a]
    return []


async def main() -> int:
    plan = get_ib_connect_plan()
    host = str(plan["host"])  # sanitized already
    candidates = list(plan["candidates"])  # type: ignore[list-item]
    client_id = int(plan["client_id"])  # type: ignore[arg-type]
    timeout = _env_int("IB_CONNECT_TIMEOUT", int(plan.get("timeout", 20)))
    method = str(plan.get("method", "linux"))

    # Try candidates in order until success
    last_error: Exception | None = None
    for port in candidates:
        try:
            ib = await connect_ib(
                host=host, port=int(port), client_id=client_id, timeout=timeout
            )
            info = {
                "connected": True,
                "host": host,
                "port": int(port),
                "clientId": client_id,
                "method": method,
                "candidates": candidates,
                "serverVersion": _server_version(ib),
                "accounts": _accounts(ib),
            }
            print(json.dumps(info, separators=(",", ":")))
            disconnect_ib(ib)
            return 0
        except Exception as e:
            last_error = e
            continue

    print(
        json.dumps(
            {
                "connected": False,
                "error": str(last_error) if last_error else "connection failed",
                "host": host,
                "port": None,
                "clientId": client_id,
                "method": method,
                "candidates": candidates,
            },
            separators=(",", ":"),
        )
    )
    return 2


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
