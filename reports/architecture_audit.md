# Architecture Audit (Initial Pass)

## Overview

This document captures an initial automated pass identifying large/complex modules and areas for potential refactor or configuration migration.

## Largest Files (LoC Sample ~25)

See `file_metrics.json` for structured data. Priority candidates for decomposition ( >600 LoC ):

- ib_async_wrapper.py
- order_management_service.py
- ml_performance_monitor.py
- senior_architect_review.py (tool)
- ml_signal_executor.py
- ml_order_management_service.py
- market_data_service.py
- record_depth.py (tool)
- data_persistence_service.py
- stock_split_detection_service.py
- Ib_Manual_Attempt.py (legacy / demo?)

## Observations

- Tools and services mixed in size; some tools exceed 700 LoC (consider splitting into subcommands or packages).
- Legacy experimental scripts (Ib_Manual_Attempt.py) likely candidates for archival or removal.
- Config centralization exists (`core/config.py`) but many port/path literals remain inside tools (e.g., record_depth, setup_ib_gateway) — plan to replace with `get_config()` accessors & env keys.
- Multiple repeated port number explanations across setup & documentation scripts — unify via helper function or constant pulled from config.

## Next Actions (Planned)

1. Standardize `--describe` across remaining tools (warrior_update added). (UPDATE: `record_depth.py` and `verify_setup.py` now compliant.)
2. Introduce shared helper for port description text referencing env-driven values.
3. Extract remaining hardcoded literals (ports, host, directory names) into `core/config.py` accessors where absent.
4. Provide `.env.example` generated from `env_keys.json`.
5. Add validation for path existence & create on startup via ConfigManager (partially present) — extend for cache/files directories.
6. Prepare refactor tickets for top 5 largest service modules (split responsibilities, add tests).

## Status

Initial artifacts created. Further automated smell detection (complexity, duplicate strings) pending.
