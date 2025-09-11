This folder contains small, source-controlled test fixtures used by unit tests.

Notes:

- We store a tiny canonical L2 parquet sample named `l2_fixture.parquet` to validate schema adapters and round-trip behavior.
- Keep it tiny (< 5KB) to avoid repository bloat.
- Update only when the canonical schema changes.
