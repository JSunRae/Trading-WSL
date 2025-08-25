"""Minimal, safe system analysis CLI (unified --describe guard)."""
# ruff: noqa: I001

# --- ultra-early describe guard (keep above heavy imports) ---
from typing import Any

from src.tools._cli_helpers import (  # type: ignore[attr-defined]
    emit_describe_early,
    env_dep,
    print_json,
)


def tool_describe() -> dict[str, Any]:
    return {
        "name": "system_analysis",
        "description": "Lightweight system + config environment summary (safe, no side effects).",
        "inputs": {},
        "outputs": {"stdout": "System summary JSON or schema"},
        "dependencies": [
            env_dep("IB_HOST"),
            env_dep("IB_PAPER_PORT"),
            env_dep("IB_LIVE_PORT"),
            env_dep("IB_GATEWAY_PAPER_PORT"),
            env_dep("IB_GATEWAY_LIVE_PORT"),
            env_dep("IB_CLIENT_ID"),
        ],
        "examples": [
            {
                "description": "Show describe metadata",
                "command": "python -m src.tools.system_analysis --describe",
            },
            {
                "description": "Run full system analysis",
                "command": "python -m src.tools.system_analysis",
            },
        ],
    }


def describe() -> dict[str, Any]:  # backward compat
    return tool_describe()


if emit_describe_early(tool_describe):  # pragma: no cover
    raise SystemExit(0)
# ----------------------------------------------------------------

import os
import platform
import sys
from pathlib import Path
from typing import Any

# When executed directly (not as package), ensure repository root on sys.path early
if __package__ is None or __package__ == "":  # pragma: no cover - direct script usage
    repo_root = Path(__file__).resolve().parent.parent.parent
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

try:  # Prefer absolute package import
    from src.tools._cli_helpers import ensure_ib_optional  # type: ignore[attr-defined]
    from src.tools._cli_helpers import load_config_safely  # type: ignore[attr-defined,misc]
    from src.tools._cli_helpers import redact  # type: ignore[attr-defined]
except Exception:  # pragma: no cover - define minimal stubs
    import json as _j  # type: ignore

    def print_json(data: dict[str, Any]) -> int:  # type: ignore
        print(_j.dumps(data, indent=2))
        return 0

    def env_dep(key: str, prefix: str = "env") -> str:  # type: ignore
        return f"{prefix}:{key}"

    def ensure_ib_optional() -> bool:  # type: ignore
        return False

    def load_config_safely():  # type: ignore
        class _Cfg:  # minimal stub
            ib_connection = None
            data_paths = None

        return _Cfg()

    def redact(key: str, value: Any) -> Any:  # type: ignore
        return value


TOOL_NAME = "system_analysis"


def _safe_get(obj: object, attr: str, warnings: list[str], default: Any = None) -> Any:
    try:
        return getattr(obj, attr, default)
    except Exception as e:  # pragma: no cover - defensive
        warnings.append(f"attr_error:{attr}:{e}")
        return default


def _collect_paths(data_paths: Any, warnings: list[str]) -> tuple[dict[str, Any], bool]:
    base_path = _safe_get(data_paths, "base_path", warnings)
    backup_path = _safe_get(data_paths, "backup_path", warnings)
    paths_ok = True
    for p in [p for p in (base_path, backup_path) if p is not None]:
        try:
            if not Path(p).exists():
                warnings.append(f"missing_path:{p}")
                paths_ok = False
        except Exception as e:  # pragma: no cover
            warnings.append(f"path_check_error:{p}:{e}")
            paths_ok = False
    return {
        "base_path": str(base_path) if base_path else None,
        "backup_path": str(backup_path) if backup_path else None,
    }, paths_ok


def _collect_ib_details(ib_cfg: Any, warnings: list[str]) -> dict[str, Any]:
    if ib_cfg is None:
        return {}
    details: dict[str, Any] = {}
    for field in (
        "host",
        "paper_port",
        "live_port",
        "gateway_paper_port",
        "gateway_live_port",
        "client_id",
    ):
        val = _safe_get(ib_cfg, field, warnings)
        details[field] = redact(field, val)
    return details


def _gather_summary() -> dict[str, Any]:
    """Collect a compact system + config snapshot (safe best-effort)."""
    cfg = load_config_safely()  # type: ignore[assignment]
    warnings: list[str] = []

    # Python / platform basics
    py_version = platform.python_version()
    plat = platform.platform()
    venv_active = bool(os.environ.get("VIRTUAL_ENV"))
    cwd = str(Path.cwd())

    # Config shallow inspection (guard every access)
    ib_cfg = _safe_get(cfg, "ib_connection", warnings)
    data_paths = _safe_get(cfg, "data_paths", warnings)
    path_info, paths_ok = _collect_paths(data_paths, warnings)
    ib_details = _collect_ib_details(ib_cfg, warnings)
    config_checks: dict[str, Any] = {"ib_connection": ib_details or None, **path_info}

    # Determine IB library availability (optional dependency)
    ib_available = ensure_ib_optional()

    # Add project version if available
    version = None
    try:  # noqa: SIM105
        from src import __version__ as v  # type: ignore

        version = v
    except Exception:  # pragma: no cover
        pass

    return {
        "tool": TOOL_NAME,
        "version": version,
        "python_version": py_version,
        "platform": plat,
        "venv_active": venv_active,
        "cwd": cwd,
        "config_checks": config_checks,
        "ib_available": ib_available,
        "paths_ok": paths_ok,
        "warnings": warnings,
    }


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--describe" in argv:
        return print_json(tool_describe())
    data = _gather_summary()
    return print_json(data)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
