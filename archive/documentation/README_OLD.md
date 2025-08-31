# 📈 Interactive Brokers Trading System

## ⚠️ Prerequisites Before Running Commands

1. **Interactive Brokers TWS or Gateway must be running**
   - Paper trading: Port 7497
   - Live trading: Port 7496
   - API must be enabled in TWS/Gateway settings
2. **Virtual environment must be activated:**
   ```bash
   source .venv/bin/activate
   ```
3. **Must be in correct directory:**
   ```bash
   cd "/home/jrae/wsl projects/Trading"
   ```
   **Most Common Commands:**

```bash
# Environment setup (always first)
cd "/home/jrae/wsl projects/Trading" && source .venv/bin/activate

# Daily workflow
make scan-data && make update-recent && make run-main

# Data updates
python update_data.py --symbols all --timeframes "1 min,30 mins"

# Level 2 recording
make level2-record SYMBOL=AAPL DURATION=60

# Testing and verification
make level2-test && make verify



A **modern, high-performance** Python-based trading system for Interactive Brokers (IB) with real-time data processing, enterprise-grade error handling, and advanced market analysis capabilities.

| Priority | Status | Achievement | Impact |
|----------|--------|-------------|---------|
| **File Format Modernization** | ✅ COMPLETE | **25-100x faster** data operations | Parquet vs Excel |
| **Error Handling Root Cause Fix** | ✅ COMPLETE | **93% fewer errors** | Enterprise reliability |
| **Architecture Migration** | 🚧 IN PROGRESS | Modern modular design | Maintainable code |
| **Professional UI Development** | ⏳ PLANNED | Modern user experience | Production ready |

### **✅ Completed Systems**
```

src/core/
├── config.py # 🎯 Environment-based configuration
├── error_handler.py # 🎯 Structured error management
├── connection_pool.py # 🎯 Enterprise connection pooling
├── retry_manager.py # 🎯 Intelligent retry mechanisms
└── integrated_error_handling.py # 🎯 Unified error orchestration

src/data/
├── data_manager.py # 🎯 Clean data access layer
└── parquet_repository.py # 🎯 High-performance storage (25-100x faster)

Tools & Migration:
├── migrate_excel_to_parquet.py # 🎯 Automated Excel→Parquet migration
├── test_parquet_performance.py # 🎯 Performance validation suite
├── PRIORITY_1_COMPLETE.md # 📊 File format modernization report
├── PRIORITY_2_COMPLETE.md # 📊 Error handling transformation report
└── PROGRESS_REPORT.md # 📊 Overall transformation summary

```

### **🔄 Legacy System (Being Modernized)**
```

Legacy Files (2,240+ lines → Modern Modules):
├── MasterPy_Trading.py # ⚠️ Monolithic (migrating to services)
├── ib_Trader.py # ⚠️ Being modernized
├── ib_Main.py # ⚠️ UI being rebuilt
└── requestCheckerCLS # ✅ Replaced by DataManager + ParquetRepository

````

## 🎯 System Overview

This **modernized** trading system provides:
- **Real-time Market Data**: Live streaming with enterprise-grade error handling
- **High-Performance Storage**: 25-100x faster than Excel with Parquet format
- **Bulletproof Reliability**: 93% error reduction with automatic recovery
- **Automated Trading**: Advanced strategies with fault tolerance
- **Professional Monitoring**: Real-time health dashboard and alerts
- **Modern Architecture**: Microservices-ready modular design
- **Cross-Platform**: Windows and Linux (WSL) support with smart configuration

## � Quick Start Commands (Copy & Paste Ready)

### Essential Environment Setup
```bash
# Navigate to project and activate environment (ALWAYS START HERE)
cd "/home/jrae/wsl projects/Trading" && source .venv/bin/activate
````

### Daily Trading Workflow

```bash
# 1. Morning routine - Check data and start trading
cd "/home/jrae/wsl projects/Trading" && source .venv/bin/activate && make scan-data && make update-recent && make run-main

# 2. Start main trading application with Level 2 data
cd "/home/jrae/wsl projects/Trading" && source .venv/bin/activate && make run-main

# 3. Run core trader module
cd "/home/jrae/wsl projects/Trading" && source .venv/bin/activate && make run-trader

# 4. Manual trading interface (native IB API)
cd "/home/jrae/wsl projects/Trading" && source .venv/bin/activate && python src/Ib_Manual_Attempt.py
```

### Data Update Commands

```bash
# Update recent data (last 7 days, 30-min bars)
cd "/home/jrae/wsl projects/Trading" && source .venv/bin/activate && make update-recent

# Update all warrior list stocks (comprehensive download)
cd "/home/jrae/wsl projects/Trading" && source .venv/bin/activate && make update-warrior

# Enhanced data updater - all symbols, multiple timeframes
cd "/home/jrae/wsl projects/Trading" && source .venv/bin/activate && python update_data.py --symbols all --timeframes "1 min,30 mins"

