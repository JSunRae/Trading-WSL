import json
from pathlib import Path

from src.services.symbol_mapping import load_symbol_mapping, to_vendor


def test_symbol_mapping_identity(tmp_path: Path):
    path = tmp_path / "mapping.json"
    path.write_text(json.dumps({"TSLA": "TSLAQ"}))
    mapping = load_symbol_mapping(path)
    assert mapping["TSLA"] == "TSLAQ"
    assert to_vendor("AAPL", "databento", path) == "AAPL"  # fallback
    assert to_vendor("TSLA", "databento", path) == "TSLAQ"
