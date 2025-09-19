"""
Lightweight IBKR connection helper using ib_async.

Features:
- Linux-first defaults (local IB Gateway at 127.0.0.1:4002) with Windows portproxy supported via env overrides.
- Simple retry policy with exponential backoff.
- Structured logging of connection target + basic server/account info.

Env vars (Linux-first defaults; Windows portproxy supported via overrides):
- IB_HOST            default "127.0.0.1"
- IB_PORT            default 4002
- IB_CLIENT_ID       default 2011
- IB_CONNECT_TIMEOUT default 20 (seconds)
- IB_HOST_AUTODETECT default 0 (enable to autodetect host)
- LOG_LEVEL          default INFO

Note on clientId: Do not reuse the same clientId concurrently. Pass different
IDs when running parallel sessions. This module does not coordinate IDs.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import socket
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
                k, raw_v = line.split("=", 1)
                k = k.strip()

                def _parse_env_value(s: str) -> str:
                    s = s.lstrip()
                    # If quoted, take content up to the matching quote and ignore the rest
                    if s.startswith('"') or s.startswith("'"):
                        q = s[0]
                        end = s.find(q, 1)
                        if end != -1:
                            return s[1:end]
                        # Fallback: strip outer quote if unmatched
                        return s.strip().strip('"').strip("'")
                    # Unquoted: strip inline comments starting with #
                    hash_pos = s.find("#")
                    if hash_pos != -1:
                        s = s[:hash_pos]
                    return s.strip()

                v = _parse_env_value(raw_v)
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


def _sanitize_host(val: str) -> str:
    """Remove inline comments and whitespace from a host string.

    Examples:
      '172.17.208.1  # comment' -> '172.17.208.1'
      ' localhost ' -> 'localhost'
    """
    try:
        h = val.strip()
        # Drop inline comments
        if "#" in h:
            h = h.split("#", 1)[0].rstrip()
        # Collapse internal whitespace (hosts shouldn't contain spaces)
        return h.split()[0] if h else h
    except Exception:
        return val


def _truthy_env(key: str, default: bool = False) -> bool:
    """Return True if env var is truthy (1/true/yes/on)."""
    val = os.environ.get(key)
    if val is None:
        return default
    return str(val).strip().lower() in {"1", "true", "yes", "on"}


def _detect_wsl_eth0_ip() -> str | None:
    """Detect WSL eth0 IPv4 address, or None if not found."""
    try:
        import subprocess

        result = subprocess.run(
            ["ip", "-4", "a", "show", "eth0"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                if "inet " in line:
                    parts = line.split()
                    if len(parts) >= 2:
                        ip = parts[1].split("/")[0]
                        return ip
    except Exception:
        pass
    return None


def _tcp_probe(host: str, port: int, timeout: float = 1.0) -> bool:
    """Probe if TCP connection to host:port succeeds within timeout."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (TimeoutError, OSError):
        return False


def _autodetect_host(port: int) -> tuple[str, str]:
    """Autodetect available host by probing candidates on given port.

    Returns (host, host_type) where host_type is 'ipv4_loopback', 'ipv6_loopback', 'wsl_eth0', or 'none'.
    """
    candidates = [
        ("127.0.0.1", "ipv4_loopback"),
        ("::1", "ipv6_loopback"),
    ]
    wsl_ip = _detect_wsl_eth0_ip()
    if wsl_ip:
        candidates.append((wsl_ip, "wsl_eth0"))

    for host, host_type in candidates:
        if _tcp_probe(host, port):
            return host, host_type

    # Fallback to ipv4_loopback even if no listener
    return "127.0.0.1", "ipv4_loopback_fallback"


def _parse_jts_config() -> dict[str, Any]:
    """Parse ~/Jts/jts.ini for diagnostic information (non-invasive).

    Returns dict with keys: api_port, ssl_enabled, trusted_ips, found.
    """
    result: dict[str, Any] = {
        "found": False,
        "api_port": None,
        "ssl_enabled": None,
        "trusted_ips": [],
    }

    try:
        jts_path = Path.home() / "Jts" / "jts.ini"
        if not jts_path.exists():
            return result

        result["found"] = True
        content = jts_path.read_text(encoding="utf-8", errors="ignore")

        # Look for API settings
        for line in content.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            if "=" in line:
                key, value = line.split("=", 1)
                key, value = key.strip().lower(), value.strip()

                # API port settings
                if "socketport" in key or "apiport" in key:
                    try:
                        result["api_port"] = int(value)
                    except ValueError:
                        pass

                # SSL settings
                elif "usessl" in key or "ssl" in key:
                    result["ssl_enabled"] = value.lower() in {"true", "1", "yes", "on"}

                # Trusted IPs
                elif "trustedips" in key or "trusted_ips" in key:
                    # Parse comma-separated IP list
                    ips = [ip.strip() for ip in value.split(",") if ip.strip()]
                    result["trusted_ips"] = ips

    except Exception:
        # Silent failure for diagnostic function
        pass

    return result