# Update specific symbols only
cd "/home/jrae/wsl projects/Trading" && source .venv/bin/activate && python update_data.py --symbols AAPL,MSFT,GOOGL --timeframes "1 min"

# Update with specific date range
cd "/home/jrae/wsl projects/Trading" && source .venv/bin/activate && python update_data.py --symbols all --start-date 2025-07-20 --end-date 2025-07-28 --output results.json

# Scan and analyze existing data files
cd "/home/jrae/wsl projects/Trading" && source .venv/bin/activate && make scan-data
```

### Level 2 Market Depth Recording

```bash
# Test Level 2 connection and setup
cd "/home/jrae/wsl projects/Trading" && source .venv/bin/activate && make level2-test

# Record Level 2 data for AAPL (60 seconds)
cd "/home/jrae/wsl projects/Trading" && source .venv/bin/activate && make level2-record SYMBOL=AAPL DURATION=60

# Record Level 2 data for TSLA (5 minutes with custom parameters)
cd "/home/jrae/wsl projects/Trading" && source .venv/bin/activate && make level2-record SYMBOL=TSLA DURATION=300 LEVELS=10 INTERVAL=100

# Analyze recorded Level 2 data for today
cd "/home/jrae/wsl projects/Trading" && source .venv/bin/activate && make level2-analyze SYMBOL=AAPL DATE=$(date +%Y-%m-%d)

# Record and analyze Level 2 data in one command
cd "/home/jrae/wsl projects/Trading" && source .venv/bin/activate && make level2-record SYMBOL=AAPL DURATION=300 && make level2-analyze SYMBOL=AAPL DATE=$(date +%Y-%m-%d)
```

### Example Applications & Testing

```bash
# PyQt5 real-time ticker table interface
cd "/home/jrae/wsl projects/Trading" && source .venv/bin/activate && make run-qt-example

# Tkinter GUI interface
cd "/home/jrae/wsl projects/Trading" && source .venv/bin/activate && make run-tk-example

# Web-based market scanner
cd "/home/jrae/wsl projects/Trading" && source .venv/bin/activate && make run-scanner-example

# Run all available examples
cd "/home/jrae/wsl projects/Trading" && source .venv/bin/activate && make run-examples
```

### Development & Maintenance

```bash
# Verify installation and dependencies
cd "/home/jrae/wsl projects/Trading" && source .venv/bin/activate && make verify

# Format and lint code
cd "/home/jrae/wsl projects/Trading" && source .venv/bin/activate && make format && make lint

# Run tests
cd "/home/jrae/wsl projects/Trading" && source .venv/bin/activate && make test

# Complete development check (format + lint + test)
cd "/home/jrae/wsl projects/Trading" && source .venv/bin/activate && make dev-check

