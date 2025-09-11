from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def _run(cmd: list[str]) -> tuple[int, str, str]:
    p = subprocess.run(cmd, capture_output=True, text=True)
    return p.returncode, p.stdout, p.stderr


def test_validate_export_manifest_observability_keys(tmp_path: Path) -> None:
    # Use sample manifest; ensure production.alias present to PASS
    repo = Path(__file__).resolve().parents[1]
    manifest = repo / "examples" / "tf1_export_manifest.sample.json"
    model_dir = tmp_path / "model"
    model_dir.mkdir(parents=True, exist_ok=True)
    (model_dir / "production.alias").write_text("tf1-model-stable")

    code, out, err = _run(
        [
            sys.executable,
            "-m",
            "src.tools.validate_export_manifest",
            "--manifest",
            str(manifest),
            "--model-dir",
            str(model_dir),
        ]
    )
    assert code == 0, f"Expected success exit code; stderr={err} stdout={out}"
    data = json.loads(out)
    # Required observability keys
    for key in ["run_id", "model_id", "stage_latency_ms"]:
        assert key in data, f"Missing observability key: {key}"
    assert isinstance(data["stage_latency_ms"], dict)
    # Optional keys should exist (best-effort) even if None
    assert "symbol" in data
    assert "symbols" in data
    assert "data_window" in data