def _log_jts_diagnostics() -> None:
    """Log JTS configuration diagnostics for troubleshooting."""
    try:
        jts_info = _parse_jts_config()
        log = logging.getLogger("ib_conn")

        if not jts_info["found"]:
            log.debug(
                "~/Jts/jts.ini not found (Gateway may use different config location)"
            )
            return

        log.info("JTS config diagnostics:")

        if jts_info["api_port"]:
            log.info("  API port (jts.ini): %s", jts_info["api_port"])
        else:
            log.info("  API port (jts.ini): not detected")

        if jts_info["ssl_enabled"] is not None:
            log.info("  SSL enabled: %s", jts_info["ssl_enabled"])
        else:
            log.info("  SSL setting: not detected")

        if jts_info["trusted_ips"]:
            localhost_in_trusted = any(
                ip in {"127.0.0.1", "localhost", "0.0.0.0", "*"}
                for ip in jts_info["trusted_ips"]
            )
            log.info("  Trusted IPs: %s", ", ".join(jts_info["trusted_ips"]))
            log.info("  Localhost in trusted IPs: %s", localhost_in_trusted)
        else:
            log.info("  Trusted IPs: not detected")

    except Exception as e:
        logging.getLogger("ib_conn").debug("JTS diagnostics failed: %s", e)


def _is_valid_port(p: int) -> bool:
    return 1 <= int(p) <= 65535


def _filter_valid_ports(ports: Iterable[int]) -> list[int]:
    log = logging.getLogger("ib_conn")
    out: list[int] = []
    for p in ports:
        try:
            ip = int(p)
        except Exception:
            continue
        if _is_valid_port(ip):
            if ip not in out:
                out.append(ip)
        else:
            try:
                log.warning("Ignoring invalid IB port candidate: %s", p)
            except Exception:
                pass
    return out