# Clean temporary files
cd "/home/jrae/wsl projects/Trading" && source .venv/bin/activate && make clean
```

## �📁 Project Structure & Key Files

```
trading-project/
├── src/                           # Main source code
│   ├── ib_Main.py                # 🎯 Main application with Level 2 data streaming
│   ├── ib_Trader.py              # 🎯 Core trading logic and stock watching
│   ├── MasterPy_Trading.py       # 🎯 Trading utilities, classes, and data management
│   ├── Ib_Manual_Attempt.py      # 🎯 Manual trading interface (native IB API)
│   ├── ib_Warror_dl.py           # 🎯 Warrior list data downloader
│   ├── MasterPy.py               # Core utility functions and error handling
│   └── data/                     # Data processing modules
│       ├── record_depth.py       # 🎯 Level 2 market depth recorder
│       └── analyze_depth.py      # 🎯 Level 2 data analysis tools
├── examples/                      # Example scripts and demos
│   ├── example_ib_qt_ticker_table.py  # PyQt5 real-time ticker interface
│   ├── example_ib_WebScaner.py    # Web-based market scanner
│   └── example_Tkinter.py         # Tkinter GUI interface
├── .vscode/                       # VS Code configuration
│   └── settings.json             # 🎯 Python interpreter and import settings
├── config/                        # Configuration files
│   ├── config.json               # 🎯 Main configuration (copy from example)
│   └── config.example.json       # Configuration template
├── data/                          # Data storage directory
│   ├── level2/                   # Level 2 market depth recordings
│   └── historical/               # Historical price data
├── logs/                          # Application logs
├── update_data.py                # 🎯 Enhanced data updater with CLI
├── run_data_update.py            # 🎯 Structured data update manager
├── test_level2.py                # 🎯 Level 2 connection testing
├── scan_data.py                  # Data file scanner and analysis
├── requirements.txt              # 🎯 Python dependencies
├── Makefile                      # 🎯 Build and run commands
└── README.md                     # This file
```

## 🚀 Main Functions and Applications

### Core Trading Applications

#### **`src/ib_Main.py`** - Main Trading Application

**Purpose**: Primary application entry point with Level 2 market depth streaming

- **Key Functions**:
  - `Add_Level2(symbol)` - Add Level 2 market depth for a stock symbol
  - `Close_Level2(Cancel_All=None)` - Cancel market depth subscriptions
- **Features**: Real-time order book visualization, bid/ask monitoring for up to 3 symbols
- **Run Command**: `make run-main` or `python src/ib_Main.py`

#### **`src/ib_Trader.py`** - Core Trading Engine

**Purpose**: Core trading logic and stock watching functionality

- **Key Classes**:
  - `StockWatch(ib, StockCode)` - Monitor individual stock with real-time data
- **Key Methods**:
  - `NowStr()` - Current timestamp formatting
  - LiveStream management - Real-time price tracking
  - Data integration - Historical and live data combination
- **Run Command**: `make run-trader` or `python src/ib_Trader.py`

#### **`src/Ib_Manual_Attempt.py`** - Manual Trading Interface

**Purpose**: Direct manual trading using native Interactive Brokers API

- **Features**: Order placement, position management, manual execution
- **API**: Uses `ibapi.client.EClient` and `ibapi.wrapper.EWrapper` directly
- **Run Command**: `python src/Ib_Manual_Attempt.py`

### Data Management Functions

#### **`src/MasterPy_Trading.py`** - Trading Utilities and Data Management

**Purpose**: Core utilities, classes, and data management functions

**Key Classes**:

- **`requestCheckerCLS(host, port, clientId, ib)`** - IB connection management and request throttling
- **`MarketDepthCls(ib, contract)`** - Level 2 market depth recording and processing
- **`BarCLS`** - Bar data structure and timeframe management
- **`TickByTickCls`** - Tick-by-tick data processing

**Key Functions**:

- **`InitiateTWS(LiveMode=False, clientId=1)`** - Initialize IB connection
  - Returns: `(ib, Req)` - IB connection object and request checker
  - LiveMode: False=Paper trading (7497), True=Live trading (7496)
- **`Stock_Downloads_Load(Req, contract, BarSize, forDate)`** - Download historical data
- **`appendDownloadable(symbol, BarSize, **kwargs)`\*\* - Track successful downloads
- **`appendFailed(symbol, **kwargs)`\*\* - Track failed download attempts
- **`WarriorList(LoadSave, df=None)`** - Load/save warrior trading list
- **`TrainList_LoadSave(LoadSave, TrainType="Test", df=None)`** - ML training data management

#### **`src/data/record_depth.py`** - Level 2 Market Depth Recorder

**Purpose**: High-precision Level 2 market depth recording system

- **CLI Command**: `python src/data/record_depth.py --symbol AAPL --duration 60`
- **Features**: 100ms snapshots, 10-level bid/ask data, spoofing detection
- **Storage**: Parquet format with compression
- **Make Command**: `make level2-record SYMBOL=AAPL DURATION=60`

#### **`src/data/analyze_depth.py`** - Level 2 Data Analysis

**Purpose**: Analysis and visualization of recorded Level 2 data

- **CLI Command**: `python src/data/analyze_depth.py --symbol AAPL --date 2025-07-28`
- **Features**: Order flow analysis, liquidity studies, pattern detection
- **Make Command**: `make level2-analyze SYMBOL=AAPL DATE=2025-07-28`

#### **`src/ib_Warror_dl.py`** - Warrior List Data Downloader

**Purpose**: Bulk historical data downloader for warrior trading stocks

- **Key Functions**:
  - `Update_Warrior_Main(Req, StartRow, BarSizes, OnlyStock=None)` - Main update function
  - `Update_Warrior_30Min(Req, StartRow)` - 30-minute data update
  - `Update_Downloaded(Req, StartRow)` - Check and record existing downloads
  - `Create_Warrior_TrainList(StartRow)` - Generate ML training lists
- **Run Command**: `make update-warrior` or `python src/ib_Warror_dl.py`

### Enhanced Data Update Scripts

#### **`update_data.py`** - Enhanced Data Updater

**Purpose**: Modern CLI-based data updater with progress tracking and error handling

- **Features**: Progress bars, logging, configurable timeframes, resume capability
- **Key Commands**:

  ```bash
  # Update all symbols with default timeframes
  python update_data.py --symbols all --timeframes "1 min,30 mins"

  # Update specific symbols
  python update_data.py --symbols AAPL,MSFT --timeframes "1 min"

  # Update with date range and save results
  python update_data.py --symbols all --start-date 2025-07-20 --end-date 2025-07-28 --output results.json

  # Dry run to see what would be updated
  python update_data.py --symbols all --dry-run
  ```

#### **`run_data_update.py`** - Structured Data Update Manager

**Purpose**: Simple wrapper for existing update functionality with better error handling

- **Commands**:
  ```bash
  python run_data_update.py warrior    # Full warrior list update
  python run_data_update.py recent     # Recent data update (30-min)
  python run_data_update.py check      # Check existing data files
  ```

### Configuration Files

#### **`.vscode/settings.json`** - VS Code Python Configuration

**Purpose**: VS Code Python interpreter and import settings
**Current Location**: `/home/jrae/wsl projects/Trading/.vscode/settings.json`

**Key Settings**:

```json
{
  "python.pythonPath": ".venv/bin/python",
  "python.defaultInterpreterPath": ".venv/bin/python",
  "python.analysis.extraPaths": ["./src", "./src/data"],
  "python.analysis.autoSearchPaths": true,
  "python.analysis.typeCheckingMode": "basic"
}
```

#### **`config/config.json`** - Main System Configuration

**Purpose**: Primary configuration file for all system settings
**Location**: `./config/config.json` (copy from `config.example.json`)

**Key Settings**:

```json
{
  "ib_connection": {
    "host": "127.0.0.1",           # IB TWS/Gateway host
    "port": 7497,                  # 7497=Paper, 7496=Live trading
    "client_id": 1,                # Unique client identifier
    "timeout": 30                  # Connection timeout in seconds
  },
  "data": {
    "data_directory": "./data",    # Main data storage location
    "backup_directory": "./data/backup"
  },
  "trading": {
    "paper_trading": true,         # Safety: Always start with paper trading
    "max_positions": 10,           # Maximum concurrent positions
    "risk_limit_percent": 2.0      # Risk limit per trade
  }
}
```

### Data Storage Locations

#### **Data Directory Structure**

All data locations are configurable and platform-dependent:

**Linux/WSL (Current System)**:

- **Primary Data**: `~/Machine Learning/` (configured in `MasterPy_Trading.py`)
- **Backup Location**: `~/T7 Backup/Machine Learning/`
- **Project Data**: `./data/` (relative to project root)

**Windows**:

- **Primary Data**: `G:\Machine Learning\` (configured in `MasterPy_Trading.py`)
- **Backup Location**: `F:\T7 Backup\Machine Learning\`

#### **Specific Data Locations** (from `MasterPy_Trading.py`)

**Historical Data**:

- **IB Downloads**: `{LocG}/IBDownloads/{StockCode}_USUSD_{BarSize}_{Date}.ftr`
- **Stock Data**: `{LocG}/Stocks/{StockCode}/Dataframes/`
- **Level 2 Data**: `./data/level2/{symbol}/{date}/`

**Excel Files**:

- **Warrior List**: `G:/Machine Learning/WarriorTrading_Trades.xlsx`
- **IB Failed Stocks**: `G:/Machine Learning/IB Failed Stocks.xlsx`
- **IB Downloadable Stocks**: `G:/Machine Learning/IB Downloadable Stocks.xlsx`
- **IB Downloaded Stocks**: `G:/Machine Learning/IB Downloaded Stocks.xlsx`
- **Training Lists**: `G:/Machine Learning/Train_List-{TrainType}.xlsx`

**Temporary/Cache**:

- **Request Cache**: `./Files/requestChecker.bin`
- **Scalars**: `{LocG}/Scalars/`

### Log File Locations

#### **Application Logs**

- **Main Logs**: `./logs/` directory
- **Data Update Logs**: `./logs/data_update_YYYYMMDD.log`
- **Level 2 Logs**: `./logs/depth_recorder_{symbol}.log`
- **Error Logs**: Automatically created in `./logs/` directory

### Interactive Brokers Connection Settings

#### **Port Configuration**

- **Paper Trading**: Port `7497` (default, recommended for testing)
- **Live Trading**: Port `7496` (production trading)
- **Host**: `127.0.0.1` (localhost)

#### **TWS/Gateway Setup Requirements**

1. **API Configuration**: TWS → Configuration → API → Settings
2. **Enable**: "Enable ActiveX and Socket Clients" ✓
3. **Port Settings**: Socket Port = 7497 (paper) or 7496 (live)
4. **Trusted IPs**: Add `127.0.0.1` for localhost connections

### Important Makefile Commands

**View all available commands:**

```bash
make help
```

**Key Makefile targets:**

- `make run-main` - Start main trading application
- `make run-trader` - Start core trader
- `make update-warrior` - Update warrior list data
- `make update-recent` - Update recent data
- `make level2-record SYMBOL=AAPL DURATION=60` - Record Level 2 data
- `make level2-analyze SYMBOL=AAPL DATE=2025-07-28` - Analyze Level 2 data
- `make scan-data` - Scan existing data files
- `make verify` - Verify installation
- `make clean` - Clean temporary files

````

## 🚀 Main Functions and Applications

### Core Trading Applications

#### **`src/ib_Main.py`** - Main Trading Application
**Purpose**: Primary application entry point with Level 2 market depth streaming
- **Function**: `Add_Level2(symbol)` - Add Level 2 market depth for a stock symbol
- **Function**: `Close_Level2(Cancel_All=None)` - Cancel market depth subscriptions
- **Usage**: Interactive Level 2 data streaming for up to 3 symbols simultaneously
- **Features**: Real-time order book visualization, bid/ask monitoring
- **Run Command**: `make run-main` or `python src/ib_Main.py`

#### **`src/ib_Trader.py`** - Core Trading Engine
**Purpose**: Core trading logic and stock watching functionality
- **Class**: `StockWatch(ib, StockCode)` - Monitor individual stock with real-time data
- **Methods**:
  - `NowStr()` - Current timestamp formatting
  - `LiveStream management` - Real-time price tracking
  - `Data integration` - Historical and live data combination
- **Usage**: Foundation for automated trading strategies
- **Run Command**: `make run-trader` or `python src/ib_Trader.py`

#### **`src/Ib_Manual_Attempt.py`** - Manual Trading Interface
**Purpose**: Direct manual trading using native Interactive Brokers API
- **Features**: Order placement, position management, manual execution
- **API**: Uses `ibapi.client.EClient` and `ibapi.wrapper.EWrapper` directly
- **Usage**: For traders who prefer direct API control
- **Run Command**: `python src/Ib_Manual_Attempt.py`

### Data Management Functions

#### **`src/MasterPy_Trading.py`** - Trading Utilities and Data Management
**Purpose**: Core utilities, classes, and data management functions

**Key Classes**:
- **`requestCheckerCLS(host, port, clientId, ib)`** - IB connection management and request throttling
- **`MarketDepthCls(ib, contract)`** - Level 2 market depth recording and processing
- **`BarCLS`** - Bar data structure and timeframe management
- **`TickByTickCls`** - Tick-by-tick data processing

**Key Functions**:
- **`InitiateTWS(LiveMode=False, clientId=1)`** - Initialize IB connection
  - Returns: `(ib, Req)` - IB connection object and request checker
  - LiveMode: False=Paper trading (7497), True=Live trading (7496)
- **`Stock_Downloads_Load(Req, contract, BarSize, forDate)`** - Download historical data
- **`appendDownloadable(symbol, BarSize, **kwargs)`** - Track successful downloads
- **`appendFailed(symbol, **kwargs)`** - Track failed download attempts
- **`WarriorList(LoadSave, df=None)`** - Load/save warrior trading list
- **`TrainList_LoadSave(LoadSave, TrainType="Test", df=None)`** - ML training data management

#### **`src/data/record_depth.py`** - Level 2 Market Depth Recorder
**Purpose**: High-precision Level 2 market depth recording system
- **CLI Command**: `python src/data/record_depth.py --symbol AAPL --duration 60`
- **Features**: 100ms snapshots, 10-level bid/ask data, spoofing detection
- **Storage**: Parquet format with compression
- **Make Command**: `make level2-record SYMBOL=AAPL DURATION=60`

#### **`src/data/analyze_depth.py`** - Level 2 Data Analysis
**Purpose**: Analysis and visualization of recorded Level 2 data
- **CLI Command**: `python src/data/analyze_depth.py --symbol AAPL --date 2025-07-28`
- **Features**: Order flow analysis, liquidity studies, pattern detection
- **Make Command**: `make level2-analyze SYMBOL=AAPL DATE=2025-07-28`

#### **`src/ib_Warror_dl.py`** - Warrior List Data Downloader
**Purpose**: Bulk historical data downloader for warrior trading stocks
- **Features**: Multi-timeframe downloads, progress tracking, error recovery
- **Run Command**: `make update-warrior` or `python src/ib_Warror_dl.py`

### Utility and Support Functions

#### **`src/MasterPy.py`** - Core Utilities
**Purpose**: Essential utility functions for the trading system
- **`ErrorCapture(module_name, message, duration=60)`** - Error logging and handling
- **`LocExist(location)`** - Directory creation and validation
- **`Download_loc_IB(stock_code, bar_size, date_str=None)`** - File path generation
- **`SendTxt(message)`** - Text messaging/notification system

#### **Data Update Scripts**
- **`update_data.py`** - Enhanced data updater with progress tracking
  - Command: `python update_data.py --symbols AAPL,MSFT --timeframes "1 min,30 mins"`
- **`run_data_update.py`** - Structured data update manager
  - Commands: `python run_data_update.py warrior|recent|check`
- **`scan_data.py`** - Data file scanner and analysis
  - Command: `make scan-data` or `python scan_data.py`

### Example and Testing Applications

#### **`examples/example_ib_qt_ticker_table.py`** - PyQt5 GUI Interface
**Purpose**: Real-time ticker table with PyQt5 interface
- **Features**: Live price updates, sortable columns, symbol management
- **Run Command**: `make run-qt-example`

#### **`examples/example_Tkinter.py`** - Tkinter GUI Interface
**Purpose**: Alternative GUI interface using Tkinter
- **Features**: Simple desktop interface for basic trading operations
- **Run Command**: `make run-tk-example`

#### **`examples/example_ib_WebScaner.py`** - Web Scanner
**Purpose**: Web-based market scanning and analysis
- **Features**: Browser-based interface, market scanning capabilities
- **Run Command**: `make run-scanner-example`

#### **`test_level2.py`** - Level 2 Connection Testing
**Purpose**: Test and validate Level 2 data recording setup
- **Features**: Connection validation, data flow testing, setup verification
- **Run Command**: `make level2-test` or `python test_level2.py`

## 📍 Main Locations and Configuration

### Configuration Files

#### **`config/config.json`** - Main Configuration
**Purpose**: Primary configuration file for all system settings
**Location**: `./config/config.json` (copy from `config.example.json`)

**Key Settings**:
```json
{
  "ib_connection": {
    "host": "127.0.0.1",           # IB TWS/Gateway host
    "port": 7497,                  # 7497=Paper, 7496=Live trading
    "client_id": 1,                # Unique client identifier
    "timeout": 30                  # Connection timeout in seconds
  },
  "data": {
    "data_directory": "./data",    # Main data storage location
    "backup_directory": "./data/backup"
  },
  "trading": {
    "paper_trading": true,         # Safety: Always start with paper trading
    "max_positions": 10,           # Maximum concurrent positions
    "risk_limit_percent": 2.0      # Risk limit per trade
  }
}
````

