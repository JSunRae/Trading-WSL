# Migration Plan: requestCheckerCLS -> DataManager / Legacy Adapter

## 1. Discovery Summary

- Primary legacy definition: `src/MasterPy_Trading.py` (class `requestCheckerCLS`)
- Secondary demo/duplicate definition: `src/tools/maintenance/architecture_demo.py` (illustrative only)
- No test files instantiate `requestCheckerCLS` (zero references under `tests/`)
- Modern replacement pieces already exist:
  - `DataManager` (`src/data/data_manager.py`)
  - `LegacyDataManagerAdapter` + `get_data_manager_legacy()` (`src/migration_helper.py`)
  - Extracted service modules (historical, availability, download tracker, request manager, persistence, etc.)

## 2. Usage Classification

| Category                                  | Files                                                                              | Action                                                                                     |
| ----------------------------------------- | ---------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------ |
| Real instantiation                        | `src/MasterPy_Trading.py` (InitiateTWS)                                            | Replace with `get_data_manager_legacy()` adapter instance (`Req`)                          |
| Documentation / Examples / Guides         | `tools/integration_examples.py`, `tools/migration_guide.py`, `tools/maintenance/*` | Update text to reference DataManager; remove executable instantiation examples if obsolete |
| Demo legacy class (architecture showcase) | `tools/maintenance/architecture_demo.py`                                           | Keep but annotate as illustrative (no runtime dependency)                                  |

## 3. Replacement Strategy

- For safety keep a thin compatibility object: prefer using `get_data_manager_legacy()` which returns an adapter exposing the legacy method names already mapped.
- Remove `requestCheckerCLS` implementation from `MasterPy_Trading.py`; import the adapter instead.
- Provide a shim name `requestCheckerCLS = LegacyDataManagerAdapter` in a new legacy module if any external code imports it (optional; only if external break risk is high). Current internal usage count is minimal — will opt for direct replacement in code.

## 4. Method Mapping (confirmed)

Legacy -> Adapter (already implemented internally):

- appendFailed -> download_tracker.mark_failed(...)
- appendDownloadable -> download_tracker.mark_downloadable(...)
- appendDownloaded -> download_tracker.mark_downloaded(...)
- is_failed -> download_tracker.is_failed(...)
- Download_Exists -> data_exists(...)
- On_Exit -> cleanup()
- Save_requestChecks & pacing logic: superseded by request_manager / services; if still required in legacy flow, adapter abstracts (review after removal for any missing calls).

Outstanding direct usages in monolith rely on: pacing (ReqRemaining, SleepRem, Sleep_TotalTime, SendRequest), tracking (Fail/Downloadable/DownloadedChanges counters). These should be delegated to `RequestManagerService` & `DownloadTracker` already split out; adapter must expose equivalent minimal API. If not present, create wrapper methods that delegate or no-op if unused.

## 5. Planned File Changes

1. `src/MasterPy_Trading.py`
   - Remove class `requestCheckerCLS` definition.
   - Replace instantiation `Req = requestCheckerCLS(...)` with adapter:
     ```python
     from src.migration_helper import get_data_manager_legacy
     Req = get_data_manager_legacy()  # host/port/clientId/ib not required by modern manager; if needed pass through
     ```
   - Adjust downstream references: methods used from Req either remain (adapter replicates names) or update to DataManager API.
2. Create `src/legacy/request_checker_adapter.py` (only if needed). Initial plan: NOT needed because adapter exists; add stub re-export if external compatibility desired.
3. Update examples & guides: replace literal `requestCheckerCLS` mentions with DataManager guidance (retain historical reference lines marked deprecated).
4. Public API (`src/__init__.py`, `src/api.py` if present): remove export of `requestCheckerCLS`; optionally export `get_data_manager_legacy`.
5. Add deprecation note in README migration section: how to upgrade from `requestCheckerCLS`.
6. Cleanup: remove any orphaned variables or methods that only the old class used (e.g., Loc_IBFailed if now encapsulated by DataManager). If still referenced, keep via adapter.

## 6. Incremental Steps / Order of Execution

- Step A: Generate usage map (DONE - stored in `.tasks/requestCheckerCLS_usage.json`).
- Step B: Introduce shim import in monolith; stop using internal class (leave definition temporarily untouched). Run tests.
- Step C: Delete legacy class body, replace with import of adapter. Run tests.
- Step D: Update InitiateTWS to return adapter instance (or both if needed). Run tests.
- Step E: Update docs/examples text.
- Step F: Remove references in architecture demo if not essential; otherwise annotate as legacy educational snippet.
- Step G: Update README migration notes.
- Step H: Final scan ensuring no `requestCheckerCLS` references outside comments or legacy doc examples.

## 7. Risk Mitigation

- Keep changes incremental with test run after each structural edit.
- Maintain a shim if any runtime failures appear due to unexpected attribute usage.
- Avoid refactoring pacing logic unless actively still invoked; if methods are invoked externally, create thin delegations to existing services.

## 8. Verification Checklist

- [ ] Tests pass (existing suite)
- [ ] `grep -i requestCheckerCLS` returns only docs/comment examples & adapter references
- [ ] No import errors
- [ ] ruff: no new issues introduced (minor existing ones acceptable; focus on net-neutral or improved)
- [ ] pyright: no increase in error count for touched files

## 9. Post-Migration Follow Ups (Not in this PR)

- Remove remaining legacy Excel path fallbacks once central path service fully adopted.
- Consolidate pacing logic into `request_manager_service` and delete any remaining stub methods.

## 10. Decision Log

- Chosen not to create duplicate adapter file under `src/legacy/` because `LegacyDataManagerAdapter` already exists in `migration_helper.py`.
- Will not provide `requestCheckerCLS = LegacyDataManagerAdapter` alias unless external integration tests fail.

-- End of Plan --
