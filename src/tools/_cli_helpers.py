"""Shared CLI helper utilities for tool scripts.

Lightweight, no heavy imports at module import time to keep `--describe` fast.

New unified helpers:
    * print_json – stable deterministic JSON (sorted keys, flush)
    * emit_describe_early – ultra-early guard to short‑circuit when --describe present
    * redacted – lightweight secrecy helper for minimal masking
"""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any


def print_json(data: dict[str, Any]) -> int:
    """Pretty-print JSON deterministically and return zero.

    Deterministic ordering helps with flaky tests diffing outputs.
    """
    sys.stdout.write(json.dumps(data, indent=2, sort_keys=True) + "\n")
    sys.stdout.flush()
    return 0


def emit_describe_early(describe_fn: Callable[[], dict[str, Any]]) -> bool:
    """If '--describe' present in argv, print JSON from callable and return True.

    This must be invoked before any heavy / optional imports to guarantee
    stability even if optional dependencies are absent or side effects would
    otherwise occur. It is idempotent and safe for repeated imports.
    """
    try:
        if any(arg == "--describe" for arg in sys.argv[1:]):
            try:
                print_json(describe_fn())
            except Exception as e:  # pragma: no cover - defensive
                print_json(
                    {
                        "name": "unknown_tool",
                        "description": "describe failed",
                        "error": str(e),
                        "inputs": {},
                        "outputs": {"stdout": "error while generating describe"},
                        "dependencies": [],
                        "examples": [],
                    }
                )
            return True
    except Exception:  # pragma: no cover - never allow early guard to fail
        print_json(
            {
                "name": "unknown_tool",
                "description": "describe failed (argv inspection)",
                "inputs": {},
                "outputs": {"stdout": "error while generating describe"},
                "dependencies": [],
                "examples": [],
            }
        )
        return True
    return False


def env_dep(key: str, prefix: str = "config") -> str:
    """Return a dependency tag of form prefix:KEY (used in describe metadata)."""
    return f"{prefix}:{key}"


def load_config_safely():  # type: ignore[return-any]
    """Import and return config; fall back to minimal stub if import fails."""
    try:  # noqa: SIM105
        from src.core.config import get_config  # type: ignore

        return get_config()
    except Exception:  # pragma: no cover

        class _IB:
            host = os.getenv("IB_HOST", "172.17.208.1")
            gateway_paper_port = int(os.getenv("IB_GATEWAY_PAPER_PORT", "4002"))
            gateway_live_port = int(os.getenv("IB_GATEWAY_LIVE_PORT", "4001"))
            paper_port = int(os.getenv("IB_PAPER_PORT", "7497"))
            live_port = int(os.getenv("IB_LIVE_PORT", "7496"))
            client_id = int(os.getenv("IB_CLIENT_ID", "2011"))

        class _Cfg:
            ib_connection = _IB()

        return _Cfg()


def redact(key: str, value: Any) -> Any:
    if value is None:
        return None
    if any(token in key.lower() for token in ("pass", "secret", "token")):
        return "***redacted***"
    return value


def redacted(value: str | None) -> str | None:
    """Compact redaction helper used inside some tool metadata.

    Returns a shortened representation retaining only a prefix + suffix.
    """
    if value is None:
        return None
    s = str(value)
    if len(s) > 6:
        return s[:3] + "…" + s[-2:]
    return "***"


def ensure_ib_optional() -> bool:
    """Return True if ib_async (or ibapi) import works; False otherwise."""
    try:  # noqa: SIM105
        __import__("ib_async")
        return True
    except Exception:
        try:
            __import__("ibapi")
            return True
        except Exception:
            return False


@dataclass
class DescribeSchema:
    required_top_keys: tuple[str, ...] = (
        "name",
        "description",
        "inputs",
        "outputs",
        "dependencies",
        "examples",
    )

    def validate(self, data: dict[str, Any]) -> list[str]:
        errs: list[str] = []
        for k in self.required_top_keys:
            if k not in data:
                errs.append(f"missing key: {k}")
        if not isinstance(data.get("inputs"), dict | list):
            errs.append("inputs must be dict or list")
        if not isinstance(data.get("outputs"), dict):
            errs.append("outputs must be dict")
        return errs


def iter_tool_modules(root: str = "src/tools") -> Iterable[str]:
    """Yield importable module paths for tool scripts (heuristic)."""
    import pathlib

    base = pathlib.Path(root)
    for py in base.rglob("*.py"):
        if py.name.startswith("_"):
            continue
        rel = py.relative_to(pathlib.Path("src"))
        mod = str(rel).replace("/", ".").removesuffix(".py")
        try:
            text = py.read_text(encoding="utf-8", errors="ignore")
        except Exception:  # pragma: no cover
            continue
        if "def tool_describe" not in text:
            continue  # skip modules lacking describe metadata
        yield f"src.{mod}" if not mod.startswith("src.") else mod
