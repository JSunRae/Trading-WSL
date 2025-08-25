# Warrior Legacy Cleanup Report

## Summary

The legacy module `src/ib_Warror_dl.py` has been retired and replaced by a modern CLI tool `src/tools/warrior_update.py` plus minor helpers added to `DataManager`.

## Actions Performed

- Inventoried legacy symbols and external usages.
- Generated `reports/cleanup_warrior_usages.json` mapping functions → callers.
- Implemented modern replacement CLI: `warrior_update.py` with modes: main, recent, mark-downloaded, trainlist.
- Added thin helper wrappers `warrior_list()` and `train_list_loadsave()` to `DataManager`.
- Rewired maintenance script `run_data_update.py` to invoke the new CLI instead of legacy functions.
- Converted `ib_Warror_dl.py` into a strict deprecation stub raising on any call.
- Began refactoring `update_data.py` (partial modernization; further simplification recommended – high complexity hotspots remain e.g. update_symbol_data).

## Legacy → Modern Mapping

| Legacy Function                          | Status                    | Modern Equivalent                                        |
| ---------------------------------------- | ------------------------- | -------------------------------------------------------- |
| Update_Warrior_Main                      | Removed (stub raises)     | warrior_update --mode main                               |
| Update_Warrior_30Min                     | Removed (stub raises)     | warrior_update --mode recent                             |
| Update_Downloaded                        | Removed (stub raises)     | warrior_update --mode mark-downloaded                    |
| Create_Warrior_TrainList                 | Removed (stub raises)     | warrior_update --mode trainlist                          |
| WarriorListCLS / AvTimeCLS / ExitTrigger | Deleted/Not Reimplemented | Replaced by DataManager + simple timing via perf_counter |

## Follow-up Recommendations

1. Finish simplifying `update_data.py` (remove residual references to internal legacy-style request object methods like Download_Exists / avail2Download if still present after full modernization).
2. Add unit tests covering each warrior_update mode for a small synthetic warrior list.
3. After external automation is confirmed updated, delete `src/ib_Warror_dl.py` entirely.
4. Consider adding a guard test that fails if any source references `ib_Warror_dl`.

## Removal Guard

Current stub raises RuntimeError guiding users to the new CLI. Search confirms no functional imports remain beyond docs/comments.

## Commit Message Template

refactor: retire ib_Warror_dl legacy; rewire to warrior_update CLI (no PSLoc, no MP.ErrorCapture)

---

Generated automatically as part of legacy retirement process.

## Update (Modernization of update_data.py)

The file `src/tools/maintenance/update_data.py` has now been fully refactored into a slim modern CLI that:

- Uses only `DataManager` + `HistoricalDataService` with `DownloadRequest`, `BarSize`, `DataType.TRADES`.
- Replaces legacy request object calls (`Download_Exists`, `avail2Download`, append\* methods) with `DataManager.data_exists` and direct download attempts.
- Preserves legacy behavior of 5 recent trade-day attempts for `1 min` and single-day fetch for other frames.
- Supports symbol collection from the warrior list or explicit `--symbols`.

No legacy constructs (PSLoc, MP.ErrorCapture, direct Stock contract creation) remain in this module.

Follow-up: consider consolidating overlapping functionality with `warrior_update.py` to reduce duplication and add unit tests for the new CLI.
