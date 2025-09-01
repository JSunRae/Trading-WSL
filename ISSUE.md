# Tech debt: ruff C901 & mypy in high-traffic modules

This issue tracks targeted lint/type improvements to keep scope small and visible.

## Checklist

- [ ] Reduce ruff C901 complexity in the top modules:
  - src/tools/analysis/analyze_scripts.py
  - src/services/path_service.py
  - src/services/market_data/warrior_backfill_orchestrator.py

- [ ] Add minimal mypy types to stabilize key tooling paths:
  - src/services/ml_contracts/export_manifest_validator.py
  - src/tools/validate_export_manifest.py (CLI wrapper, if present)
  - src/tools/self_check.py

## Notes

- Aim for small, incremental PRs (1–2 functions per PR) with before/after ruff output in the description.
- Prefer type hints on public function signatures and focused refactors to reduce branching where C901 triggers.
- Keep behavior identical; add tests where refactors touch logic.
