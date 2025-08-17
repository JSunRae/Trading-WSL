# Configuration Management System
# Centralized configuration for the trading system

"""Configuration Management System with centralized .env driven paths."""

import json
import os
from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path
from typing import Any


class Environment(Enum):
    DEVELOPMENT = "development"
    TESTING = "testing"
    PRODUCTION = "production"


@dataclass
class IBConnectionConfig:
    host: str = "127.0.0.1"
    port: int = 7497
    client_id: int = 1
    timeout: int = 30
    paper_trading: bool = True
    live_port: int = 7496
    paper_port: int = 7497
    gateway_live_port: int = 4001
    gateway_paper_port: int = 4002

    def validate(self):
        if self.port not in [7496, 7497, 4001, 4002]:
            raise ValueError("Port must be 7496 (live), 7497 (paper), 4001 (gateway live), or 4002 (gateway paper)")
        if self.paper_trading and self.port == 7496:
            raise ValueError("Paper trading should use port 7497")

    def get_port_for_mode(self, use_gateway: bool = False) -> int:
        """Get the appropriate port based on trading mode and gateway usage."""
        if use_gateway:
            return self.gateway_paper_port if self.paper_trading else self.gateway_live_port
        return self.paper_port if self.paper_trading else self.live_port


@dataclass
class DataPathConfig:
    base_path: Path
    backup_path: Path
    logs_path: Path
    config_path: Path
    temp_path: Path

    def __post_init__(self):
        self.base_path = Path(self.base_path)
        self.backup_path = Path(self.backup_path)
        self.logs_path = Path(self.logs_path)
        self.config_path = Path(self.config_path)
        self.temp_path = Path(self.temp_path)

    def create_directories(self):
        for p in [self.base_path, self.backup_path, self.logs_path, self.temp_path]:
            p.mkdir(parents=True, exist_ok=True)


@dataclass
class DataUpdateConfig:
    default_timeframes: list[str] | None = None
    max_retry_attempts: int = 3
    retry_delay_seconds: int = 5
    batch_size: int = 10
    max_file_age_days: int = 30

    def __post_init__(self):
        if self.default_timeframes is None:
            self.default_timeframes = ["1 min", "30 mins", "1 secs"]


@dataclass
class LoggingConfig:
    level: str = "INFO"
    format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    file: str = "./logs/trading.log"
    max_file_size: str = "10MB"
    backup_count: int = 5
    enable_console: bool = True
    enable_file: bool = True


def _load_dotenv(path: str = ".env") -> dict[str, str]:  # pragma: no cover
    env: dict[str, str] = {}
    p = Path(path)
    if not p.exists():
        return env
    try:
        for raw in p.read_text().splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            v = v.strip().strip('"').strip("'")
            if v.startswith("~/"):
                v = str(Path.home() / v[2:])
            env[k.strip()] = v
    except Exception:
        return {}
    return env


