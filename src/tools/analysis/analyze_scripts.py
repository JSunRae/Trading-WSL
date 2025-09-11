#!/usr/bin/env python3
"""
@agent.tool script_inventory_analyzer

Script Inventory Analyzer - Python file analysis for organization planning.
"""

import ast
import csv
import json
import logging
import subprocess
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, NoReturn

from src.tools._cli_helpers import env_dep, print_json

# Schema definitions for agent tool pattern / describe support
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "skip_pyright": {
            "type": "boolean",
            "default": False,
            "description": "Skip pyright analysis",
        },
        "verbose": {
            "type": "boolean",
            "default": False,
            "description": "Enable verbose logging",
        },
    },
}

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "success": {
            "type": "boolean",
            "description": "Analysis completed successfully",
        },
        "files_analyzed": {
            "type": "integer",
            "description": "Number of Python files analyzed",
        },
        "reports_generated": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Report files created",
        },
    },
}


def describe() -> dict[str, object]:
    """Return machine readable metadata for --describe flag."""
    return {
        "name": "analyze_scripts",
        "description": "Inventory & classify project Python scripts; produces CSV + JSON summaries.",
        "inputs": {
            "--skip-pyright": {
                "type": "flag",
                "required": False,
                "description": "Skip pyright type analysis",
            },
            "--verbose": {
                "type": "flag",
                "required": False,
                "description": "Enable verbose logging",
            },
            "--describe": {
                "type": "flag",
                "required": False,
                "description": "Print this schema and exit",
            },
        },
        "outputs": {
            "stdout": {
                "type": "json",
                "description": "Summary JSON (tool results or schema)",
            },
            "scripts_inventory.json": {
                "type": "file",
                "description": "Inventory of analyzed scripts with metrics",
            },
            "scripts_groups.json": {
                "type": "file",
                "description": "Proposed grouping / target paths",
            },
            "scripts_move_plan.csv": {
                "type": "file",
                "description": "CSV move/organization plan",
            },
            "import_graph.json": {
                "type": "file",
                "description": "Simplified import graph",
            },
            "duplicates.json": {
                "type": "file",
                "description": "Duplicate file analysis placeholder",
            },
        },
        "dependencies": [env_dep("PROJECT_ROOT")],
        "examples": [
            {
                "description": "Show schema",
                "command": "python -m src.tools.analysis.analyze_scripts --describe",
            },
            {
                "description": "Analyze scripts",
                "command": "python -m src.tools.analysis.analyze_scripts",
            },
        ],
    }


# Setup logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def find_python_files(repo_root: Path) -> list[Path]:
    """Find all Python files in target directories."""
    python_files: list[Path] = []

    # Search in src/, scripts/, and root
    patterns = ["src/**/*.py", "scripts/**/*.py", "*.py"]

    for pattern in patterns:
        files = list(repo_root.glob(pattern))
        python_files.extend(files)

    # Remove duplicates and __pycache__ files
    python_files = [
        f
        for f in set(python_files)
        if "__pycache__" not in str(f) and f.name.endswith(".py")
    ]

    return sorted(python_files)


def _tags_from_path(file_path: Path) -> list[str]:
    """Tags based on path only (priority order, first match wins)."""
    path_str = str(file_path).lower()
    if "test" in path_str:
        return ["test"]
    if "script" in path_str or file_path.parent.name == "scripts":
        return ["tool"]
    if "util" in path_str or "helper" in path_str:
        return ["utils"]
    if "config" in path_str:
        return ["config"]
    if "model" in path_str or "ml" in path_str:
        return ["model"]
    if "data" in path_str:
        return ["data_io"]
    if "service" in path_str:
        return ["service"]
    if "legacy" in path_str or "deprecated" in path_str:
        return ["deprecated"]
    return []


def _tags_from_content(content: str) -> list[str]:
    """Tags inferred from file content."""
    tags: list[str] = []
    if "@agent.tool" in content:
        tags.append("tool")
    if "if __name__ == '__main__'" in content:
        tags.append("cli")
    if "argparse" in content or "click" in content or "typer" in content:
        tags.append("cli")
    return tags