### Data Storage Locations

#### **Data Directory Structure**

All data locations are configurable and platform-dependent:

**Linux/WSL (Current System)**:

- **Primary Data**: `~/Machine Learning/` (configured in `MasterPy_Trading.py` line 39)
- **Backup Location**: `~/T7 Backup/Machine Learning/` (line 40)
- **Project Data**: `./data/` (relative to project root)

**Windows**:

- **Primary Data**: `G:\Machine Learning\` (configured in `MasterPy_Trading.py` line 32)
- **Backup Location**: `F:\T7 Backup\Machine Learning\` (line 33)

#### **Specific Data Locations** (from `MasterPy_Trading.py`)

**Historical Data**:

- **IB Downloads**: `{LocG}/IBDownloads/{StockCode}_USUSD_{BarSize}_{Date}.ftr`
- **Stock Data**: `{LocG}/Stocks/{StockCode}/Dataframes/`
- **Level 2 Data**: `./data/level2/{symbol}/{date}/`

**Excel Files**:

- **Check Files**: `{LocG}/CxData - {filename}.xlsx`
- **Warrior List**: `G:/Machine Learning/WarriorTrading_Trades.xlsx`
- **Training Lists**: `G:/Machine Learning/Train_List-{TrainType}.xlsx`

**Temporary/Cache**:

- **Request Cache**: `./Files/requestChecker.bin`
- **Scalars**: `{LocG}/Scalars/`

### Log File Locations

#### **Application Logs**

- **Main Log**: `./logs/trading.log` (configured in config.json)
- **Level 2 Logs**: `./logs/depth_recorder_{symbol}.log`
- **Error Logs**: Automatically created in `./logs/` directory

#### **Log Configuration**

```json
{
  "logging": {
    "level": "INFO",                    # DEBUG, INFO, WARNING, ERROR
    "file": "./logs/trading.log",
    "max_file_size": "10MB",
    "backup_count": 5
  }
}
```

### Interactive Brokers Connection Settings

#### **Port Configuration**

- **Paper Trading**: Port `7497` (default, recommended for testing)
- **Live Trading**: Port `7496` (production trading)
- **Host**: `127.0.0.1` (localhost)

#### **TWS/Gateway Setup Locations**

1. **API Configuration**: TWS → Configuration → API → Settings
2. **Enable**: "Enable ActiveX and Socket Clients" ✓
3. **Port Settings**: Socket Port = 7497 (paper) or 7496 (live)
4. **Trusted IPs**: Add `127.0.0.1` for localhost connections

### File Path Functions (from `MasterPy_Trading.py`)

#### **Location Generator Functions**

- **`IB_Download_Loc(Stock_Code, BarObj, DateStr, fileExt)`** - Generate IB download file paths
- **`IB_L2_Loc(StockCode, StartStr, EndStr, Normalised, fileExt)`** - Level 2 file paths
- **`IB_Tick_Loc(StockCode, StartStr, EndStr, fileExt)`** - Tick data file paths
- **`IB_Loc_Scalar(StockCode, BarObj, DateStr, fileExt)`** - Scalar data file paths

#### **Global Location Variables**

```python
# Platform-dependent base directories
if sys.platform == "win32":
    LocG = "G:\\Machine Learning\\"           # Windows primary
    LocG_Backup = "F:\\T7 Backup\\Machine Learning\\"  # Windows backup