async def _attempt_connect_once(
    ib_ctor: Any,
    log: logging.Logger,
    host: str,
    port: int,
    base_client_id: int,
    timeout: int,
    attempt_no: int,
) -> tuple[Any | None, Exception | None]:
    """Try a few nearby clientIds to avoid duplicate-client collisions.

    Returns (ib, err). If ib is not None, it's a connected instance.
    """
    last_err: Exception | None = None
    for cid in (base_client_id, base_client_id + 1, base_client_id + 2):
        ib = ib_ctor()
        log.info(
            "Connecting to IBKR host=%s port=%s clientId=%s timeout=%ss (attempt %s/%s)",
            host,
            port,
            cid,
            timeout,
            attempt_no,
            3,
        )
        try:
            ok = await ib.connectAsync(host, port, clientId=cid)  # type: ignore[attr-defined]
        except Exception as e:  # pragma: no cover - vendor dependent
            last_err = e
            log.warning(
                "Connect failed (clientId=%s) on attempt %s: %s", cid, attempt_no, e
            )
            try:
                ib.disconnect()
            except Exception:
                pass
            continue

        if ok:
            server_version = _get_server_version(ib)
            accounts = _get_managed_accounts(ib)
            log.info(
                "Connected. serverVersion=%s accounts=%s",
                server_version if server_version is not None else "?",
                json.dumps(accounts) if accounts else "[]",
            )
            return ib, None

        last_err = RuntimeError("connectAsync returned False")
        try:
            ib.disconnect()
        except Exception:
            pass
        log.warning(
            "connectAsync returned False with clientId=%s; trying next clientId", cid
        )
    return None, last_err


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

    # Resolve defaults (favor explicit args over env) and sanitize host
    host = _sanitize_host(host or _env_str("IB_HOST", "127.0.0.1"))
    port = int(port if port is not None else _env_int("IB_PORT", 4002))
    # Clamp invalid port values to a safe default (4002) and warn
    if not _is_valid_port(port):
        logging.getLogger("ib_conn").warning(
            "Invalid IB_PORT=%s; clamping to 4002 to avoid :0 logs", port
        )
        port = 4002
    client_id = int(
        client_id if client_id is not None else _env_int("IB_CLIENT_ID", 2011)
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
        ib, last_err = await _attempt_connect_once(
            IB, log, host, port, int(client_id), int(timeout), attempt
        )
        if ib is not None:
            return ib

    # Exhausted attempts
    msg = f"Failed to connect to IB at {host}:{port} (clientId~={client_id}) after {len(delays)} attempts"
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


def _dedupe_ints(items: Iterable[int]) -> list[int]:
    """Deduplicate integers preserving order."""
    seen: set[int] = set()
    out: list[int] = []
    for p in items:
        if p not in seen:
            out.append(p)
            seen.add(p)
    return out


def _candidate_base_ports() -> tuple[int, int]:
    """Return (gateway_paper, tws_paper) base ports, consulting config if present."""
    gw, tws = 4002, 7497
    try:  # best-effort enrichment from project config
        from src.core.config import get_config  # type: ignore

        cfg = get_config().ib_connection
        gw = int(getattr(cfg, "gateway_paper_port", gw))
        tws = int(getattr(cfg, "paper_port", tws))
    except Exception:
        pass
    return gw, tws


def _build_candidate_ports() -> list[int]:
    """Build candidate port list env-first, Linux-first order.

    Base order (Linux-first): [IB_PORT?, gateway_paper(4002), tws_paper(7497)]
    Windows/portproxy [4003, 4004] are appended ONLY when IB_ALLOW_WINDOWS=1.
    """
    out: list[int] = []
    env_port = os.environ.get("IB_PORT")
    if env_port:
        try:
            out.append(int(env_port))
        except ValueError:
            pass
    gw_paper, tws_paper = _candidate_base_ports()
    for p in (gw_paper, tws_paper):
        if p not in out:
            out.append(p)
    # Gate Windows/portproxy ports behind explicit opt-in
    if _truthy_env("IB_ALLOW_WINDOWS", False):
        for p in (4003, 4004):
            if p not in out:
                out.append(p)
    # Validate and return
    return _filter_valid_ports(out)


def _detect_connect_method(resolved_host: str, env_host: str, env_port: str) -> str:
    """Detect connection method label for logging/telemetry (Linux-first).

    - If resolved host is localhost/127.0.0.1 -> linux
    - Else if env_host looks like a LAN address and env_port is a typical
      portproxy port (4003/4004) -> windows-portproxy
    - Else -> linux
    """
    try:
        if resolved_host in {"127.0.0.1", "localhost"}:
            return "linux"
        p_int = int(env_port) if env_port else None
    except ValueError:
        p_int = None
    if env_host.startswith("172.") or env_host.startswith("192.168."):
        if p_int in {4003, 4004} and _truthy_env("IB_ALLOW_WINDOWS", False):
            return "windows-portproxy"
    return "linux"


def get_ib_connect_plan() -> dict[str, Any]:
    """Return a connection plan with env-first defaults and candidate ports.

    Returns a dict with keys: host (str), candidates (list[int]), client_id (int),
    timeout (int), method (str), host_type (str). This centralizes the logic used by tools to prefer the WSL
    portproxy first and then fall back to Gateway/TWS paper defaults.

    If IB_HOST_AUTODETECT=1, probes 127.0.0.1, ::1, WSL eth0 IP on port 4002 to find available host.

    If the project's config is importable, it will be consulted to enrich the
    candidate list. Otherwise sensible fallbacks are used.
    """
    _load_dotenv_if_present()

    # Log JTS diagnostics for troubleshooting (non-invasive)
    _log_jts_diagnostics()

    # Host autodetect if enabled
    if _truthy_env("IB_HOST_AUTODETECT", False):
        host, host_type = _autodetect_host(4002)
        log = logging.getLogger("ib_conn")
        log.info("IB host autodetect: selected %s (%s)", host, host_type)
    else:
        host = _sanitize_host(_env_str("IB_HOST", "127.0.0.1"))
        host_type = "explicit"

    # Client ID and timeout
    client_id = _env_int("IB_CLIENT_ID", 2011)
    timeout = _env_int("IB_CONNECT_TIMEOUT", 20)

    candidates = _build_candidate_ports()

    # De-duplicate while preserving order (ports already validated)
    deduped = _dedupe_ints(candidates)

    # WSL-specific host rewriting removed; rely on explicit env overrides
    # Determine method for logging/reporting
    env_host = os.environ.get("IB_HOST", "")
    env_port = os.environ.get("IB_PORT", "")
    method = _detect_connect_method(host, env_host, env_port)

    log = logging.getLogger("ib_conn")
    allow_windows = _truthy_env("IB_ALLOW_WINDOWS", False)
    if method == "linux":
        if allow_windows:
            log.info(
                "IB plan: Linux-first with Windows fallback enabled (IB_ALLOW_WINDOWS=1)"
            )
        else:
            log.info("IB plan: Linux-only (Windows fallback disabled)")
    else:
        # Only possible when allow_windows and env suggests portproxy
        log.info("IB plan: Windows portproxy (explicit opt-in via IB_ALLOW_WINDOWS=1)")

    return {
        "host": host,
        "candidates": deduped,
        "client_id": client_id,
        "timeout": timeout,
        "method": method,
        "host_type": host_type,
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

    async def _probe_tcp(host: str, port: int) -> bool:
        """Check if TCP connection is possible."""
        s: socket.socket | None = None
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(2.0)
            return s.connect_ex((host, port)) == 0
        except Exception:
            return False
        finally:
            if s is not None:
                try:
                    s.close()
                except Exception:
                    pass

    async def _try_handshake_for_port(
        host: str, port: int, base_client_id: int
    ) -> int | None:
        """Try API handshake for a specific port with clientId cycling."""
        # Try a few nearby clientIds to avoid duplicate-client collisions
        for cid_offset in range(3):
            current_cid = base_client_id + cid_offset
            try:
                ok = await connect_cb(host, port, current_cid)
            except TypeError:
                # Some wrappers use clientId keyword only
                ok = await connect_cb(host, port, clientId=current_cid)  # type: ignore[call-arg]
            except Exception as e:
                log.warning(
                    "API handshake error for %s:%s (clientId=%s): %s",
                    host,
                    port,
                    current_cid,
                    e,
                )
                continue

            if ok:
                ev.append(
                    {"event": "ib_connected", "port": port, "client_id": current_cid}
                )  # type: ignore[arg-type]
                log.info(
                    "✅ API handshake successful for %s:%s (clientId=%s)",
                    host,
                    port,
                    current_cid,
                )
                return port

            log.info(
                "API handshake failed for %s:%s (clientId=%s); trying next clientId",
                host,
                port,
                current_cid,
            )

        # All clientIds failed for this port
        log.warning(
            "TCP open but API handshake failed for %s:%s with all clientIds → not API socket or SSL-only. "
            "Check IB Gateway/TWS API settings: enable 'ActiveX and Socket Clients', "
            "verify Trusted IPs, and ensure SSL is disabled for plain connections",
            host,
            port,
        )
        return None

    async def _attempt_all() -> int | None:
        for p in candidates:
            # Validate port to avoid :0 attempts
            if not _is_valid_port(p):
                log.warning("Skipping invalid port candidate: %s", p)
                continue

            # TCP probe first
            if not await _probe_tcp(host, p):
                log.info("TCP probe failed for %s:%s; trying next candidate", host, p)
                continue

            # TCP is open, now attempt API handshake with clientId cycling
            log.info(
                "[SOCKET_OPEN] TCP probe successful for %s:%s; attempting API handshake (clientId~=%s)",
                host,
                p,
                client_id,
            )
            result = await _try_handshake_for_port(host, p, client_id)
            if result is not None:
                log.info("[API_READY] %s:%s", host, p)
                return result

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


__all__ += ["get_ib_connect_plan", "try_connect_candidates", "connect_ib_planned"]

# Test utilities
__all__ += [
    "_build_candidate_ports",
    "_filter_valid_ports",
    "_is_valid_port",
    "_parse_jts_config",
]


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
        # Support both async and sync connect methods
        try:
            res = ib.connect(h, p, c)  # type: ignore[attr-defined]
        except TypeError:
            res = ib.connect(h, p, clientId=c)  # type: ignore[attr-defined]
        if asyncio.iscoroutine(res):
            return await res
        return bool(res)

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
