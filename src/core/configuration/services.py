from __future__ import annotations

import json
import os
import shutil
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, cast

from jsonschema import Draft7Validator

SCHEMA_DIR = Path(__file__).resolve().parents[3] / "contracts" / "schemas"
CONFIG_DIR = Path(__file__).resolve().parents[3] / "config"
BACKUP_DIR = Path(__file__).resolve().parents[3] / "artifacts" / "config_backups"


@dataclass
class ValidationResult:
    valid: bool
    errors: tuple[str, ...]


def _load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _write_json_atomic(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(prefix=path.name, dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as tmp_file:
            json.dump(data, tmp_file, indent=2, sort_keys=True)
            tmp_file.flush()
            os.fsync(tmp_file.fileno())
        # Atomic replace
        Path(tmp_path).replace(path)
    finally:
        try:
            tmp = Path(tmp_path)
            if tmp.exists():
                tmp.unlink()
        except OSError:
            pass


def _schema_for(filename: str) -> Path:
    mapping = {
        "config.json": SCHEMA_DIR / "config.schema.json",
        "ib_gateway_config.json": SCHEMA_DIR / "ib_gateway_config.schema.json",
        "symbol_mapping.json": SCHEMA_DIR / "symbol_mapping.schema.json",
    }
    schema = mapping.get(filename)
    if not schema or not schema.exists():
        raise FileNotFoundError(f"Schema not found for {filename}: {schema}")
    return schema


def validate_config(filename: str, data: dict[str, Any]) -> ValidationResult:
    schema_path = _schema_for(filename)
    schema = _load_json(schema_path)
    validator = Draft7Validator(schema)
    # jsonschema types aren’t fully typed; cast to Any for iter_errors
    errors = tuple(
        sorted(
            (str(e.message) for e in cast(Any, validator).iter_errors(data)), key=str
        )
    )
    return ValidationResult(valid=not errors, errors=errors)


def load_config(filename: str) -> dict[str, Any]:
    path = CONFIG_DIR / filename
    if not path.exists():
        raise FileNotFoundError(f"Missing config file: {path}")
    return _load_json(path)


def diff_dict(old: dict[str, Any], new: dict[str, Any]) -> dict[str, Any]:
    diff: dict[str, Any] = {"changed": {}, "added": {}, "removed": {}}
    for k in old.keys() | new.keys():
        if k in old and k in new:
            if old[k] != new[k]:
                diff["changed"][k] = {"from": old[k], "to": new[k]}
        elif k in new:
            diff["added"][k] = new[k]
        else:
            diff["removed"][k] = old[k]
    return diff


def backup_config(filename: str) -> Path:
    ts = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S%z")
    src = CONFIG_DIR / filename
    dst_dir = BACKUP_DIR / ts
    dst_dir.mkdir(parents=True, exist_ok=True)
    dst = dst_dir / filename
    shutil.copy2(src, dst)
    return dst


def save_config(filename: str, data: dict[str, Any]) -> ValidationResult:
    result = validate_config(filename, data)
    if not result.valid:
        return result
    # Compute diff against current content (if exists)
    try:
        old = load_config(filename)
    except FileNotFoundError:
        old = {}
    changes = diff_dict(old, data)
    backup_config(filename)
    path = CONFIG_DIR / filename
    _write_json_atomic(path, data)
    # Publish change event (best-effort, avoid hard dependency at import time)
    try:
        import importlib

        mod = importlib.import_module("src.infra.events.config_events")
        publish = getattr(mod, "publish_config_changed", None)
        if callable(publish):
            publish(filename, changes)
    except Exception:
        # Best-effort: ignore failures in event publishing
        pass
    return result