def detect_role_tags(file_path: Path, content: str) -> list[str]:
    """Detect role tags for the file based on heuristics."""
    tags = _tags_from_path(file_path) + _tags_from_content(content)
    # De-duplicate while preserving order
    ordered = list(dict.fromkeys(tags))
    return ordered if ordered else ["unknown"]


def check_entrypoint(content: str) -> bool:
    """Check if file has an executable entry point."""
    return "if __name__ == '__main__'" in content


def detect_cli_framework(content: str) -> str:
    """Detect which CLI framework is used."""
    if "argparse" in content:
        return "argparse"
    elif "click" in content:
        return "click"
    elif "typer" in content:
        return "typer"
    elif "sys.argv" in content:
        return "sys.argv"
    else:
        return "none"


def check_describe_support(file_path: Path, repo_root: Path) -> dict[str, bool]:
    """Check if file supports --describe flag."""
    has_describe = False
    valid_json = False

    try:
        result = subprocess.run(
            [sys.executable, str(file_path), "--describe"],
            capture_output=True,
            text=True,
            timeout=10,
            cwd=repo_root,
        )

        if result.returncode == 0 and result.stdout.strip():
            has_describe = True
            try:
                json.loads(result.stdout.strip())
                valid_json = True
            except json.JSONDecodeError:
                pass

    except Exception:
        pass

    return {"has_describe": has_describe, "valid_json": valid_json}


def analyze_file(file_path: Path, repo_root: Path) -> dict[str, Any] | None:
    """Analyze a single Python file."""
    try:
        with Path(file_path).open(encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        logger.error(f"Could not read {file_path}: {e}")
        return None

    try:
        tree = ast.parse(content)
    except SyntaxError as e:
        logger.warning(f"Syntax error in {file_path}: {e}")
        return None

    # Extract imports
    internal_deps: list[str] = []
    external_deps: list[str] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith(("src", "scripts")):
                    internal_deps.append(alias.name)
                else:
                    external_deps.append(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.module.startswith(("src", "scripts")):
                internal_deps.append(node.module)
            elif node.module:
                external_deps.append(node.module.split(".")[0])

    # Calculate metrics
    loc = len(content.splitlines())
    functions = len([n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)])
    classes = len([n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)])

    file_info = {
        "path": str(file_path.relative_to(repo_root)),
        "absolute_path": str(file_path),
        "role_tags": detect_role_tags(file_path, content),
        "entrypoint": check_entrypoint(content),
        "cli_framework": detect_cli_framework(content),
        "describe_support": check_describe_support(file_path, repo_root),
        "deps_internal": list(set(internal_deps)),
        "deps_external": list(set(external_deps)),
        "metrics": {"loc": loc, "functions": functions, "classes": classes},
    }

    return file_info


def propose_target_path(file_info: dict[str, Any]) -> dict[str, Any]:
    """Propose a target path for a file."""
    current_path = file_info["path"]
    role_tags: list[str] = file_info["role_tags"]
    entrypoint: bool = bool(file_info["entrypoint"])  # explicit

    target_dir = "src/"
    confidence = 0.5
    rationale = "Default placement"

    # Special-case tools: prefer scripts/ when they are executable
    if "tool" in role_tags or "cli" in role_tags:
        if entrypoint:
            target_dir = "scripts/"
            confidence = 0.9
            rationale = "Executable tool/CLI script"
        else:
            target_dir = "src/tools/"
            confidence = 0.7
            rationale = "Tool module"
    else:
        # Ordered tag preference mapping (first match wins)
        tag_to_target = [
            ("test", ("tests/", 0.95, "Test file")),
            ("config", ("src/config/", 0.8, "Configuration module")),
            ("model", ("src/models/", 0.8, "ML/data model")),
            ("data_io", ("src/data/", 0.8, "Data processing")),
            ("utils", ("src/utils/", 0.8, "Utility module")),
            ("service", ("src/services/", 0.8, "Service module")),
            ("deprecated", ("archive/legacy/", 0.9, "Deprecated code")),
        ]
        for tag, (dir_, conf, why) in tag_to_target:
            if tag in role_tags:
                target_dir, confidence, rationale = dir_, conf, why
                break

    target_path = target_dir + Path(current_path).name
    blockers = ["internal_dependencies"] if file_info["deps_internal"] else []

    return {
        "current_path": current_path,
        "target_path": target_path,
        "confidence": confidence,
        "rationale": rationale,
        "blockers": blockers,
    }


