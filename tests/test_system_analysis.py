from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

SCRIPT = Path("src/tools/system_analysis.py")


def run(cmd: list[str]) -> tuple[int, str, str]:
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
    return proc.returncode, proc.stdout, proc.stderr


def test_system_analysis_describe():
    # Run as module path for proper package-relative imports
    code, out, err = run(
        [sys.executable, "-m", "src.tools.system_analysis", "--describe"]
    )
    assert code == 0, err
    data = json.loads(out)
    assert data["name"] == "system_analysis"
    assert "description" in data
    assert "outputs" in data and "stdout" in data["outputs"]
    assert any(ex["command"].endswith("--describe") for ex in data["examples"])


def test_system_analysis_run_basic():
    code, out, err = run([sys.executable, "-m", "src.tools.system_analysis"])
    assert code == 0, err
    data = json.loads(out)
    for key in [
        "tool",
        "python_version",
        "platform",
        "venv_active",
        "cwd",
        "config_checks",
        "ib_available",
        "paths_ok",
        "warnings",
    ]:
        assert key in data, f"missing {key}"
    assert data["tool"] == "system_analysis"
    assert isinstance(data["config_checks"], dict)
    assert isinstance(data["warnings"], list)
