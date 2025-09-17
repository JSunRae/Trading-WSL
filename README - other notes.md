## IB historical data wrapper updates

The async IB wrapper gained two quality-of-life improvements to make targeted historical pulls and downstream orchestration easier:

- Target specific session end: `IBAsync.req_historical_data(..., end_datetime: str | None = None)`
  - Pass an IB-formatted end time (e.g., `"20240905 16:00:00"`) to anchor a 1 D request to a precise session boundary. Defaults to current time when omitted.

- Rich completion + proactive cleanup in `historicalDataEnd`
  - Emits an info log when a request completes: `Historical data complete reqId=... bars=N range=START->END`.
  - Enqueues `(reqId, bars)` into the historical events queue as before.
  - Immediately frees the stored bars and pending request for that `reqId` to reduce memory usage in long sessions.

These changes improve traceability for paced, repeated requests (especially minute/second bars) and help avoid gradual memory growth in long-running jobs.

## Single-symbol/day E2E smoke test (IB bars + DataBento L2)

A lightweight integration test validates the end-to-end path for one `(symbol, trading_day)` from your Warrior list.

- Location: `tests/e2e/test_single_symbol_single_day_e2e.py`
- What it does:
  - Discovers one `(symbol, day)` via `find_warrior_tasks()`.
  - Connects to IB and fetches hourly and 1‑second historical bars for that day (anchored with `end_datetime`).
  - Runs `backfill_l2(symbol, day)` to fetch Level 2 snapshots via DataBento and write `_databento` suffixed parquet (idempotent; atomic write).
  - Emits a comprehensive JSON audit to stdout and saves it under `logs/e2e_single_{SYMBOL}_{YYYY-MM-DD}.json`.
- Outputs captured in the audit:
  - IB connection target (host/port/client_id) from config
  - Hourly/seconds parquet file paths and whether they exist after the run
  - L2 backfill result dict (status/rows/path/error)
  - Before/after "needs" (hourly/seconds/L2) and key env like `L2_BACKFILL_WINDOW_ET`, `DATABENTO_DATASET`, `DATABENTO_SCHEMA`
  - Key folders: Level2 directory for the symbol, IBDownloads, logs
- Preconditions:
  - IB TWS or Gateway is running with API enabled (paper/live per your config). No credentials are read by the test; it uses an already-running API endpoint.
  - Warrior CSV is available at the configured path (see `ML_BASE_PATH` and `WARRIOR_TRADES_FILENAME`).
  - Optional: `DATABENTO_API_KEY` + databento extra installed if you want L2 to write; otherwise the test still passes as long as IB bars exist.
- Behavior:
  - If IB isn’t reachable, the test is skipped.
  - If DataBento is unavailable, L2 result will carry an error, but the test still passes if bars exist (it asserts at least one of hourly/seconds/L2 was produced).

```bash
pytest -q -s tests/e2e/test_single_symbol_single_day_e2e.py
```