def _write_json(path: Path, obj: object) -> None:
    with path.open("w") as f:
        json.dump(obj, f, indent=2)


def _generate_reports(
    repo_root: Path, file_inventory: list[dict[str, Any]]
) -> list[str]:
    reports_dir = repo_root / "reports"
    reports_dir.mkdir(exist_ok=True)

    groups_proposal = [propose_target_path(f) for f in file_inventory]
    _write_json(reports_dir / "scripts_inventory.json", file_inventory)
    _write_json(reports_dir / "scripts_groups.json", groups_proposal)

    # CSV move plan
    with (reports_dir / "scripts_move_plan.csv").open("w", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "current_path",
                "target_path",
                "reason",
                "confidence",
                "blockers",
            ],
        )
        writer.writeheader()
        for proposal in groups_proposal:
            writer.writerow(
                {
                    "current_path": proposal["current_path"],
                    "target_path": proposal["target_path"],
                    "reason": proposal["rationale"],
                    "confidence": proposal["confidence"],
                    "blockers": "; ".join(proposal["blockers"]),
                }
            )

    # Simple import graph + duplicates placeholder
    import_graph = {
        "nodes": [
            {"id": f["path"], "role_tags": f["role_tags"]} for f in file_inventory
        ],
        "edges": [],
        "cycles": [],
    }
    _write_json(reports_dir / "import_graph.json", import_graph)
    _write_json(reports_dir / "duplicates.json", [])

    return [
        "scripts_inventory.json",
        "scripts_groups.json",
        "scripts_move_plan.csv",
        "import_graph.json",
        "duplicates.json",
    ]


def _summarize_inventory(file_inventory: list[dict[str, Any]]) -> dict[str, Any]:
    role_counts: dict[str, int] = defaultdict(int)
    for f in file_inventory:
        for role in f["role_tags"]:
            role_counts[role] += 1
    return {
        "total_files": len(file_inventory),
        "by_role": dict(role_counts),
        "executable_files": sum(1 for f in file_inventory if f["entrypoint"]),
        "files_with_describe": sum(
            1 for f in file_inventory if f["describe_support"]["has_describe"]
        ),
    }


def run_analysis(verbose: bool = False) -> None:
    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    repo_root = Path(__file__).parent
    python_files = find_python_files(repo_root)
    logger.info(f"Found {len(python_files)} Python files to analyze")

    file_inventory: list[dict[str, Any]] = []
    for file_path in python_files:
        file_info = analyze_file(file_path, repo_root)
        if file_info:
            file_inventory.append(file_info)

    logger.info(f"Successfully analyzed {len(file_inventory)} files")
    reports = _generate_reports(repo_root, file_inventory)
    summary = _summarize_inventory(file_inventory)

    result = {
        "success": True,
        "files_analyzed": len(file_inventory),
        "reports_generated": reports,
        "summary": summary,
    }
    print(json.dumps(result, indent=2))


def _parse_args() -> Any:
    import argparse

    parser = argparse.ArgumentParser(
        description="Analyze Python files for organization"
    )
    parser.add_argument(
        "--describe", action="store_true", help="Show tool description and schema"
    )
    parser.add_argument(
        "--skip-pyright", action="store_true", help="Skip pyright analysis"
    )
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")
    return parser.parse_args()


def _print_error_and_exit(e: Exception) -> NoReturn:
    error_result = {
        "success": False,
        "error": str(e),
        "files_analyzed": 0,
        "reports_generated": [],
    }
    print(json.dumps(error_result, indent=2))
    sys.exit(1)


def main() -> None:
    """Main entry point."""
    args = _parse_args()

    if args.describe:
        print_json(describe())
        return None

    try:
        run_analysis(verbose=args.verbose)
    except Exception as e:
        _print_error_and_exit(e)


if __name__ == "__main__":  # pragma: no cover
    if "--describe" in sys.argv[1:]:
        print_json(describe())
        raise SystemExit(0)
    main()
    raise SystemExit(0)
