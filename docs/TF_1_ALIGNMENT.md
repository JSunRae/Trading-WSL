# TF_1 Alignment Guide

Purpose: align the Trading platform with TF_1 (ML project) across data, APIs, environments, and operations. This document lists contracts and practical guidance so both repos can integrate smoothly without surprises.

Last updated: 2025-08-31

## Scope and Principles

- Contracts first: explicit, minimal, stable hand-offs.
- Idempotent and deterministic artifacts for reproducible ML.
- Backward compatible changes preferred; announce breaking changes.
- Clear ownership: Trading produces market data and orchestration; TF_1 consumes data and produces models/features.

## Shared Environment and Paths

Authoritative env docs live in `docs/ENVIRONMENT.md`. Keys most relevant to TF_1:

- ML_BASE_PATH: root ML data directory (default: `~/Machine Learning`).
- ML_BACKUP_PATH: optional mirror for critical files.
- LOGS_PATH, TEMP_PATH, CONFIG_PATH: operational infra.
- DATA_PATH_OVERRIDE: repo-local override for data (default `./data`).
- LEVEL2_DIRNAME: subdir name for live L2 under ML base (default `Level2`).
- SYMBOL_MAPPING_FILE: JSON mapping local → vendor symbols.
- DATABENTO*\* and L2*\*: control historical backfill behavior and windows.

Recommendation: define these in a shared `.env` or centralized secrets store and keep values consistent across Trading and TF_1. Trading reads them via `src/core/config.py`.

## Data Contracts (Primary)

### Level 2 Snapshots (Live capture via IBKR)

- Location: `${DATA_PATH_OVERRIDE or ML_BASE_PATH}/level2/{SYMBOL}/` for this repo; TF_1 should support both base path styles.
- Files:
  - `{YYYY-MM-DD}_snapshots_{HHMMSS}.parquet`
  - `{YYYY-MM-DD}_messages_{HHMMSS}.json`
  - `session_stats_{YYYYMMDD_HHMMSS}.json`
- Parquet columns (as produced by `src/tools/record_depth.py`):
  - `timestamp` (ISO 8601, UTC)
  - `bid_prices` (list[float], size N)
  - `bid_sizes` (list[int], size N)
  - `ask_prices` (list[float], size N)
  - `ask_sizes` (list[int], size N)
- JSON messages capture raw depth update events with:
  - `timestamp`, `operation` (add/update/remove), `side` (bid/ask), `level`, `price`, `size`, `symbol`.

Notes:

- Snapshot arrays are fixed-length by `levels` (default 10). Missing levels are zeros.
- Session stats contain high-level metadata (num_snapshots/messages, interval_ms, etc.).

### Level 2 Snapshots (Historical backfill via DataBento)

- Location and layout match live capture for downstream agnosticism.
- Filenames include `_databento` suffix for provenance, e.g.:
  - `{YYYY-MM-DD}_snapshots_databento.parquet` (exact naming from provider wrapper; ensure TF_1 treats suffix as a source tag, not a different schema).
- Schema: column names are identical to live snapshots. TF_1 can merge sources safely on columns.

### Manifests and Run Artifacts

- `backfill_l2_manifest.jsonl` (append-only JSON Lines): per-task status with fields:
  - `symbol` (string), `date` (YYYY-MM-DD), `status` (WRITE | SKIP | EMPTY | ERROR)
- `backfill_l2_summary.json` (overwritten per run): aggregate summary with fields:
  - `counts` (dict of WRITE/SKIP/EMPTY/ERROR), `zero_row_tasks` ([symbol, date] list), `errors` (list[str])
  - `total_tasks`, `duration_sec`, `strict`, `force`, `max_tasks`, `concurrency`

- `bars_download_manifest.jsonl` (append-only JSON Lines): emitted whenever hourly/minute/second bars are written. Fields:
  - `schema_version` (string; currently `bars_manifest.v1`)
  - `written_at` (ISO 8601)
  - `vendor` (e.g., `IBKR`)
  - `file_format` (e.g., `parquet`)
  - `symbol` (string)
  - `bar_size` (e.g., `1 hour`, `1 min`, `1 sec`)
  - `path` (absolute path)
  - `filename` (basename)
  - `rows` (int)
  - `columns` (list[str])
  - `time_start` (ISO 8601 or null)
  - `time_end` (ISO 8601 or null)

- `bars_coverage_manifest.json` (compact summary built from the append-only manifest): summarizes current coverage per `(symbol, bar_size)` with per-day best files and overall date range. Fields:
  - `schema_version` (string; currently `bars_coverage.v1`)
  - `generated_at` (ISO 8601)
  - `entries` (list): each entry has
    - `symbol` (string)
    - `bar_size` (string; `1 hour` | `1 min` | `1 sec`)
    - `total` (object): `{ "date_start": YYYY-MM-DD, "date_end": YYYY-MM-DD }`
    - `days` (list): best file per day with fields `{ "date", "time_start", "time_end", "path", "filename", "rows" }`

Production path and refresh:

- Location: `${DATA_PATH_OVERRIDE or ML_BASE_PATH}/bars_coverage_manifest.json`
- Producer: `src/tools/analysis/build_bars_coverage.py`
- Auto-refresh: invoked at the end of `auto_backfill_from_warrior.py` runs; can also be run directly.

Consumption guidance for TF_1:

- Treat this as the fast “current index” to plan incremental downloads and resume partial days.
- Prefer coverage to discover which days are present and which are missing per `(symbol, bar_size)` without scanning directories.
- For training, iterate `entries[*].days` and read `path` for the best available file per day. Fall back to the append-only manifest if deeper provenance is required.

Compatibility:

- This file is fully derived from `bars_download_manifest.jsonl`. If the schema evolves, a new `schema_version` will be introduced; reject unknown versions.

Consumption guidance for TF_1:

- Use this manifest to discover available bar files quickly instead of walking directories.
- Filter by `bar_size` and `symbol`; prefer the newest `written_at` per `(symbol, bar_size, time_start, time_end)` if duplicates exist.
- Treat `schema_version` as a gate; reject unknown versions.

Usage guidance for TF_1:

- Consume manifest incrementally to detect which (symbol, date) are newly written vs skipped vs empty.
- Treat `EMPTY` as a semantic “zero rows from vendor” and record for data quality flags; do not fail the pipeline unless policy demands.

## Programmatic APIs (Produced by Trading)

### Backfill API

- Function: `src.services.market_data.backfill_api.backfill_l2(symbol: str, trading_day: date, *, force: bool=False, strict: bool=False) -> dict`
- Status codes in result:
  - `status`: `written` | `skipped` | `error`
  - `zero_rows`: bool (true when vendor returned 0 rows; pairs with `skipped`)
  - `path`: file path when written or existing
  - `rows`: int (vendor-reported row count when available)
  - `error`: optional string when `status == error`
- Behavior:
  - Idempotent atomic writes; skip if destination exists unless `force=True`.
  - Windowing conforms to `L2_BACKFILL_WINDOW_ET` and `L2_TRADING_WINDOW_ET` when enforced.

### Orchestrator (Batch)

- Discovery: `find_warrior_tasks(since_days: int|None=None, last: int|None=None) -> list[tuple[str, date]]`
- Execution: `run_warrior_backfill(tasks, *, force=False, strict=False, max_tasks=None, max_workers=None) -> dict`
- Deterministic ordering: input order preserved in manifest regardless of concurrency.

Integration tip for TF_1:

- For ad-hoc experiments, import `backfill_l2` directly and call per (symbol, day) to ensure on-demand data availability.
- For large cohorts, use the orchestrator with `max_workers` tuned for vendor rate limits.

## Symbol Mapping

- Source: JSON file referenced by `SYMBOL_MAPPING_FILE` (default `config/symbol_mapping.json`).
- Purpose: map local symbols to vendor-specific symbols.
- Identity entries (AAPL → AAPL) are allowed but warn; keep mapping minimal.
- TF_1 should use the same mapping file or at least be aware of non-identity entries to avoid mismatches.

## Operational Considerations

- Concurrency: set via `L2_MAX_WORKERS` (or legacy `L2_BACKFILL_CONCURRENCY`). Coordinate with vendor rate limits; default 4.
- Idempotence: both API and CLI avoid re-writing existing data; `_databento` suffix avoids source collision with live files.
- Zero-row days: tracked separately; ingest but flag for quality. Re-run with a wider window if appropriate.
- Time windows: ET-based `HH:MM-HH:MM` strings; DST-aware via `America/New_York`. Ensure TF_1 normalizes to ET when deriving features tied to specific sessions.
- Logging: `LOG_LEVEL` controls verbosity. Batch SUMMARY lines are machine-parsable.
- File atomics: temporary file then rename to prevent torn writes.

## Versioning and Compatibility

- Trading repo follows semantic versioning in tags (see README Release Workflow).
- Breaking changes to data schemas or file naming will be announced and gated by minor/major bumps.
- Additive schema changes are preferred (extra columns with defaults).

Recommendations for TF_1:

- Pin Trading versions or commit SHAs in your pipelines.
- Add schema validation in TF_1 ingestion to assert expected columns/types.
- Consider contract tests that load a small sample parquet written by Trading to ensure compatibility.

## Example End-to-End Flows

1. Live capture → TF_1 features

- Trading: `record_depth.py` runs for SYM and writes parquet/json.
- TF_1: watches `data/level2/SYM/` for new parquet, triggers feature pipeline.

2. Historical backfill → TF_1 training set

- Trading: `auto_backfill_from_warrior.py --since 30 --max-workers 4 --strict` writes historical parquets and manifest.
- TF_1: reads `backfill_l2_manifest.jsonl` for all entries where `status == WRITE` over the run window; loads parquet for training.

## Test Data and Fixtures

- Trading includes tests using a Fake IB client; TF_1 can reuse or mirror the approach to avoid hard dependency on IB during unit tests.
- For integration tests, prefer a small curated parquet fixture in TF_1 that matches the schema listed above.

## CI/CD and Automation

- Use `Describe All Tools` VS Code task (or `--describe`) to keep CLIs in sync.
- Consider a cross-repo check that ensures `docs/ENVIRONMENT.md` keys are aligned between Trading and TF_1.
- Optional: nightly orchestrator run (dry-run) to detect vendor/API issues early.

## Open Coordination Topics

- Feature definitions that require consistent windows and market hours alignment.
- Handling halts/odd-lot behavior in L2 when present in vendor data.
- Normalization of symbol corporate actions (splits) and historical stitching.
- Back-pressure and storage quotas when running large backfills.

## Points of Contact

- Trading repo owners: see CODEOWNERS or GitHub settings.
- For urgent vendor issues, set `LOG_LEVEL=DEBUG` and attach `backfill_l2_summary.json` and relevant logs.
