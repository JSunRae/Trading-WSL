import json
import pathlib
import subprocess
import sys


def test_backfill_describe_returns_json():
    mod_path = pathlib.Path("src/tools/auto_backfill_from_warrior.py")
    assert mod_path.exists()
    out = subprocess.check_output(
        [sys.executable, str(mod_path), "--describe"], text=True
    )
    data = json.loads(out)
    assert data["name"] == "auto_backfill_from_warrior"
    assert "inputs" in data
