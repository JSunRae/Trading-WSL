# BarCLS Retirement Decision

Date: 2025-08-17

## 1. Usage Inventory

Generated in `reports/retire_barcls_usages.json`.

| Category               | Count | Files                                     |
| ---------------------- | ----- | ----------------------------------------- |
| Production definitions | 1     | `src/MasterPy_Trading.py`                 |
| Production call sites  | 0     | (none)                                    |
| Test call sites        | 4     | `tests/test_masterpy_trading_interval.py` |

No other `BarCLS(` constructions or `from MasterPy_Trading import BarCLS` patterns detected in `src/`, `tools/`, or `scripts/`.

## 2. Options Assessment

### Option A: Replace with enum + helper

- Create `src/core/intervals.py` with `format_legacy_duration(start, end)`.
- Update tests to call helper directly.
- Delete `BarCLS`.
- Pros: Clean functional API; encourages typed uses.
- Cons: Test currently exercises object; small churn to adjust tests.

### Option B: Move BarCLS to test helper (Chosen)

- Create `tests/helpers/legacy_bar.py` containing `BarClsTestShim` replicating logic.
- Update tests to import that; delete `BarCLS` from production.
- Pros: Removes dead code from prod; isolates legacy behavior purely for backward-compat test; simplest (only tests touched).
- Cons: Leaves a shim but confined to test scope.

### Option C: Minimal adapter in infra

- Not required; no external prod consumers remaining.

## 3. Rationale for Option B

- Zero production call sites; only tests depend on object form.
- Minimizes production diff footprint (no need to add new core helper unless/ until real usage emerges).
- Keeps legacy duration formatting logic colocated with its only remaining consumer (tests).

## 4. Legacy Behavior Preservation Requirements

All enforced in planned shim:

- Accept str / datetime / pandas.Timestamp; invalid -> "0 S".
- Negative -> "0 S".
- Exactly 60 seconds -> integer 0.
- < 1 day -> "<seconds> S".
- > = 1 day -> "<days> D" (min 1).

## 5. Implementation Plan

1. Create `tests/helpers/legacy_bar.py` with `BarClsTestShim` implementing legacy rules.
2. Update `tests/test_masterpy_trading_interval.py` to import shim instead of module import of `src.MasterPy_Trading` for Bar access; keep module import if other legacy pieces required (currently only BarCLS used there).
3. Remove `BarCLS` (and file) from `src/MasterPy_Trading.py`; replace module with deprecation notice or remove file if nothing remains (MasterPy_Trading currently only holds BarCLS after earlier cleanups).
4. Run tests; ensure all pass.
5. Lint / type-check changed files.

## 6. Risk & Mitigation

- Risk: Hidden external import of `src.MasterPy_Trading.BarCLS` outside repo. Mitigation: Provide clear deprecation message in removed module stub explaining replacement path; tests ensure behavior parity.
- Risk: Duration formatting regression. Mitigation: Existing interval tests cover main cases (minutes, 60-sec special, 1-day boundary, invalid input).

## 7. Next Steps After Merge

- If in future production needs duration formatting, promote shim logic to `core/intervals.py` and reuse from tests.

## 8. Decision

**Proceed with Option B now.**

---
