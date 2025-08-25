from __future__ import annotations

import importlib
import json
import subprocess
import sys

from src.tools._cli_helpers import DescribeSchema, iter_tool_modules

SCHEMA = DescribeSchema()


def run_tool(module: str) -> dict[str, object]:
    """Execute a tool module with --describe and return parsed JSON."""
    # Convert module to path for python -m execution
    cmd = [sys.executable, "-m", module, "--describe"]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
    assert proc.returncode == 0, f"{module} exited {proc.returncode}: {proc.stderr}"
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError as e:  # pragma: no cover
        raise AssertionError(
            f"Invalid JSON from {module}: {e}\nOutput: {proc.stdout}"
        ) from e
    return data


def discover_tool_modules() -> list[str]:
    modules: list[str] = []
    for mod in iter_tool_modules():
        # quick import check; skip if import error (legacy / not CLI)
        try:
            importlib.import_module(mod)
        except Exception:
            continue
        modules.append(mod)
    return sorted(set(modules))


def test_describe_schema_all_tools():
    modules = discover_tool_modules()
    assert modules, "No tool modules discovered"
    for mod in modules:
        data = run_tool(mod)
        errs = SCHEMA.validate(data)
        assert not errs, f"Schema errors in {mod}: {errs}"
        # Spot checks
        assert isinstance(data["name"], str)
        assert isinstance(data["description"], str)
        assert isinstance(data["dependencies"], list)
        assert isinstance(data["examples"], list)
        assert data["examples"], "examples should not be empty"
        assert isinstance(data["outputs"], dict)
        assert "stdout" in data["outputs"]
        # Inputs may be dict or list; if dict ensure each entry has type
        inputs = data["inputs"]
        if isinstance(inputs, dict):
            for k, v in list(inputs.items()):  # type: ignore[assignment]
                assert isinstance(v, dict), f"input {k} should map to dict"
                assert "type" in v, f"input {k} missing type"
        elif isinstance(inputs, list):
            for item in list(inputs):  # type: ignore[assignment]
                assert isinstance(item, dict)
                assert "name" in item and "type" in item
        else:  # pragma: no cover
            raise AssertionError("inputs not dict or list")