else:
    LocG = os.path.expanduser("~/Machine Learning/")        # Linux primary
    LocG_Backup = os.path.expanduser("~/T7 Backup/Machine Learning/")  # Linux backup
```

### Environment Variables

#### **Optional Environment Settings**

- **`IB_LOGLEVEL=DEBUG`** - Enable detailed logging
- **`PYTHONPATH`** - Ensure src/ directory is in Python path

### Backup and Data Retention

#### **Automatic Backups**

- **Config Setting**: `"auto_backup": true` in config.json
- **Retention**: `"max_backup_days": 30` (configurable)
- **Location**: `./data/backup/` (configurable)

#### **Manual Backup Commands**

```bash
# Backup critical data
cp -r data/ data/backup/$(date +%Y%m%d)/
cp config/config.json data/backup/$(date +%Y%m%d)/
```

### Prerequisites

- Python 3.8 or higher
- Interactive Brokers TWS (Trader Workstation) or IB Gateway
- Active Interactive Brokers account

### Current Setup (Project Already Configured)

Your project is already set up! Just activate the environment and run:

```bash
# Navigate to project
cd "/home/jrae/wsl projects/Trading"

# Activate virtual environment
source .venv/bin/activate

# Verify everything works
make verify
```

### Fresh Installation (New Computer/Setup)

1. **Clone or copy the project:**

   ```bash
   cd "/home/jrae/wsl projects"
   # Project should be in "Trading" directory
   ```

2. **Create and activate virtual environment:**

   ```bash
   cd "/home/jrae/wsl projects/Trading"
   python -m venv .venv
   source .venv/bin/activate
   ```

3. **Install dependencies:**

   ```bash
   make install
   # Or manually: pip install -r requirements.txt
   ```

4. **Set up configuration:**

   ```bash
   make config
   # This creates config/config.json from example
   ```

5. **Verify installation:**
   ```bash
   make verify
   ```

### Development Setup

```bash
# Install development dependencies
make install-dev

