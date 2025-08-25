# Refactor Plan for src/MasterPy_Trading.py

## Scope

Target the current script only. Enumerate issues, propose fixes with tradeoffs, acceptance criteria, and assess repo-wide impact for any signature/behavior changes. Implement safe, backward-compatible changes, add minimal tests, and validate with existing CI gates.

## Issues Inventory

1. API misuse and signature mismatches

- Evidence: Market_InfoCLS.get_TradeDates(forDate, Bar, daysWanted) requires Bar but requestCheckerCLS.get_TradeDates forwarded as get_TradeDates(forDate, daysWanted) (lines around 837), passing an int into Bar. Call sites (e.g., src/ib_Warror_dl.py) call get_TradeDates(forDate, daysWanted=5) without Bar.
- Risk: Runtime errors when Market calendar is available; incorrect behavior in fallback.
- Desired: Backward-compatible get_TradeDates that accepts old calls (no Bar) and infers 1-min behavior by default; correct forwarding to market info method.
- Options:
  A. Change signature to include optional Bar and default minute behavior. (Chosen)
  B. Require Bar everywhere and update call sites. (Breaking)
- Acceptance: Old call sites unchanged; returns sensible dates; tests added.

2. Wrong Bar type checks in Market_InfoCLS.get_TradeDates

- Evidence: Compares Bar.BarType to string "1 min" instead of int code (2). Both fallback and schedule branches.
- Desired: Correctly detect minute bars; handle Bar optional.
- Options: Use isinstance/attribute check; also accept string inputs containing "min" for robustness. (Chosen)
- Acceptance: Unit test verifies minute path returns N prior trade days.

3. Async misuse in Download_Historical and throttling

- Evidence: In async Download_Historical, uses self.ib.sleep(...) without await; calls synchronous SendRequest which may block via time.sleep; calls async getEarliestAvailBar without await.
- Desired: No blocking sleeps in async context; await async API calls; preserve rate-limiting.
- Options:
  A. Introduce async aSendRequest with awaitable sleeps; use await asyncio.sleep in loops; await getEarliestAvailBar. (Chosen)
  B. Convert everything to sync (undesirable).
- Acceptance: No un-awaited coroutine warnings; passes type checks; tests exercise code paths lightly.

4. IB_Download_Loc call argument errors

- Evidence: Calls IB_Download_Loc with BarObj.BarSize (str) where function expects BarObj with BarType (lines ~1486, ~1489, ~1750).
- Desired: Pass full BarObj.
- Options: Update call sites in this file. (Chosen)
- Acceptance: Paths resolve without attribute errors.

5. Minor correctness and hygiene

- Evidence: Missing method invocation `self.Save_requestChecks` (missing parentheses) in Download_Historical; loose None checks; broad `except:` clauses.
- Desired: Invoke method; use `is None`; narrow `except Exception` in non-critical places.
- Options: Small safe edits. (Chosen)
- Acceptance: Lints cleaner; no behavior change.

## Impact Analysis (repo-wide)

- Changed: requestCheckerCLS.get_TradeDates signature to accept optional Bar; still supports prior usage (positional/keyword daysWanted). Internal forwarding uses named args to Market_InfoCLS.
- Changed: Market_InfoCLS.get_TradeDates now has Bar optional with default minute behavior; existing direct uses (none outside this module) unaffected.
- Internal-only changes to Download_Historical and SendRequest (adds aSendRequest and uses it internally). No external references to aSendRequest.
- IB_Download_Loc call fixes are local to this file; other modules already use service wrappers or pass appropriate objects.

Files to watch for call site impact:

- src/ib_Warror_dl.py (calls req.get_TradeDates(DateStp, daysWanted=5)) — remains valid.
- src/tools/maintenance/update_data.py — uses daysWanted kwarg; remains valid.

## Test Plan

- Add tests for:
  - Market_InfoCLS.get_TradeDates fallback minute behavior (no market_cal), verifying length and formatting.
  - requestCheckerCLS.get_TradeDates backward-compat call (no Bar) returns multiple days (default minute behavior).

