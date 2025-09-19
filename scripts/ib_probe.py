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

import argparse
import asyncio
import json
import os
import re
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Any, cast

from src.infra.ib_conn import connect_ib, disconnect_ib, get_ib_connect_plan


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


def _truthy(val: str | None) -> bool:
    return (val or "").strip().lower() in ("1", "true", "yes", "on")


def _with_env_diagnostics(diag: dict[str, Any]) -> dict[str, Any]:
    diag = dict(diag)
    diag["windows_allowed"] = _truthy(os.getenv("IB_ALLOW_WINDOWS"))
    return diag


async def main() -> int:  # noqa: C901 - compact probe with guarded branches
    ap = argparse.ArgumentParser(description="IBKR connectivity probe with diagnostics")
    ap.add_argument(
        "--fix-api-config",
        action="store_true",
        help="Attempt to enable API, disable SSL, set port=7497 in config (idempotent, makes backups)",
    )
    args, _ = ap.parse_known_args()

    plan = get_ib_connect_plan()
    host = str(plan["host"])  # sanitized already
    # Validate candidates; drop invalid ports (e.g., 0)
    raw_candidates = list(plan["candidates"])  # type: ignore[list-item]
    candidates: list[int] = [
        int(p) for p in raw_candidates if isinstance(p, (int, str))
    ]
    candidates = [p for p in candidates if 1 <= int(p) <= 65535]
    client_id = int(plan["client_id"])  # type: ignore[arg-type]
    timeout = _env_int("IB_CONNECT_TIMEOUT", int(plan.get("timeout", 20)))
    method = str(plan.get("method", "linux"))

    def _read_api_settings() -> dict[str, Any]:
        """Best-effort read of API settings from ~/.ibgateway and ~/Jts.

        Returns keys: api_enabled (bool|None), api_port (int|None), ssl (bool|None), trusted_localhost (bool|None)
        """
        result: dict[str, Any] = {
            "api_enabled": None,
            "api_port": None,
            "ssl": None,
            "trusted_localhost": None,
        }
        # Check ~/.ibgateway_automated/Jts/jts.ini if present
        ini_candidates = [
            Path.home() / ".ibgateway_automated" / "Jts" / "jts.ini",
            Path.home() / "Jts" / "jts.ini",
            Path.home() / "Jts" / "ibgateway" / "jts.ini",
        ]
        for ini in ini_candidates:
            try:
                if not ini.exists():
                    continue
                txt = ini.read_text(encoding="utf-8", errors="ignore")
                # Simple INI-ish parsing
                api_only = re.search(r"^ApiOnly\s*=\s*(\w+)", txt, re.M)
                port_m = re.search(r"^LocalServerPort\s*=\s*(\d+)", txt, re.M)
                ssl_m = re.search(r"^UseSSL\s*=\s*(\w+)", txt, re.M)
                trust = re.search(r"^TrustedIPs\s*=\s*(.+)$", txt, re.M)
                if api_only:
                    result["api_enabled"] = api_only.group(1).strip().lower() in (
                        "1",
                        "true",
                        "yes",
                        "on",
                    )
                if port_m:
                    result["api_port"] = int(port_m.group(1))
                if ssl_m:
                    result["ssl"] = ssl_m.group(1).strip().lower() in (
                        "1",
                        "true",
                        "yes",
                        "on",
                    )
                if trust:
                    result["trusted_localhost"] = "127.0.0.1" in trust.group(1)
                break
            except Exception:
                continue

        return result

    def _apply_fix_api_config() -> dict[str, Any]:
        """Idempotently write settings enabling API w/o SSL on port 7497 in jts.ini; backups created."""
        changes: dict[str, Any] = {"touched": False, "path": None, "backup": None}
        ini = Path.home() / ".ibgateway_automated" / "Jts" / "jts.ini"
        if not ini.exists():
            ini = Path.home() / "Jts" / "jts.ini"
        try:
            if not ini.exists():
                return changes
            changes["path"] = str(ini)
            lines = ini.read_text(encoding="utf-8", errors="ignore").splitlines()
            # Create backup
            bak = ini.with_suffix(ini.suffix + ".bak")
            bak.write_text("\n".join(lines), encoding="utf-8")
            changes["backup"] = str(bak)
            # Map of settings to enforce
            enforce = {
                "ApiOnly": "true",
                "LocalServerPort": "7497",
                "UseSSL": "0",
                "TrustedIPs": "127.0.0.1",
            }
            new_lines: list[str] = []
            seen: set[str] = set()
            for line in lines:
                m = re.match(r"^(\w+)\s*=\s*(.*)$", line)
                if not m:
                    new_lines.append(line)
                    continue
                k = m.group(1)
                if k in enforce:
                    new_lines.append(f"{k}={enforce[k]}")
                    seen.add(k)
                else:
                    new_lines.append(line)
            for k, v in enforce.items():
                if k not in seen:
                    new_lines.append(f"{k}={v}")
            if new_lines != lines:
                ini.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
                changes["touched"] = True
            return changes
        except Exception:
            return changes

    # Attach diagnostics about API settings
    api_diag = _with_env_diagnostics(_read_api_settings())
    if args.fix_api_config:
        _ = _apply_fix_api_config()

    # Try candidates in order until success
    last_error: Exception | None = None
    for port in candidates:
        if not (1 <= int(port) <= 65535):
            continue
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
                "windows_allowed": bool(
                    os.getenv("IB_ALLOW_WINDOWS", "").strip().lower()
                    in ("1", "true", "yes", "on")
                ),
                "candidates": candidates,
                "api_enabled": api_diag.get("api_enabled"),
                "api_port": api_diag.get("api_port"),
                "api_ssl": api_diag.get("ssl"),
                "trusted_localhost": api_diag.get("trusted_localhost"),
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
                "api_enabled": api_diag.get("api_enabled"),
                "api_port": api_diag.get("api_port"),
                "api_ssl": api_diag.get("ssl"),
                "trusted_localhost": api_diag.get("trusted_localhost"),
                "hint": (
                    "Gateway API requires SSL; Python ibapi will not handshake. Disable SSL or use supported setup."
                    if api_diag.get("ssl")
                    else None
                ),
            },
            separators=(",", ":"),
        )
    )
    return 2


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