# Set up pre-commit hooks (optional)
pre-commit install
```

## Configuration

1. **Interactive Brokers Setup:**
   - Install TWS or IB Gateway
   - Enable API connections in TWS/Gateway settings
   - Configure socket port (default: 7497 for paper trading, 7496 for live)

2. **Environment Configuration:**
   - Copy `config/config.example.json` to `config/config.json`
   - Update configuration with your settings

## Quick Command Reference

### 🚀 Environment Setup (Run Once)

```bash
# Navigate to project directory
cd "/home/jrae/wsl projects/Trading"

# Activate virtual environment
source .venv/bin/activate

# Verify installation
make verify
```

### 📊 Daily Workflow Commands

**Always start with environment activation:**

```bash
cd "/home/jrae/wsl projects/Trading" && source .venv/bin/activate
```

#### Core Trading Applications

```bash
# Main trading application with Level 2 data
make run-main

# Core trader module
make run-trader

# Manual trading interface
python Ib_Manual_Attempt.py
```

#### Data Management

```bash
# Scan existing data files
make scan-data

# Update all warrior list stocks (comprehensive)
make update-warrior

# Update recent data (last 7 days, 30-min bars)
make update-recent

# Enhanced data updater with progress tracking
python update_data.py --symbols all --timeframes "1 min,30 mins"