## Acceptance Gates

- pyright/pyright task passes for updated files (no new errors in this script).
- pytest passes with coverage unchanged or improved.
- ruff check yields no new issues in the edited sections.

## Tradeoffs

- aSendRequest duplicates some logic to maintain sync SendRequest for existing sync call sites. This avoids blocking in async contexts without breaking sync behavior.
- Market calendar unavailable path uses simplified weekday logic; preserves current fallback behavior.

## Migration

- No external API breaks. If future deprecation desired, consider emitting a DeprecationWarning when get_TradeDates is called without Bar; not done now to avoid noisy tests.

# Script Plan: src/MasterPy_Trading.py

Date: 2025-08-12
Owner: Safe-Refactor Agent

## Inventory and Findings

1. Time delta arithmetic on mixed types

- Evidence: get_intervalReq uses `EndTime - StartTime` where inputs can be Any/str/datetime (line ~611).
- Risks: Type errors at runtime, negative intervals, incorrect units.
- Desired: Strict conversion to pandas.Timestamp; clamp negatives; default fallback.
- Options:
  - A) Best-effort conversion with try/except.
  - B) Strict helper `_to_timestamp_or_none` with fallback. (Chosen)
- Acceptance: No arithmetic on str/Any; unit tests cover D/H/M/S paths and edge cases (invalid inputs).

2. Typing alias issue (`Variable not allowed in type expression`)

- Evidence: Bare `Symbol`/`BarSize` in annotations caused pyright errors.
- Desired: Stable local aliases (SymbolT, BarSizeT) resolving to project types or str fallback.
- Options:
  - A) Import typing.TypeAlias and assign aliases.
  - B) Python 3.12 `type` aliases. (Chosen)
- Acceptance: `pyright src/MasterPy_Trading.py` shows 0 errors.

3. Quoted annotations with future annotations

- Evidence: "BarCLS" was quoted in signatures.
- Desired: Unquoted annotations when using future annotations.
- Acceptance: No UP007/quoted type issues; file type-checks.

4. Async pitfalls

- Evidence: Awaiting IB timestamp async call is present; check for blocking calls inside async.
- Desired: No time.sleep or blocking I/O in async; ensure awaits where needed.
- Status: No new async misuse introduced; further refactor deferred.

5. Error handling and bare excepts

- Evidence: Several bare `except:` blocks elsewhere in file (outside current changes).
- Desired: Narrow exceptions with context; maintain current behavior pending larger refactor.
- Acceptance: Mark for follow-up refactor; no new bare excepts added.

6. Pandas schema and type safety

- Evidence: Untyped DataFrame operations; fillna_typed expects DataFrame but receives Series in one place.
- Desired: Adjust call to pass DataFrame or use a Series-compatible helper; defer to follow-up.

## Impact Analysis (repo-wide)

- No external imports of requestCheckerCLS/BarCLS found across src/ and tests.
- Methods updated type annotations only; behavior unchanged except safer interval math.
- Breaking changes: None (annotations only). Behavior: Interval calc now clamps negative and falls back on invalid inputs.
- Migration: Not required.

## Implementation Notes

- Implemented strict timestamp conversion in get_intervalReq with `_to_timestamp_or_none` and clamping.
- Added local type aliases `SymbolT` and `BarSizeT` via `type` keyword.
- Removed unnecessary quoted type annotations.

## Acceptance Criteria

- `npx --no-install pyright src/MasterPy_Trading.py` -> 0 errors.
- Interval calculation tests cover valid/invalid inputs; negative durations clamp to 0.
- CI gates unchanged; tests pass with coverage non-regressing.

## Follow-ups (deferred)

- Replace bare excepts with precise exceptions.
- Fix Series/DataFrame mismatch for fillna_typed or introduce Series variant.
- Improve import ordering and lints via per-file ignore or local changes without behavior change.
- Async hygiene audit for entire module.
