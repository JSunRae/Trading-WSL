# Environment & Configuration

Single authoritative list of environment variables. Defaults sourced from `ConfigManager._env_defaults` plus additional runtime knobs.

## Table

| Key                             | Default                      | Purpose                                   | Used By                    |
| ------------------------------- | ---------------------------- | ----------------------------------------- | -------------------------- |
| ML_BASE_PATH                    | ~/Machine Learning           | Root ML data directory                    | config, data manager       |
| ML_BACKUP_PATH                  | ~/T7 Backup/Machine Learning | Backup mirror for critical files          | backup utilities           |
| LOGS_PATH                       | logs                         | Log file directory                        | logging setup              |
| TEMP_PATH                       | temp                         | Temp workspace (atomic writes, staging)   | backfill, data ops         |
| CONFIG_PATH                     | config                       | Config storage (generated JSON)           | config manager             |
| DATA_PATH_OVERRIDE              | ./data                       | Override base data path (legacy compat)   | data access                |
| FILES_PATH                      | ./Files                      | Legacy files directory                    | legacy loaders             |
| CACHE_PATH                      | ./cache                      | Cache directory                           | performance caching        |
| IB_FAILED_STOCKS_FILENAME       | IB Failed Stocks.xlsx        | Legacy Excel artifact                     | legacy ingestion           |
| IB_DOWNLOADABLE_STOCKS_FILENAME | IB Downloadable Stocks.xlsx  | Legacy Excel artifact                     | legacy ingestion           |
| IB_DOWNLOADED_STOCKS_FILENAME   | IB Downloaded Stocks.xlsx    | Legacy Excel artifact                     | legacy ingestion           |
| WARRIOR_TRADES_FILENAME         | WarriorTrading_Trades.xlsx   | Warrior source trade list                 | warrior task discovery     |
| TRAIN_LIST_PREFIX               | Train_List-                  | Prefix for generated training list Excel  | training utilities         |
| FAILED_STOCKS_CSV               | failed_stocks.csv            | CSV export (derived)                      | legacy reports             |
| DOWNLOADABLE_STOCKS_CSV         | downloadable_stocks.csv      | CSV export (derived)                      | legacy reports             |
| DOWNLOADED_STOCKS_CSV           | downloaded_stocks.csv        | CSV export (derived)                      | legacy reports             |
| REQUEST_CHECKER_BIN             | Files/requestChecker.bin     | Binary request checker path               | legacy tool                |
| LEVEL2_DIRNAME                  | Level2                       | Subdir under ML base for L2 live data     | record_depth, analysis     |
| IB_DOWNLOADS_DIRNAME            | IBDownloads                  | IB historical bar downloads               | download scripts           |
| IB_HOST                         | 127.0.0.1                    | IBKR host (Gateway/TWS)                   | gateway, clients           |
| IB_LIVE_PORT                    | 7496                         | IBKR live trading port                    | ib connection              |
| IB_PAPER_PORT                   | 7497                         | IBKR paper trading port                   | ib connection              |
| IB_GATEWAY_LIVE_PORT            | 4001                         | Headless gateway live port                | headless gateway           |
| IB_GATEWAY_PAPER_PORT           | 4002                         | Headless gateway paper port               | headless gateway           |
| IB_CLIENT_ID                    | 1                            | Explicit client id override               | ib connection              |
| IB_PAPER_TRADING                | true                         | Paper vs live mode flag                   | connection config          |
| DEFAULT_DATA_FORMAT             | parquet                      | Primary on-disk format                    | data manager               |
| BACKUP_FORMAT                   | csv                          | Backup export format                      | backup utilities           |
| EXCEL_ENGINE                    | openpyxl                     | Excel reader/writer engine                | legacy IO                  |
| MAX_WORKERS                     | 4                            | Generic parallel worker cap (non L2)      | misc parallel ops          |
| CHUNK_SIZE                      | 1000                         | Chunk size for batched IO                 | data manager               |
| CACHE_SIZE_MB                   | 512                          | In-memory cache target size               | caching layer              |
| CONNECTION_TIMEOUT              | 30                           | IB connection timeout (s)                 | gateway, requests          |
| RETRY_ATTEMPTS                  | 3                            | Generic retry attempts                    | retry logic                |
| DATABENTO_API_KEY               | (empty)                      | DataBento API key (optional)              | databento service          |
| DATABENTO_ENABLE_BACKFILL       | 0                            | Enable DataBento-powered backfill         | orchestrator, backfill_api |
| DATABENTO_DATASET               | NASDAQ.ITCH                  | Dataset code                              | databento service          |
| DATABENTO_SCHEMA                | mbp-10                       | L2 schema selection                       | databento service          |
| DATABENTO_TZ                    | America/New_York             | Timezone for vendor window parse          | backfill window logic      |
| L2_BACKFILL_WINDOW_ET           | 08:00-11:30                  | ET window for historical slice extraction | backfill_api               |
| L2_BACKFILL_CONCURRENCY         | 2                            | Legacy backfill CLI concurrency           | backfill_l2_from_warrior   |
| L2_MAX_WORKERS                  | 4                            | New orchestrator worker pool size         | auto_backfill_from_warrior |
| L2_TASK_BACKOFF_BASE_MS         | 250                          | Base backoff (ms) for vendor retry        | databento_l2_service       |
| L2_TASK_BACKOFF_MAX_MS          | 2000                         | Max backoff cap (ms)                      | databento_l2_service       |
| SYMBOL_MAPPING_FILE             | config/symbol_mapping.json   | Local symbol -> vendor symbol mapping     | backfill & mapping         |
| LOG_LEVEL                       | INFO                         | Global log level for batch tools          | orchestrators, backfill    |
| FORCE_FAKE_IB                   | 0                            | Force fake IB client (CI/offline)         | ib client resolution       |
| IB_USERNAME                     | (empty)                      | Gateway auth username                     | headless gateway           |
| IB_PASSWORD                     | (empty)                      | Gateway auth password                     | headless gateway           |

## Example .env (Paper Trading)

```env
# Core paths
echo "ML_BASE_PATH=~/Machine Learning" >> .env
ML_BACKUP_PATH=~/T7 Backup/Machine Learning
LOG_LEVEL=INFO

# IB (paper)
IB_HOST=127.0.0.1
IB_PAPER_TRADING=1
IB_CLIENT_ID=7

# DataBento (optional)
DATABENTO_ENABLE_BACKFILL=1
DATABENTO_API_KEY=replace_me

# L2 backfill tuning
L2_MAX_WORKERS=4
L2_TASK_BACKOFF_BASE_MS=250
L2_TASK_BACKOFF_MAX_MS=2000
```

## Example .env (Live - minimal diff)

```env
IB_PAPER_TRADING=0
LOG_LEVEL=INFO
L2_MAX_WORKERS=2
```

## Notes

- Concurrency: `L2_MAX_WORKERS` governs the new orchestrator. Legacy tool still respects `L2_BACKFILL_CONCURRENCY` (fallback when `L2_MAX_WORKERS` unset).
- Backoff: `L2_TASK_BACKOFF_*` provide bounded jittered exponential backoff for vendor rate limiting and transient network issues.
- Logging: `LOG_LEVEL` defaults to INFO; set DEBUG for verbose per-task traces or WARNING to reduce noise in cron.
- Security: Omit `IB_USERNAME` / `IB_PASSWORD` from committed files; use a secrets manager in production.

All variables documented here must stay in sync with the main README and `.env.example`.
