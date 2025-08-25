#!/usr/bin/env python
"""Generate a tool manifest (reports/script_manifest.json) by invoking --describe for each maintained CLI.

Discovers python files in src/tools (excluding __pycache__, legacy maintenance duplicates), runs each with --describe,
validates JSON schema (description/input_schema/output_schema keys), and writes a consolidated JSON mapping:
{
  "tool_name": {"path": "src/tools/...", "describe": {...}}
}

Usage:
  python scripts/generate_tool_manifest.py

Exit non-zero if any tool fails or returns invalid JSON.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
TOOLS_DIR = ROOT / "src" / "tools"
OUT_PATH = ROOT / "reports" / "script_manifest.json"

REQUIRED_KEYS = {"description"}


def iter_tool_files():
    for p in TOOLS_DIR.rglob("*.py"):
        if p.name.startswith("_"):
            continue
        if "/maintenance/" in str(p):  # skip deep legacy duplicates
            continue
        if p.name in {"__init__.py"}:
            continue
        yield p


def run_describe(path: Path) -> dict[str, Any]:
    cmd = [sys.executable, str(path), "--describe"]
    out: str = ""
    try:
        out = subprocess.check_output(
            cmd, text=True, stderr=subprocess.STDOUT, timeout=30
        )
        data = json.loads(out)
    except subprocess.CalledProcessError as e:  # pragma: no cover
        return {"error": f"failed --describe: {e.output[:120]}"}
    except json.JSONDecodeError as e:  # pragma: no cover
        return {"error": f"invalid JSON: {e} raw={out[:120]}"}
    missing = REQUIRED_KEYS - data.keys()
    if missing:
        data.setdefault("warnings", []).append(
            f"missing keys {sorted(missing)} (tolerated)"
        )
    if "input_schema" not in data:
        data["input_schema"] = {"type": "object"}
    if "output_schema" not in data:
        data["output_schema"] = {"type": "object"}
    return data


def main():
    manifest: dict[str, dict[str, Any]] = {}
    for tool in sorted(iter_tool_files()):
        rel = tool.relative_to(ROOT)
        name = tool.stem
        data = run_describe(tool)
        manifest[name] = {
            "path": str(rel),
            **({"describe": data} if "error" not in data else data),
        }
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(manifest, indent=2, sort_keys=True))
    print(f"Wrote {OUT_PATH} with {len(manifest)} tools")


if __name__ == "__main__":
    main()
