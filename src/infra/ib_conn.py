"""
Lightweight IBKR connection helper using ib_async.

Features:
- Env-driven defaults suitable for WSL→Windows portproxy.
- Simple retry policy with exponential backoff.
- Structured logging of connection target + basic server/account info.

Env vars (defaults chosen for WSL→Windows portproxy):
- IB_HOST            default "172.17.208.1"
- IB_PORT            default 4003
- IB_CLIENT_ID       default 1001
- IB_CONNECT_TIMEOUT default 20 (seconds)
- LOG_LEVEL          default INFO

Note on clientId: Do not reuse the same clientId concurrently. Pass different
IDs when running parallel sessions. This module does not coordinate IDs.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from collections.abc import Iterable
from pathlib import Path
from typing import Any, cast


def _load_dotenv_if_present() -> None:
    """Best-effort .env loader (no dependency on python-dotenv).

    Only sets keys that aren't already in process env.
    """
    path = Path(".env")
    try:
        if not path.exists():
            return
        with path.open(encoding="utf-8") as f:
            for raw in f:
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.strip()
                # Strip surrounding quotes if present
                v = v.strip().strip('"').strip("'")
                if k and k not in os.environ:
                    os.environ[k] = v
    except Exception:
        # Silent best-effort
        return


def _env_str(key: str, default: str) -> str:
    return os.environ.get(key, default)


def _env_int(key: str, default: int) -> int:
    try:
        return int(os.environ.get(key, str(default)))
    except ValueError:
        return default


def _configure_logging() -> None:
    level = _env_str("LOG_LEVEL", "INFO").upper()
    lvl = getattr(logging, level, logging.INFO)
    logging.basicConfig(
        level=lvl,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


async def connect_ib(
    host: str | None = None,
    port: int | None = None,
    client_id: int | None = None,
    timeout: int | None = None,
) -> Any:
    """Connect to IB using ib_async with retries.

    Returns the connected IB instance on success, otherwise raises RuntimeError.
    """
    _load_dotenv_if_present()
    _configure_logging()
    log = logging.getLogger("ib_conn")

    # Resolve defaults (favor explicit args over env)
    host = host or _env_str("IB_HOST", "172.17.208.1")
    port = int(port if port is not None else _env_int("IB_PORT", 4003))
    client_id = int(
        client_id if client_id is not None else _env_int("IB_CLIENT_ID", 1001)
    )
    timeout = int(
        timeout if timeout is not None else _env_int("IB_CONNECT_TIMEOUT", 20)
    )

    # Late import to keep dependency light for callers that don't use IB
    try:
        from ib_async import IB  # type: ignore
    except Exception as e:  # pragma: no cover - environment dependent
        raise RuntimeError("ib_async is not installed or unavailable") from e

    # Two retries after the first attempt
    delays = [0.0, 0.5, 1.5]
    last_err: Exception | None = None
    for attempt, delay in enumerate(delays, start=1):
        if delay:
            await asyncio.sleep(delay)
        try:
            ib = IB()
            log.info(
                "Connecting to IBKR host=%s port=%s clientId=%s timeout=%ss (attempt %s/%s)",
                host,
                port,
                client_id,
                timeout,
                attempt,
                len(delays),
            )
            # Some variants don't support timeout kw; call with required args only
            ok = await ib.connectAsync(host, port, clientId=client_id)  # type: ignore[attr-defined]
            if ok:
                # Try to extract diagnostics (best-effort across variants)
                server_version = _get_server_version(ib)
                accounts = _get_managed_accounts(ib)
                log.info(
                    "Connected. serverVersion=%s accounts=%s",
                    server_version if server_version is not None else "?",
                    json.dumps(accounts) if accounts else "[]",
                )
                return ib
            else:
                last_err = RuntimeError("connectAsync returned False")
        except Exception as e:  # pragma: no cover - depends on runtime
            last_err = e
            log.warning("Connect failed on attempt %s: %s", attempt, e)

    # Exhausted attempts
    msg = f"Failed to connect to IB at {host}:{port} (clientId={client_id}) after {len(delays)} attempts"
    raise RuntimeError(msg) from last_err


def disconnect_ib(ib: Any) -> None:
    """Gracefully disconnect (best-effort)."""
    try:
        ib.disconnect()
    except Exception:  # pragma: no cover - best effort
        pass


def _get_server_version(ib: Any) -> int | str | None:
    # Try common locations
    try:
        sv = getattr(ib, "serverVersion", None)
        if callable(sv):
            val = sv()
            if isinstance(val, int | str):
                return val
        if isinstance(sv, int | str):
            return sv
    except Exception:
        pass
    try:
        client = getattr(ib, "client", None)
        if client is not None:
            sv = getattr(client, "serverVersion", None)
            if callable(sv):
                val = sv()
                if isinstance(val, int | str):
                    return val
            if isinstance(sv, int | str):
                return sv
    except Exception:
        pass
    return None


def _get_managed_accounts(ib: Any) -> list[str]:
    # Known shapes across variants: managedAccounts (str comma-delimited) or accounts list
    try:
        accts = getattr(ib, "managedAccounts", None)
        if isinstance(accts, str):
            return [a for a in (x.strip() for x in accts.split(",")) if a]
        if isinstance(accts, list | tuple):
            it = cast(Iterable[object], accts)
            return [str(a) for a in it]
    except Exception:
        pass
    try:
        accts = getattr(ib, "accounts", None)
        if isinstance(accts, list | tuple):
            it2 = cast(Iterable[object], accts)
            return [str(a) for a in it2]
    except Exception:
        pass
    # Fallback: look on client
    try:
        client = getattr(ib, "client", None)
        if client is not None:
            accts = getattr(client, "managedAccounts", None)
            if isinstance(accts, str):
                return [a for a in (x.strip() for x in accts.split(",")) if a]
    except Exception:
        pass
    return []


__all__ = ["connect_ib", "disconnect_ib"]


# ---------------------------------------------------------------------------
# Shared connection plan + candidate helper (reusable across wrappers)
# ---------------------------------------------------------------------------


def get_ib_connect_plan() -> dict[str, Any]:
    """Return a connection plan with env-first defaults and candidate ports.

    Returns a dict with keys: host (str), candidates (list[int]), client_id (int),
    timeout (int). This centralizes the logic used by tools to prefer the WSL
    portproxy first and then fall back to Gateway/TWS paper defaults.

    If the project's config is importable, it will be consulted to enrich the
    candidate list. Otherwise sensible fallbacks are used.
    """
    _load_dotenv_if_present()

    # Host: prefer explicit env, else WSL→Windows adapter default
    host = _env_str("IB_HOST", "172.17.208.1")

    # Client ID and timeout
    client_id = _env_int("IB_CLIENT_ID", 1001)
    timeout = _env_int("IB_CONNECT_TIMEOUT", 20)

    # Seed candidates from env IB_PORT if present
    port_env = os.environ.get("IB_PORT")
    candidates: list[int] = []
    if port_env:
        try:
            candidates.append(int(port_env))
        except ValueError:
            pass

    # Enrich with config-driven defaults when available
    gw_paper = 4002
    tws_paper = 7497
    try:
        from src.core.config import get_config  # type: ignore

        cfg = get_config().ib_connection
        gw_paper = int(getattr(cfg, "gateway_paper_port", gw_paper))
        tws_paper = int(getattr(cfg, "paper_port", tws_paper))
    except Exception:
        # Best-effort; keep fallbacks
        pass

    if not candidates:
        # Prefer portproxy 4003 (WSL→Windows), then Gateway Paper, then TWS Paper
        candidates = [4003, gw_paper, tws_paper]
    else:
        # Ensure unique but stable order with common fallbacks appended
        for p in (4003, gw_paper, tws_paper):
            if p not in candidates:
                candidates.append(p)

    # De-duplicate while preserving order
    seen: set[int] = set()
    deduped: list[int] = []
    for p in candidates:
        if p not in seen:
            deduped.append(p)
            seen.add(p)

    return {
        "host": host,
        "candidates": deduped,
        "client_id": client_id,
        "timeout": timeout,
    }


async def try_connect_candidates(  # noqa: C901 - orchestrator helper with guarded branches
    connect_cb: Any,
    host: str,
    candidates: Iterable[int],
    client_id: int,
    *,
    autostart: bool = False,
    events: list[dict[str, Any]] | None = None,
) -> tuple[bool, int | None]:
    """Try connecting across candidate ports using provided async connect callback.

    Parameters:
      - connect_cb: awaitable callable like `lambda h,p,c: ib.connect(h,p,c)`
      - host: target host
      - candidates: ports to try in order
      - client_id: IB clientId
      - autostart: if True, attempt to run start script/env command once after first pass
      - events: optional list to append diagnostic events

    Returns (ok, port) where port is the successful one or None.
    """
    log = logging.getLogger("ib_conn")
    ev = events if events is not None else []

    plan = {"event": "ib_connect_plan", "host": host, "candidates": list(candidates)}
    try:
        ev.append(plan)  # type: ignore[arg-type]
    except Exception:
        pass

    async def _attempt_all() -> int | None:
        for p in candidates:
            try:
                ok = await connect_cb(host, int(p), client_id)
            except TypeError:
                # Some wrappers use clientId keyword only
                ok = await connect_cb(host, int(p), clientId=client_id)  # type: ignore[call-arg]
            if ok:
                ev.append({"event": "ib_connected", "port": int(p)})  # type: ignore[arg-type]
                return int(p)
            log.info("IB connect failed on %s:%s; trying next candidate", host, p)
        return None

    port = await _attempt_all()
    if port is not None:
        return True, port

    if autostart:
        # Try to start Gateway then re-attempt once
        try:
            script = Path("start_gateway.sh")
            if not script.exists():
                try:
                    from src.tools.setup.setup_ib_gateway import (
                        IBGatewaySetup,  # type: ignore
                    )

                    IBGatewaySetup().create_startup_script()
                except Exception:
                    pass
            if script.exists():
                ev.append({"event": "gateway_autostart_attempt", "script": str(script)})  # type: ignore[arg-type]
                import subprocess
                import time as _t

                subprocess.run(["bash", str(script)], check=False, timeout=60)
                _t.sleep(3)
            else:
                start_cmd = os.environ.get("IB_GATEWAY_START_CMD")
                if start_cmd:
                    ev.append(
                        {"event": "gateway_autostart_env_cmd", "start_cmd": start_cmd}
                    )  # type: ignore[arg-type]
                    try:
                        import subprocess as _sp

                        _sp.Popen(start_cmd, shell=True)
                    except Exception as e:  # pragma: no cover - system dependent
                        ev.append(
                            {
                                "event": "gateway_autostart_env_cmd_error",
                                "error": str(e),
                            }
                        )  # type: ignore[arg-type]
                    import time as _t

                    _t.sleep(5)
        except Exception as e:  # pragma: no cover - best effort
            ev.append({"event": "gateway_autostart_error", "error": str(e)})  # type: ignore[arg-type]

        port = await _attempt_all()
        if port is not None:
            return True, port

    ev.append(
        {"event": "ib_unreachable", "error": f"Failed: {host}:{list(candidates)}"}
    )  # type: ignore[arg-type]
    return False, None


__all__ += ["get_ib_connect_plan", "try_connect_candidates"]


async def connect_ib_planned(
    *, autostart: bool = False, events: list[dict[str, Any]] | None = None
) -> Any:
    """Connect using the centralized connection plan and candidate ports.

    Returns a connected IB instance or raises RuntimeError.
    """
    plan = get_ib_connect_plan()
    try:
        from ib_async import IB  # type: ignore
    except Exception as e:  # pragma: no cover - environment dependent
        raise RuntimeError("ib_async is not installed or unavailable") from e

    ib = IB()

    async def _cb(h: str, p: int, c: int) -> Any:
        return await ib.connect(h, p, c)  # type: ignore[attr-defined]

    ok, _ = await try_connect_candidates(
        _cb,
        plan["host"],
        plan["candidates"],
        int(plan["client_id"]),
        autostart=autostart,
        events=events,
    )
    if not ok:
        raise RuntimeError(
            f"Failed to connect to IB with plan host={plan['host']} candidates={plan['candidates']}"
        )
    return ib


__all__ += ["connect_ib_planned"]
