# Path & Environment Centralization Migration Log

This document records the migration from hardcoded, platform-specific file paths to centralized configuration variables loaded from `.env` and surfaced through `src/core/config.py`.

## Added/Standardized Environment Keys

| Key                             | Default                     | Purpose                                  |
| ------------------------------- | --------------------------- | ---------------------------------------- |
| ML_BASE_PATH                    | ~/Machine Learning          | Root for data area (`Machine Learning/`) |
| ML_BACKUP_PATH                  | ~/Machine Learning/backups  | Backup mirror tree                       |
| LOGS_PATH                       | ./logs                      | Log output directory                     |
| TEMP_PATH                       | ./temp                      | Temp / scratch files                     |
| CONFIG_PATH                     | ./config                    | Persisted JSON config                    |
| IB_FAILED_STOCKS_FILENAME       | IB Failed Stocks.xlsx       | Excel (failed symbols)                   |
| IB_DOWNLOADABLE_STOCKS_FILENAME | IB Downloadable Stocks.xlsx | Excel (downloadable)                     |
| IB_DOWNLOADED_STOCKS_FILENAME   | IB Downloaded Stocks.xlsx   | Excel (downloaded)                       |
| WARRIOR_TRADES_FILENAME         | WarriorTrading_Trades.xlsx  | Warrior trades list                      |
| TRAIN_LIST_PREFIX               | Train_List-                 | Prefix for training list files           |
| IB_DOWNLOADS_DIRNAME            | IBDownloads                 | Subdir for raw IB files                  |
| LEVEL2_DIRNAME                  | Level2                      | Subdir for L2 data                       |
| REQUEST_CHECKER_BIN             | Files/requestChecker.bin    | Request timing persistence               |
| IB_HOST                         | 127.0.0.1                   | IB connection host                       |
| IB_PORT                         | 4002                        | IB connection port                       |
| IB_CLIENT_ID                    | 1                           | Default client id                        |
| IB_PAPER                        | 1                           | Paper trading flag (1/0)                 |

## Representative Literal Replacements

| Old Literal                               | New Accessor                                      |
| ----------------------------------------- | ------------------------------------------------- |
| "G:/Machine Learning/"                    | cfg.data_paths.base_path / "Machine Learning"     |
| os.path.expanduser("~/Machine Learning/") | ML_BASE_PATH env                                  |
| "./Files/requestChecker.bin"              | cfg.get_special_file("request_checker_bin")       |
| "IB Failed Stocks.xlsx"                   | cfg.get_data_file_path("ib_failed_stocks")        |
| "IB Downloadable Stocks.xlsx"             | cfg.get_data_file_path("ib_downloadable_stocks")  |
| "IB Downloaded Stocks.xlsx"               | cfg.get_data_file_path("ib_downloaded_stocks")    |
| "./Warrior/WarriorTrading_Trades.xlsx"    | cfg.get_data_file_path("warrior_trading_trades")  |
| "Train_List-" + kind + ".xlsx"            | cfg.get_data_file_path("train_list", symbol=kind) |

## Files Updated

- core/config.py (central manager + accessors)
- services/path_service.py
- services/request_manager_service.py
- services/data_persistence_service.py
- services/historical_data/historical_data_service.py
- services/historical_data/download_tracker.py
- services/data_management_service.py
- MasterPy_Trading.py (legacy monolith touchpoints)

## Backward Compatibility

Legacy functions remain; they now defer to the configuration system so existing external scripts continue to operate without immediate changes.

## Verification

All tests pass (`pytest`: 126 tests). Grep confirms active runtime code no longer relies on Windows drive literals for operational paths; remaining occurrences are in migration/demo scripts or backup snapshots.

---

Generated as part of configuration centralization.
