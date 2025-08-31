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


def find_python_files(repo_root):
    """Find all Python files in target directories."""
    python_files = []

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


def detect_role_tags(file_path, content):
    """Detect role tags for the file based on heuristics."""
    tags = []
    path_str = str(file_path).lower()

    # Path-based detection
    if "test" in path_str:
        tags.append("test")
    elif "script" in path_str or file_path.parent.name == "scripts":
        tags.append("tool")
    elif "util" in path_str or "helper" in path_str:
        tags.append("utils")
    elif "config" in path_str:
        tags.append("config")
    elif "model" in path_str or "ml" in path_str:
        tags.append("model")
    elif "data" in path_str:
        tags.append("data_io")
    elif "service" in path_str:
        tags.append("service")
    elif "legacy" in path_str or "deprecated" in path_str:
        tags.append("deprecated")

    # Content-based detection
    if "@agent.tool" in content:
        tags.append("tool")
    if "if __name__ == '__main__'" in content:
        tags.append("cli")
    if "argparse" in content or "click" in content:
        tags.append("cli")

    return tags if tags else ["unknown"]


def check_entrypoint(content):
    """Check if file has an executable entry point."""
    return "if __name__ == '__main__'" in content


def detect_cli_framework(content):
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


def check_describe_support(file_path, repo_root):
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


def analyze_file(file_path, repo_root):
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
    internal_deps = []
    external_deps = []

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


def propose_target_path(file_info):
    """Propose a target path for a file."""
    current_path = file_info["path"]
    role_tags = file_info["role_tags"]

    if "tool" in role_tags or "cli" in role_tags:
        if file_info["entrypoint"]:
            target_dir = "scripts/"
            confidence = 0.9
            rationale = "Executable tool/CLI script"
        else:
            target_dir = "src/tools/"
            confidence = 0.7
            rationale = "Tool module"
    elif "test" in role_tags:
        target_dir = "tests/"
        confidence = 0.95
        rationale = "Test file"
    elif "config" in role_tags:
        target_dir = "src/config/"
        confidence = 0.8
        rationale = "Configuration module"
    elif "model" in role_tags:
        target_dir = "src/models/"
        confidence = 0.8
        rationale = "ML/data model"
    elif "data_io" in role_tags:
        target_dir = "src/data/"
        confidence = 0.8
        rationale = "Data processing"
    elif "utils" in role_tags:
        target_dir = "src/utils/"
        confidence = 0.8
        rationale = "Utility module"
    elif "service" in role_tags:
        target_dir = "src/services/"
        confidence = 0.8
        rationale = "Service module"
    elif "deprecated" in role_tags:
        target_dir = "archive/legacy/"
        confidence = 0.9
        rationale = "Deprecated code"
    else:
        target_dir = "src/"
        confidence = 0.5
        rationale = "Default placement"

    file_name = Path(current_path).name
    target_path = target_dir + file_name

    blockers = []
    if file_info["deps_internal"]:
        blockers.append("internal_dependencies")

    return {
        "current_path": current_path,
        "target_path": target_path,
        "confidence": confidence,
        "rationale": rationale,
        "blockers": blockers,
    }


def main():
    if "--describe" in sys.argv[1:]:
        return print_json(describe())
    """Main entry point."""
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

    args = parser.parse_args()

    if args.describe:  # secondary path (argparse) still returns canonical schema
        return print_json(describe())

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    try:
        repo_root = Path(__file__).parent
        reports_dir = repo_root / "reports"
        reports_dir.mkdir(exist_ok=True)

        # Find and analyze all Python files
        python_files = find_python_files(repo_root)
        logger.info(f"Found {len(python_files)} Python files to analyze")

        file_inventory = []
        for file_path in python_files:
            file_info = analyze_file(file_path, repo_root)
            if file_info:
                file_inventory.append(file_info)

        logger.info(f"Successfully analyzed {len(file_inventory)} files")

        # Generate grouping proposals
        groups_proposal = []
        for file_info in file_inventory:
            proposal = propose_target_path(file_info)
            groups_proposal.append(proposal)

        # Generate reports
        with (reports_dir / "scripts_inventory.json").open("w") as f:
            json.dump(file_inventory, f, indent=2)

        with (reports_dir / "scripts_groups.json").open("w") as f:
            json.dump(groups_proposal, f, indent=2)

        # Create CSV move plan
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

        # Simple import graph
        import_graph = {
            "nodes": [
                {"id": f["path"], "role_tags": f["role_tags"]} for f in file_inventory
            ],
            "edges": [],
            "cycles": [],
        }

        with (reports_dir / "import_graph.json").open("w") as f:
            json.dump(import_graph, f, indent=2)

        with (reports_dir / "duplicates.json").open("w") as f:
            json.dump([], f, indent=2)

        # Summary
        role_counts = defaultdict(int)
        for file_info in file_inventory:
            for role in file_info["role_tags"]:
                role_counts[role] += 1

        executable_files = sum(1 for f in file_inventory if f["entrypoint"])
        files_with_describe = sum(
            1 for f in file_inventory if f["describe_support"]["has_describe"]
        )

        result = {
            "success": True,
            "files_analyzed": len(file_inventory),
            "reports_generated": [
                "scripts_inventory.json",
                "scripts_groups.json",
                "scripts_move_plan.csv",
                "import_graph.json",
                "duplicates.json",
            ],
            "summary": {
                "total_files": len(file_inventory),
                "by_role": dict(role_counts),
                "executable_files": executable_files,
                "files_with_describe": files_with_describe,
            },
        }

        print(json.dumps(result, indent=2))

    except Exception as e:
        error_result = {
            "success": False,
            "error": str(e),
            "files_analyzed": 0,
            "reports_generated": [],
        }
        print(json.dumps(error_result, indent=2))
        sys.exit(1)


if __name__ == "__main__":  # pragma: no cover
    if "--describe" in sys.argv[1:]:
        print_json(describe())
        raise SystemExit(0)
    raise SystemExit(main())