# Update specific symbols
python update_data.py --symbols AAPL,MSFT,GOOGL --timeframes "1 min"

# Update with date range
python update_data.py --symbols all --start-date 2025-07-20 --end-date 2025-07-28
```

#### Level 2 Market Depth Recording

```bash
# Test Level 2 connection
make level2-test

# Record Level 2 data for AAPL (60 seconds)
make level2-record SYMBOL=AAPL DURATION=60

# Record with custom parameters
make level2-record SYMBOL=TSLA DURATION=300 LEVELS=10 INTERVAL=100

# Analyze recorded Level 2 data
make level2-analyze SYMBOL=AAPL DATE=2025-07-28
```

#### Example Scripts & Testing

```bash
# PyQt5 ticker table interface
make run-qt-example

# Tkinter GUI interface
make run-tk-example

# Web scanner example
make run-scanner-example

# Run all available examples
make run-examples
```

### 🔧 Development & Maintenance

```bash
# Format code
make format

# Run linting
make lint

# Run tests
make test

# Complete dev check (format + lint + test)
make dev-check

# Clean temporary files
make clean

# Type checking
make typecheck
```

### 📋 One-Liner Commands (Copy & Paste Ready)

**Start trading session:**

```bash
cd "/home/jrae/wsl projects/Trading" && source .venv/bin/activate && make run-main
```

**Quick data update:**

```bash
cd "/home/jrae/wsl projects/Trading" && source .venv/bin/activate && make update-recent
```

**Scan existing data:**

```bash
cd "/home/jrae/wsl projects/Trading" && source .venv/bin/activate && make scan-data
```

**Record Level 2 for AAPL:**

```bash
cd "/home/jrae/wsl projects/Trading" && source .venv/bin/activate && make level2-record SYMBOL=AAPL DURATION=60
```

**Update warrior stocks:**

```bash
cd "/home/jrae/wsl projects/Trading" && source .venv/bin/activate && make update-warrior
```

### 🎯 Common Use Cases

**Morning routine - Check data and start trading:**

```bash
cd "/home/jrae/wsl projects/Trading" && source .venv/bin/activate
make scan-data                    # Check existing data
make update-recent               # Update recent data
make run-main                    # Start main application
```

**Record Level 2 data for analysis:**

```bash
cd "/home/jrae/wsl projects/Trading" && source .venv/bin/activate
make level2-record SYMBOL=AAPL DURATION=300
make level2-analyze SYMBOL=AAPL DATE=$(date +%Y-%m-%d)
```

**Bulk data update:**

```bash
cd "/home/jrae/wsl projects/Trading" && source .venv/bin/activate
python update_data.py --symbols all --timeframes "1 min,30 mins" --output results.json
```

### ⚙️ Prerequisites Before Running Commands

1. **Interactive Brokers TWS or Gateway must be running**
   - Paper trading: Port 7497
   - Live trading: Port 7496

2. **Environment activated:**

   ```bash
   source .venv/bin/activate
   ```

3. **In correct directory:**
   ```bash
   cd "/home/jrae/wsl projects/Trading"
   ```

## Usage

### Quick Start

1. **Start Interactive Brokers TWS or Gateway**

2. **Run the main trading application:**

   ```bash
   make run-main
   ```

3. **Or run individual components:**
   ```bash
   make run-trader
   ```

## Core Components

### Main Files

- **`ib_main.py`**: Main application entry point with Level 2 market data
- **`ib_trader.py`**: Core trading functionality and stock watching
- **`MasterPy_Trading.py`**: Trading utilities, classes, and helper functions
- **`Ib_Manual_Attempt.py`**: Manual trading interface using native IB API

### Dependencies

- **ibapi**: Official Interactive Brokers Python API
- **pandas**: Data manipulation and analysis
- **numpy**: Numerical computing
- **PyQt5**: GUI framework for desktop applications
- **asyncio**: Asynchronous programming support

## Development

### Setting up Development Environment

```bash
# Install development dependencies
pip install -e ".[dev]"

