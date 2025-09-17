"""Validate TF_1 export manifests against Trading's acceptance rules.

This validator is intentionally small and dependency-light so it can be used in
CI and ops paths. It enforces:

- Known schema_version (reject unknown)
- Presence of a production alias for promoted models (metadata.production.alias)
- Metrics thresholds when a promotion.rule.json is available

Input contract (manifest JSON object):
{
  "schema_version": "1.0",
  "model": {
    "id": "uuid-or-name",
    "version": "v2025.08.31",
    "metadata": {
      "production": {"alias": "my-model-stable"}
    }
  },
  "artifacts": [
    {"type": "feature_parquet", "path": "...", "schema": {"version": "1"}}
  ],
  "metrics": {
    "sharpe": 1.7,
    "f1": 0.45,
    "max_drawdown": -0.10
  }
}

Return shape:
{"ok": bool, "errors": [str], "warnings": [str]}
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

# Accept both semantic and tagged forms for schema version for backward/forward compat
# with TF_1 exports and contracts repo. Keep list narrow and explicit.
ALLOWED_SCHEMA_VERSIONS = {"1.0", "v1"}


def _contracts_base(repo_root: Path) -> Path | None:
    # Allow override via env var CONTRACTS_DIR; else default to repo_root/contracts
    import os as _os

    p = _os.getenv("CONTRACTS_DIR")
    if p:
        base = Path(p)
        return base if base.exists() else None
    default = repo_root / "contracts"
    return default if default.exists() else None


def _load_promotion_rule(repo_root: Path) -> dict[str, Any] | None:
    # 1) Repo root (used by tests)
    root_rule = repo_root / "promotion.rule.json"
    if root_rule.exists():
        try:
            data = json.loads(root_rule.read_text())
            return cast(dict[str, Any], data) if isinstance(data, dict) else None
        except Exception:
            return None
    # 2) contracts/ tree
    base = _contracts_base(repo_root)
    if base:
        try:
            for p in base.rglob("promotion.rule.json"):
                try:
                    data = json.loads(p.read_text())
                    return (
                        cast(dict[str, Any], data) if isinstance(data, dict) else None
                    )
                except Exception:
                    continue
        except Exception:
            return None
    return None


def _validate_against_json_schema(
    manifest: dict[str, Any], *, repo_root: Path
) -> list[str]:
    """Validate manifest against local JSON Schema (v1) when available.

    We avoid hard dependency on jsonschema; if unavailable, skip with no error.
    Returns a list of schema error strings.
    """
    # Best-effort import: if jsonschema isn't installed, silently skip.
    try:
        import jsonschema  # type: ignore
    except Exception:
        return []

    # Locate schema under contracts/ or repo root fallback.
    schema_path: Path | None = None
    # Prefer contracts/ tree
    base = _contracts_base(repo_root)
    if base:
        try:
            for p in base.rglob("manifest.schema.v1.json"):
                schema_path = p
                break
        except Exception:
            schema_path = None
    # Fallback to legacy in-tree location for backward compat
    if schema_path is None:
        legacy = repo_root / "src/services/ml_contracts/manifest.schema.v1.json"
        schema_path = legacy if legacy.exists() else None
    if schema_path is None or not schema_path.exists():
        return []

    # Load schema; surface only genuine local schema errors.
    try:
        schema = json.loads(schema_path.read_text())
    except Exception as e:  # malformed schema on disk
        return [f"invalid local JSON Schema: {e}"]

    # Validate and return any validation error as a single message.
    try:
        from typing import Any as _Any

        validator: _Any = getattr(jsonschema, "validate", None)
        if validator is None:
            return []
        validator(instance=manifest, schema=schema)
        return []
    except Exception as e:
        return [str(e)]


def _extract_alias(manifest: dict[str, Any]) -> str | None:
    model_any = manifest.get("model")
    model: dict[str, Any] = (
        cast(dict[str, Any], model_any) if isinstance(model_any, dict) else {}
    )
    meta_any = model.get("metadata")
    meta: dict[str, Any] = (
        cast(dict[str, Any], meta_any) if isinstance(meta_any, dict) else {}
    )
    prod_any = meta.get("production")
    prod: dict[str, Any] = (
        cast(dict[str, Any], prod_any) if isinstance(prod_any, dict) else {}
    )
    alias_any = prod.get("alias")
    return alias_any if isinstance(alias_any, str) else None


def _apply_promotion_thresholds(
    manifest: dict[str, Any], rule: dict[str, Any]
) -> list[str]:
    errs: list[str] = []
    raw_metrics = manifest.get("metrics")
    metrics: dict[str, Any] = (
        cast(dict[str, Any], raw_metrics) if isinstance(raw_metrics, dict) else {}
    )
    try:
        min_sharpe = float(rule.get("min_sharpe", 1.5))
        min_f1 = float(rule.get("min_f1", 0.40))
        min_maxdd = float(rule.get("min_max_drawdown", -0.15))
    except Exception:
        min_sharpe, min_f1, min_maxdd = 1.5, 0.40, -0.15
    sharpe_any = metrics.get("sharpe")
    f1_any = metrics.get("f1")
    maxdd_any = metrics.get("max_drawdown")
    sharpe = float(sharpe_any) if isinstance(sharpe_any, (int, float, str)) else None  # noqa: UP038
    f1 = float(f1_any) if isinstance(f1_any, (int, float, str)) else None  # noqa: UP038
    maxdd = float(maxdd_any) if isinstance(maxdd_any, (int, float, str)) else None  # noqa: UP038
    if sharpe is None or sharpe < min_sharpe:
        errs.append(f"Sharpe below threshold: {sharpe} < {min_sharpe}")
    if f1 is None or f1 < min_f1:
        errs.append(f"F1 below threshold: {f1} < {min_f1}")
    if maxdd is None or maxdd < min_maxdd:
        errs.append(f"MaxDD below threshold: {maxdd} < {min_maxdd}")
    return errs


def validate_export_manifest(
    manifest: dict[str, Any],
    *,
    repo_root: Path,
    require_alias_file_in: Path | None = None,
) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []

    # 1) Schema version
    sv = str(manifest.get("schema_version", ""))
    if sv not in ALLOWED_SCHEMA_VERSIONS:
        errors.append(
            f"Unknown schema_version: '{sv}' (allowed: {sorted(ALLOWED_SCHEMA_VERSIONS)})"
        )

    # 1b) Optional JSON Schema check (best-effort)
    for err in _validate_against_json_schema(manifest, repo_root=repo_root):
        if err:
            errors.append(f"schema: {err}")

    # 2) Production alias (required for promotion)
    alias = _extract_alias(manifest)
    if not alias:
        errors.append("Missing model.metadata.production.alias")
    elif require_alias_file_in:  # only when alias present
        alias_file = Path(require_alias_file_in) / "production.alias"
        if not alias_file.exists():
            errors.append(
                f"production.alias file missing in model dir: {alias_file} (required for non-dry emissions)"
            )

    # 3) Promotion thresholds (if rule present)
    rule = _load_promotion_rule(repo_root)
    if rule:
        errors.extend(_apply_promotion_thresholds(manifest, rule))
    else:
        warnings.append(
            "promotion.rule.json not found; skipping metric threshold checks"
        )

    return {"ok": not errors, "errors": errors, "warnings": warnings}


def validate_export_manifest_file(
    path: str | Path,
    *,
    repo_root: Path | None = None,
    require_alias_file_in: Path | None = None,
) -> dict[str, Any]:
    p = Path(path)
    root = repo_root or Path(__file__).resolve().parents[3]
    data = json.loads(p.read_text())
    return validate_export_manifest(
        data, repo_root=root, require_alias_file_in=require_alias_file_in
    )
