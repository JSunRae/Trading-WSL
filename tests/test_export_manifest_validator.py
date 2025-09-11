from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.services.ml_contracts.export_manifest_validator import (
    validate_export_manifest,
)


def test_rejects_unknown_schema_version(tmp_path: Path) -> None:
    manifest: dict[str, Any] = {
        "schema_version": "9.9",
        "model": {"metadata": {"production": {"alias": "foo"}}},
        "metrics": {"sharpe": 2.0, "f1": 0.5, "max_drawdown": -0.05},
    }
    result = validate_export_manifest(manifest, repo_root=tmp_path)
    assert not result["ok"]
    assert any("Unknown schema_version" in e for e in result["errors"])


def test_requires_production_alias(tmp_path: Path) -> None:
    manifest: dict[str, Any] = {
        "schema_version": "1.0",
        "model": {"metadata": {}},
        "metrics": {"sharpe": 2.0, "f1": 0.5, "max_drawdown": -0.05},
    }
    result = validate_export_manifest(manifest, repo_root=tmp_path)
    assert not result["ok"]
    assert any("production.alias" in e for e in result["errors"])


def test_thresholds_applied_when_rule_present(tmp_path: Path) -> None:
    rule = {
        "min_sharpe": 1.5,
        "min_f1": 0.40,
        "min_max_drawdown": -0.15,
    }
    (tmp_path / "promotion.rule.json").write_text(json.dumps(rule))

    bad: dict[str, Any] = {
        "schema_version": "1.0",
        "model": {"metadata": {"production": {"alias": "ok"}}},
        "metrics": {"sharpe": 1.2, "f1": 0.39, "max_drawdown": -0.20},
    }
    res_bad = validate_export_manifest(bad, repo_root=tmp_path)
    assert not res_bad["ok"]
    assert (
        any("Sharpe" in e for e in res_bad["errors"])
        and any("F1" in e for e in res_bad["errors"])
        and any("MaxDD" in e for e in res_bad["errors"])
    )

    good: dict[str, Any] = {
        "schema_version": "1.0",
        "model": {"metadata": {"production": {"alias": "ok"}}},
        "metrics": {"sharpe": 1.6, "f1": 0.45, "max_drawdown": -0.10},
    }
    res_good = validate_export_manifest(good, repo_root=tmp_path)
    assert res_good["ok"]


def test_requires_alias_file_when_model_dir_provided(tmp_path: Path) -> None:
    manifest: dict[str, Any] = {
        "schema_version": "1.0",
        "model": {"metadata": {"production": {"alias": "foo"}}},
        "metrics": {"sharpe": 2.0, "f1": 0.5, "max_drawdown": -0.05},
    }
    # Missing alias file
    res = validate_export_manifest(
        manifest, repo_root=tmp_path, require_alias_file_in=tmp_path
    )
    assert not res["ok"]
    assert any("production.alias" in e for e in res["errors"])
    # Create the alias file and re-validate
    (tmp_path / "production.alias").write_text("tf1-model-stable\n")
    res2 = validate_export_manifest(
        manifest, repo_root=tmp_path, require_alias_file_in=tmp_path
    )
    assert res2["ok"]
