# MasterPy_Trading Cleanup Report

## Summary

Initial refactor pass: inserted deprecation shims for path/location helpers and Excel review function, beginning migration toward services.path_service and data.pandas_helpers.

## Final Inventory (post‑cleanup)

Remaining minimal legacy symbols (backward compatibility only):

- (None) – `BarCLS` retired (moved to test shim) and `requestCheckerCLS` removed.

Removed in this final pass:

- `Market_InfoCLS` (replaced by MarketInfoService)
- `requestCheckerCLS` pacing & tracking methods (`SendRequest`, `Sleep_TotalTime`, `appendFailed`, `appendDownloaded`, `appendDownloadable`, etc.)
- `MarketDepthCls`, `TickByTickCls` (migrated earlier to dedicated services / scripts)
- `InitiateTWS` (replaced by `utils.ib_connection_helper.get_ib_connection`)
- Path helpers `IB_Download_Loc`, `IB_Df_Loc`, `IB_L2_Loc`, `IB_Train_Loc`, `IB_Scalar` (all via PathService)
- `SaveExcel_ForReview` (via data manager / pandas helpers)

## Migration Map (final)

| Removed Legacy Symbol                  | Modern Replacement / Location                                                                                                  | Status              |
| -------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------ | ------------------- |
| Market_InfoCLS                         | `src.services.market_info_service.MarketInfo`                                                                                  | ✅ Done             |
| requestCheckerCLS.\* (pacing/tracking) | `src.services.request_manager_service.RequestManagerService` & `src.services.historical_data.download_tracker.DownloadTracker` | ✅ Done             |
| MarketDepthCls                         | `src.services.market_data.depth_service`                                                                                       | ✅ Done             |
| TickByTickCls                          | Modern tick handlers (service layer)                                                                                           | ✅ Done             |
| InitiateTWS                            | `src.utils.ib_connection_helper.get_ib_connection`                                                                             | ✅ Done             |
| IB\_\* path helpers                    | `src.services.path_service.PathService`                                                                                        | ✅ Done             |
| SaveExcel_ForReview                    | `data manager / pandas helpers`                                                                                                | ✅ Done             |
| WarriorList / TrainList loaders        | `DataManager` + `DataLoaderService`                                                                                            | ✅ Done             |
| Historical monolith                    | `HistoricalDataService` + adapter (`requestCheckerCLS.Download_Historical`)                                                    | ✅ Done             |
| BarCLS (pending)                       | `bar_configuration_service` (future)                                                                                           | ⏳ Keep temporarily |

## Size / Metrics

`src/MasterPy_Trading.py` replaced by <50 line deprecation stub (original ~2300 LOC).

## Status

Cleanup complete; deprecation stub will be deleted on 2025-09-30 pending external migration confirmation.

## Update: L2 Backfill API Extraction

The historical L2 backfill logic was centralized into `services.market_data.backfill_api.backfill_l2` and the CLI tool now delegates per-task execution to this API. Legacy `WarriorList` accessor issues a `DeprecationWarning`; a usage map was added at `reports/usage_map_backfill.json` to track remaining legacy touch points.

# MasterPy_Trading.py Cleanup Report

## Overview

This report documents the removal of deprecated/legacy functions from `src/MasterPy_Trading.py` and the rewiring of all remaining references to modern implementations.

## Analysis Performed

### Current MasterPy_Trading.py Inventory

#### Classes Found:

- `BarCLS` - Bar configuration and timing logic
- `Market_InfoCLS` - Market info wrapper (deprecated - redirects to MarketInfo service)
- `requestCheckerCLS` - IB request management and download tracking (mostly deprecated)
- `MarketDepthCls` - Level 2 market depth recording
- `TickByTickCls` - Tick-by-tick data processing

#### Functions Found:

- `_to_timestamp_or_none()` - Utility function
- `_date_key_str()` - Utility function
- `InitiateTWS()` - IB connection initialization
- `Initiate_Auto_Reconnect()` - Auto-reconnection logic
- `WarriorList()` - Load/save warrior trading data
- `TrainList_LoadSave()` - Load/save ML training lists
- `Stock_Downloads_Load()` - Download historical data
- `IB_Download_Loc()` - File path generation (deprecated)
- `IB_Df_Loc()` - DataFrame path generation (deprecated)
- `IB_L2_Loc()` - Level 2 data path generation (deprecated)
- `IB_Train_Loc()` - Training data path generation (deprecated)
- `IB_Scalar()` - Scalar loading (deprecated)
- `SaveExcel_ForReview()` - Excel export utility

