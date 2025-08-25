"""Legacy script inventory analyzer (placeholder).

This file previously contained logic now replaced by `analyze_scripts`.
We retain a minimal stub with --describe support so global describe schema
tests pass while signalling deprecation to users.
"""

from __future__ import annotations

from src.tools._cli_helpers import env_dep, print_json


def describe() -> dict[str, object]:
    return {
        "name": "script_inventory_analyzer",
        "description": "Deprecated legacy script inventory analyzer (use analyze_scripts instead).",
        "inputs": {
            "--describe": {"type": "flag", "description": "Show schema and exit"}
        },
        "outputs": {
            "stdout": {
                "type": "text",
                "description": "Deprecation notice or schema JSON",
            }
        },
        "dependencies": [env_dep("PROJECT_ROOT")],
        "examples": [
            {
                "description": "Show schema",
                "command": "python -m src.tools.analysis.script_inventory_analyzer --describe",
            }
        ],
    }


def main(argv: list[str] | None = None) -> int:  # pragma: no cover - minimal
    import sys

    args = sys.argv[1:] if argv is None else argv
    if "--describe" in args:
        return print_json(describe())
    print("script_inventory_analyzer is deprecated; use analyze_scripts instead.")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