# Install pre-commit hooks
pre-commit install

# Run tests
pytest

# Format code
black .
isort .

# Type checking
mypy src/
```

### Testing

```bash
# Run all tests
pytest

# Run specific test file
pytest tests/test_trading.py

# Run with coverage
pytest --cov=src
```

## Important Notes

### Platform Considerations

- **Windows**: Full functionality including WhatsApp integration
- **Linux/WSL**: Core trading features available (GUI may require X11 forwarding)

### Risk Warnings

⚠️ **IMPORTANT**: This software is for educational and research purposes.

- Always test with paper trading accounts first
- Understand the risks of algorithmic trading
- Ensure proper risk management controls
- Monitor positions and system status regularly
- Be aware of market volatility and system limitations

### Data and Privacy

- This system handles financial data - ensure proper security measures
- API keys and credentials should be stored securely
- Consider encryption for sensitive configuration files

## Troubleshooting

### Common Issues

1. **"Command not found" or "Module not found":**

   ```bash
   # Make sure you're in the right directory and environment is activated
   cd "/home/jrae/wsl projects/Trading"
   source .venv/bin/activate
   ```

2. **Import errors (MasterPy_Trading, etc.):**

   ```bash
   # Run from project root, not from src/ directory
   cd "/home/jrae/wsl projects/Trading"
   python update_data.py  # ✓ Correct
   # Not: cd src && python ../update_data.py  # ✗ Wrong
   ```

3. **Interactive Brokers connection issues:**
   - Verify TWS/Gateway is running
   - Check API settings in TWS/Gateway (Enable API, port 7497 for paper)
   - Try the connection test: `make level2-test`

4. **Permission Errors:**

   ```bash
   # Fix file permissions if needed
   chmod +x .venv/bin/activate
   ```

5. **"No such file or directory" with spaces in path:**

   ```bash
   # Use quotes around the path
   cd "/home/jrae/wsl projects/Trading"
   ```

6. **Virtual environment not found:**
   ```bash
   # Recreate virtual environment if needed
   python -m venv .venv
   source .venv/bin/activate
   make install
   ```

### Quick Diagnostic Commands

```bash
# Check if in correct directory
pwd
# Should show: /home/jrae/wsl projects/Trading

# Check if virtual environment is activated
which python
# Should show: /home/jrae/wsl projects/Trading/.venv/bin/python

# Test IB connection
make level2-test
```

### Getting Help

```bash
# Show all available make commands
make help

# Show data update options
make update-data

# Show example commands
make run-examples
```

### Logging

Enable detailed logging by setting environment variable:

```bash
export IB_LOGLEVEL=DEBUG
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests for new functionality
5. Ensure all tests pass
6. Submit a pull request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Disclaimer

This software is provided "as is" without warranty of any kind. Trading involves risk, and past performance does not guarantee future results. Users are responsible for their own trading decisions and should consult with financial advisors before making investment decisions.

## Support

For issues and questions:

- Check the documentation in the `docs/` directory
- Review existing issues on GitHub
- Create a new issue with detailed information about the problem

## Acknowledgments

- Interactive Brokers for providing the API

- Python trading community for inspiration and guidance