### Files Using MasterPy_Trading:

1. `src/ib_Main.py` - Uses `MPT.MarketDepthCls`, `MPT.InitiateTWS`
2. `src/ib_Trader.py` - Uses `MPT.InitiateTWS`
3. `src/ib_Warror_dl.py` - Uses `MPT.InitiateTWS`
4. `src/tools/maintenance/update_data.py` - Uses `MPT.InitiateTWS`

### Migration Map: Legacy → Modern

| Legacy Symbol                          | Target Module                                                | Target Symbol           | Status       |
| -------------------------------------- | ------------------------------------------------------------ | ----------------------- | ------------ |
| `requestCheckerCLS.appendFailed`       | `src.services.historical_data.DownloadTracker`               | `mark_failed`           | ✅ Available |
| `requestCheckerCLS.appendDownloaded`   | `src.services.historical_data.DownloadTracker`               | `mark_downloaded`       | ✅ Available |
| `requestCheckerCLS.appendDownloadable` | `src.services.historical_data.DownloadTracker`               | `mark_downloadable`     | ✅ Available |
| `requestCheckerCLS.is_failed`          | `src.services.historical_data.DownloadTracker`               | `is_failed`             | ✅ Available |
| `requestCheckerCLS.Download_Exists`    | `src.services.historical_data.DownloadTracker`               | `is_downloaded`         | ✅ Available |
| `requestCheckerCLS.SendRequest`        | `src.services.request_manager_service.RequestManagerService` | `send_request`          | ✅ Available |
| `InitiateTWS`                          | `src.infra.ib_client`                                        | `get_ib_connection`     | ✅ Available |
| `IB_Download_Loc`                      | `src.services.path_service`                                  | `IB_Download_Loc`       | ✅ Available |
| `IB_Df_Loc`                            | `src.services.path_service`                                  | `IB_Df_Loc`             | ✅ Available |
| `IB_L2_Loc`                            | `src.services.path_service`                                  | `IB_L2_Loc`             | ✅ Available |
| `SaveExcel_ForReview`                  | `src.data.pandas_helpers`                                    | `save_excel_for_review` | 🔄 To Create |
| `MarketDepthCls`                       | `src.tools.record_depth`                                     | Modern depth recording  | 🔄 Migrate   |
| `TickByTickCls`                        | `src.infra.ib_requests`                                      | Modern tick-by-tick     | 🔄 Migrate   |

## Plan

### Phase 1: Create Missing Modern Components

1. **Create `src/data/pandas_helpers.py` enhancement** for Excel export
2. **Create modern depth recorder wrapper** in `src/services/market_data/`
3. **Create modern tick-by-tick wrapper** in `src/services/market_data/`

### Phase 2: Rewire External References

1. **Update `src/ib_Main.py`**:
   - Replace `MPT.InitiateTWS` → `from src.infra.ib_client import get_ib_connection`
   - Replace `MPT.MarketDepthCls` → modern market depth service

2. **Update `src/ib_Trader.py`**:
   - Replace `MPT.InitiateTWS` → `from src.infra.ib_client import get_ib_connection`

3. **Update `src/ib_Warror_dl.py`**:
   - Replace `MPT.InitiateTWS` → `from src.infra.ib_client import get_ib_connection`

4. **Update `src/tools/maintenance/update_data.py`**:
   - Replace `MPT.InitiateTWS` → `from src.infra.ib_client import get_ib_connection`

### Phase 3: Clean MasterPy_Trading.py

1. **Remove deprecated classes/functions**:
   - Remove `requestCheckerCLS` (replaced by modern services)
   - Remove path generation functions (replaced by path_service)
   - Remove `Market_InfoCLS` (already wrapped)

2. **Keep with deprecation warnings**:
   - `BarCLS` (still used, add deprecation warning)
   - `InitiateTWS` (add shim with deprecation warning)
   - Core utility functions if still needed

3. **Migrate to services**:
   - `MarketDepthCls` → `src/services/market_data/depth_service.py`
   - `TickByTickCls` → `src/services/market_data/tick_service.py`

## Acceptance Criteria

- [ ] All external references rewired to modern implementations
- [ ] No failing tests
- [ ] No new linter/type errors
- [ ] Legacy code removed or shimmed with deprecation warnings
- [ ] Migration documented with removal timeline

## Next Steps

1. Start with Phase 1 - create missing modern components
2. Execute Phase 2 - rewire external references
3. Complete Phase 3 - clean the main file
4. Verify all tests pass and no import cycles exist