class ConfigManager:
    def __init__(self, env: Environment = Environment.DEVELOPMENT):
        self.env = env
        self.config_file = self._get_config_file_path()
        self.config = self._load_config()
        self._dotenv = _load_dotenv()
        self._env_defaults: dict[str, str] = {
            "ML_BASE_PATH": str(Path.home() / "Machine Learning"),
            "ML_BACKUP_PATH": str(Path.home() / "T7 Backup" / "Machine Learning"),
            "LOGS_PATH": "logs",
            "TEMP_PATH": "temp",
            "CONFIG_PATH": "config",
            "DATA_PATH_OVERRIDE": "./data",
            "FILES_PATH": "./Files",
            "CACHE_PATH": "./cache",
            "IB_FAILED_STOCKS_FILENAME": "IB Failed Stocks.xlsx",
            "IB_DOWNLOADABLE_STOCKS_FILENAME": "IB Downloadable Stocks.xlsx",
            "IB_DOWNLOADED_STOCKS_FILENAME": "IB Downloaded Stocks.xlsx",
            "WARRIOR_TRADES_FILENAME": "WarriorTrading_Trades.xlsx",
            "TRAIN_LIST_PREFIX": "Train_List-",
            "FAILED_STOCKS_CSV": "failed_stocks.csv",
            "DOWNLOADABLE_STOCKS_CSV": "downloadable_stocks.csv",
            "DOWNLOADED_STOCKS_CSV": "downloaded_stocks.csv",
            "REQUEST_CHECKER_BIN": "Files/requestChecker.bin",
            "LEVEL2_DIRNAME": "Level2",
            "IB_DOWNLOADS_DIRNAME": "IBDownloads",
            "IB_HOST": "127.0.0.1",
            "IB_LIVE_PORT": "7496",
            "IB_PAPER_PORT": "7497",
            "IB_GATEWAY_LIVE_PORT": "4001",
            "IB_GATEWAY_PAPER_PORT": "4002",
            "DEFAULT_DATA_FORMAT": "parquet",
            "BACKUP_FORMAT": "csv",
            "EXCEL_ENGINE": "openpyxl",
            "MAX_WORKERS": "4",
            "CHUNK_SIZE": "1000",
            "CACHE_SIZE_MB": "512",
            "CONNECTION_TIMEOUT": "30",
            "RETRY_ATTEMPTS": "3",
        }
        ib_config_data = self.config.get("ib_connection", {})
        self.ib_connection = IBConnectionConfig(
            host=ib_config_data.get("host", self.get_env("IB_HOST")),
            port=ib_config_data.get("port", self.get_env_int("IB_PORT", 7497)),
            client_id=ib_config_data.get("client_id", self.get_env_int("IB_CLIENT_ID", 1)),
            timeout=ib_config_data.get("timeout", self.get_env_int("CONNECTION_TIMEOUT", 30)),
            paper_trading=ib_config_data.get("paper_trading", self.get_env_bool("IB_PAPER_TRADING", True)),
            live_port=ib_config_data.get("live_port", self.get_env_int("IB_LIVE_PORT", 7496)),
            paper_port=ib_config_data.get("paper_port", self.get_env_int("IB_PAPER_PORT", 7497)),
            gateway_live_port=ib_config_data.get("gateway_live_port", self.get_env_int("IB_GATEWAY_LIVE_PORT", 4001)),
            gateway_paper_port=ib_config_data.get("gateway_paper_port", self.get_env_int("IB_GATEWAY_PAPER_PORT", 4002)),
        )
        self._apply_environment_overrides()
        self.data_paths = self._get_platform_paths()
        self.data_update = DataUpdateConfig(**self.config.get("data_update", {}))
        self.logging = LoggingConfig(**self.config.get("logging", {}))
        self.ib_connection.validate()
        self.data_paths.create_directories()

    # -------------- internal helpers -----------------
    def _get_config_file_path(self) -> Path:  # pragma: no cover
        return Path("config/config.json")

    def _apply_environment_overrides(self):
        if self.env == Environment.PRODUCTION:
            self.ib_connection.paper_trading = False
            self.ib_connection.port = 7496
        else:
            if self.ib_connection.port == 7496 and self.ib_connection.paper_trading:
                self.ib_connection.port = 7497

    def _load_config(self) -> dict[str, Any]:
        if self.config_file.exists():
            try:
                with self.config_file.open() as f:
                    return json.load(f)
            except Exception as e:  # pragma: no cover
                print(f"Warning: Failed to load config file: {e}")
        return {
            "ib_connection": {},
            "data_update": {},
            "logging": {},
        }

    def _get_platform_paths(self) -> DataPathConfig:
        base_path = Path(self.get_env("ML_BASE_PATH"))
        backup_path = Path(self.get_env("ML_BACKUP_PATH"))
        return DataPathConfig(
            base_path=base_path,
            backup_path=backup_path,
            logs_path=Path(self.get_env("LOGS_PATH")),
            config_path=Path(self.get_env("CONFIG_PATH")),
            temp_path=Path(self.get_env("TEMP_PATH")),
        )

    # -------------- public API -----------------
    def save_config(self):
        data = {
            "ib_connection": asdict(self.ib_connection),
            "data_update": asdict(self.data_update),
            "logging": asdict(self.logging),
        }
        self.data_paths.config_path.mkdir(parents=True, exist_ok=True)
        with self.config_file.open("w") as f:
            json.dump(data, f, indent=2, default=str)

    def get_env(self, key: str, default: str | None = None) -> str:
        if key in os.environ:
            return os.environ[key]
        if key in self._dotenv:
            return self._dotenv[key]
        if key in self._env_defaults:
            return self._env_defaults[key]
        return default or ""

    def get_env_path(self, key: str, default: str | None = None) -> Path:
        val = self.get_env(key, default)
        return Path(val) if val else Path()

    def get_env_int(self, key: str, default: int = 0) -> int:
        """Get environment variable as integer."""
        val = self.get_env(key, str(default))
        try:
            return int(val)
        except ValueError:
            return default

    def get_env_bool(self, key: str, default: bool = False) -> bool:
        """Get environment variable as boolean."""
        val = self.get_env(key, str(default)).lower()
        return val in ("true", "1", "yes", "on")

    def get_csv_file_path(self, csv_type: str) -> Path:
        """Get path for CSV files in data directory."""
        data_dir = Path(self.get_env("DATA_PATH_OVERRIDE"))
        csv_files = {
            "failed_stocks": self.get_env("FAILED_STOCKS_CSV"),
            "downloadable_stocks": self.get_env("DOWNLOADABLE_STOCKS_CSV"),
            "downloaded_stocks": self.get_env("DOWNLOADED_STOCKS_CSV"),
        }
        if csv_type not in csv_files:
            raise ValueError(f"Unknown CSV type: {csv_type}")
        return data_dir / csv_files[csv_type]

    def get_files_dir(self) -> Path:
        """Get the Files directory path."""
        return Path(self.get_env("FILES_PATH"))

    def get_cache_dir(self) -> Path:
        """Get the cache directory path."""
        return Path(self.get_env("CACHE_PATH"))

    def get_ib_host(self) -> str:
        """Get IB connection host."""
        return self.get_env("IB_HOST")

    def get_performance_settings(self) -> dict[str, int]:
        """Get performance-related settings."""
        return {
            "max_workers": self.get_env_int("MAX_WORKERS", 4),
            "chunk_size": self.get_env_int("CHUNK_SIZE", 1000),
            "cache_size_mb": self.get_env_int("CACHE_SIZE_MB", 512),
            "connection_timeout": self.get_env_int("CONNECTION_TIMEOUT", 30),
            "retry_attempts": self.get_env_int("RETRY_ATTEMPTS", 3),
        }

    def get_file_format_settings(self) -> dict[str, str]:
        """Get file format preferences."""
        return {
            "default_data_format": self.get_env("DEFAULT_DATA_FORMAT"),
            "backup_format": self.get_env("BACKUP_FORMAT"),
            "excel_engine": self.get_env("EXCEL_ENGINE"),
        }

    def get_special_file(self, logical_name: str) -> Path:
        if logical_name == "request_checker_bin":
            return self.get_env_path("REQUEST_CHECKER_BIN")
        if logical_name == "warrior_trading_trades":
            # Lives in base Machine Learning directory
            return self.get_data_file_path("warrior_trading_trades")
        raise ValueError(f"Unknown special file logical name: {logical_name}")

    def get_data_file_path(
        self, file_type: str, symbol: str = "", timeframe: str = "", date_str: str = ""
    ) -> Path:
        base = self.data_paths.base_path
        ml_dir = base
        ml_dir.mkdir(parents=True, exist_ok=True)
        simple: dict[str, str] = {
            "ib_failed_stocks": self.get_env("IB_FAILED_STOCKS_FILENAME"),
            "ib_downloadable_stocks": self.get_env("IB_DOWNLOADABLE_STOCKS_FILENAME"),
            "ib_downloaded_stocks": self.get_env("IB_DOWNLOADED_STOCKS_FILENAME"),
            "warrior_trading_trades": self.get_env("WARRIOR_TRADES_FILENAME"),
            "ib_stocklist": "IB_StockList.ftr",
            # legacy aliases
            "excel_failed": self.get_env("IB_FAILED_STOCKS_FILENAME"),
            "excel_downloadable": self.get_env("IB_DOWNLOADABLE_STOCKS_FILENAME"),
            "excel_downloaded": self.get_env("IB_DOWNLOADED_STOCKS_FILENAME"),
            "warrior_list": self.get_env("WARRIOR_TRADES_FILENAME"),
        }
        if file_type == "ib_download":
            ddir = ml_dir / self.get_env("IB_DOWNLOADS_DIRNAME")
            ddir.mkdir(parents=True, exist_ok=True)
            return ddir / f"{symbol}_USUSD_{timeframe}_{date_str}.ftr"
        if file_type == "level2":
            l2 = base / self.get_env("LEVEL2_DIRNAME") / symbol
            l2.mkdir(parents=True, exist_ok=True)
            return l2 / f"{date_str}_snapshots.parquet"
        if file_type == "train_list":
            return ml_dir / f"{self.get_env('TRAIN_LIST_PREFIX')}{symbol}.xlsx"
        if file_type in simple:
            return ml_dir / simple[file_type]
        raise ValueError(f"Unknown file type: {file_type}")

    def get_backup_path(self, original_path: Path) -> Path:
        rel = original_path.relative_to(self.data_paths.base_path)
        return self.data_paths.backup_path / rel

    def is_paper_trading(self) -> bool:
        return self.ib_connection.paper_trading

    def get_ib_port(self) -> int:
        return 7496 if self.env == Environment.PRODUCTION else 7497


_config_manager: ConfigManager | None = None


def get_config(env: Environment = Environment.DEVELOPMENT) -> ConfigManager:
    global _config_manager
    if _config_manager is None:
        _config_manager = ConfigManager(env)
    return _config_manager


def reload_config() -> ConfigManager:
    global _config_manager
    _config_manager = None
    return get_config()


def get_data_path(file_type: str, **kwargs: str) -> Path:
    return get_config().get_data_file_path(file_type, **kwargs)


def is_paper_trading() -> bool:
    return get_config().is_paper_trading()


def get_ib_connection_config() -> IBConnectionConfig:
    return get_config().ib_connection
