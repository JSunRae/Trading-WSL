# Configuration Management System
# Centralized configuration for the trading system

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
    """Interactive Brokers connection configuration"""

    host: str = "127.0.0.1"
    port: int = 7497  # 7497 for paper, 7496 for live
    client_id: int = 1
    timeout: int = 30
    paper_trading: bool = True

    def validate(self):
        """Validate configuration settings"""
        if self.port not in [7496, 7497]:
            raise ValueError("Port must be 7496 (live) or 7497 (paper)")
        if self.paper_trading and self.port == 7496:
            raise ValueError("Paper trading should use port 7497")


@dataclass
class DataPathConfig:
    """Data storage path configuration"""

    base_path: Path
    backup_path: Path
    logs_path: Path
    config_path: Path
    temp_path: Path

    def __post_init__(self):
        """Ensure paths are Path objects"""
        self.base_path = Path(self.base_path)
        self.backup_path = Path(self.backup_path)
        self.logs_path = Path(self.logs_path)
        self.config_path = Path(self.config_path)
        self.temp_path = Path(self.temp_path)

    def create_directories(self):
        """Create all required directories"""
        for path in [self.base_path, self.backup_path, self.logs_path, self.temp_path]:
            path.mkdir(parents=True, exist_ok=True)


@dataclass
class DataUpdateConfig:
    """Data update process configuration"""

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
    """Logging configuration"""

    level: str = "INFO"
    format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    file: str = "./logs/trading.log"
    max_file_size: str = "10MB"
    backup_count: int = 5
    enable_console: bool = True
    enable_file: bool = True


class ConfigManager:
    """Centralized configuration manager for the trading system"""

    def __init__(self, env: Environment = Environment.DEVELOPMENT):
        self.env = env
        # Allow tests to patch a hook for where the config file lives
        self.config_file = self._get_config_file_path()
        self.config = self._load_config()

        # Initialize configuration objects from raw config
        self.ib_connection = IBConnectionConfig(**self.config.get("ib_connection", {}))
        # Apply environment specific overrides before validation
        self._apply_environment_overrides()
        self.data_paths = self._get_platform_paths()
        self.data_update = DataUpdateConfig(**self.config.get("data_update", {}))
        self.logging = LoggingConfig(**self.config.get("logging", {}))

        # Validate configuration
        self.ib_connection.validate()
        self.data_paths.create_directories()

    # --- Hooks & helpers -------------------------------------------------
    def _get_config_file_path(self) -> Path:  # pragma: no cover - simple hook
        """Return path of primary config file (override/patch in tests)."""
        return Path("config/config.json")

    def _apply_environment_overrides(self):
        """Adjust runtime config according to target environment.

        Production should force live trading port (7496) and disable paper trading
        regardless of file defaults. Other environments default to paper.
        """
        if self.env == Environment.PRODUCTION:
            # Force live trading settings
            self.ib_connection.paper_trading = False
            self.ib_connection.port = 7496
        else:
            # Ensure paper settings for non-production if unspecified
            if self.ib_connection.port == 7496 and self.ib_connection.paper_trading:
                # If user accidentally set an invalid combo, switch port to paper port
                self.ib_connection.port = 7497

    def _load_config(self) -> dict[str, Any]:
        """Load configuration from file with defaults"""
        if self.config_file.exists():
            try:
                with self.config_file.open() as f:
                    config = json.load(f)
                return config
            except Exception as e:
                print(f"Warning: Failed to load config file: {e}")

        # Return default configuration
        return self._get_default_config()

    def _get_default_config(self) -> dict[str, Any]:
        """Get default configuration"""
        return {
            "ib_connection": {
                "host": "127.0.0.1",
                "port": 7497,
                "client_id": 1,
                "timeout": 30,
                "paper_trading": True,
            },
            "data_update": {
                "default_timeframes": ["1 min", "30 mins", "1 secs"],
                "max_retry_attempts": 3,
                "retry_delay_seconds": 5,
                "batch_size": 10,
                "max_file_age_days": 30,
            },
            "logging": {
                "level": "INFO",
                "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
                "file": "./logs/trading.log",
                "max_file_size": "10MB",
                "backup_count": 5,
                "enable_console": True,
                "enable_file": True,
            },
        }

    def _get_platform_paths(self) -> DataPathConfig:
        """Get platform-specific data paths"""
        if os.name == "nt":  # Windows
            base_path = Path("G:/Machine Learning")
            backup_path = Path("F:/T7 Backup/Machine Learning")
        else:  # Linux/WSL
            base_path = Path.home() / "Machine Learning"
            backup_path = Path.home() / "T7 Backup/Machine Learning"

        return DataPathConfig(
            base_path=base_path,
            backup_path=backup_path,
            logs_path=Path("logs"),
            config_path=Path("config"),
            temp_path=Path("temp"),
        )

    def save_config(self):
        """Save current configuration to file"""
        config_data = {
            "ib_connection": asdict(self.ib_connection),
            "data_update": asdict(self.data_update),
            "logging": asdict(self.logging),
        }

        self.data_paths.config_path.mkdir(parents=True, exist_ok=True)
        with self.config_file.open("w") as f:
            json.dump(config_data, f, indent=2, default=str)

    def get_data_file_path(
        self, file_type: str, symbol: str = "", timeframe: str = "", date_str: str = ""
    ) -> Path:
        """Get standardized file paths for different data types.

        Reduced branching complexity by using lookup tables.
        """
        base = self.data_paths.base_path
        ml_dir = base / "Machine Learning"
        ml_dir.mkdir(parents=True, exist_ok=True)

        simple_mappings: dict[str, str] = {
            "ib_failed_stocks": "IB Failed Stocks.xlsx",
            "ib_downloadable_stocks": "IB Downloadable Stocks.xlsx",
            "ib_downloaded_stocks": "IB Downloaded Stocks.xlsx",
            "warrior_trading_trades": "WarriorTrading_Trades.xlsx",
            "ib_stocklist": "IB_StockList.ftr",
            # Legacy aliases
            "excel_failed": "IB Failed Stocks.xlsx",
            "excel_downloadable": "IB Downloadable Stocks.xlsx",
            "excel_downloaded": "IB Downloaded Stocks.xlsx",
            "warrior_list": "WarriorTrading_Trades.xlsx",
        }

        if file_type == "ib_download":
            downloads_dir = ml_dir / "IBDownloads"
            downloads_dir.mkdir(parents=True, exist_ok=True)
            return downloads_dir / f"{symbol}_USUSD_{timeframe}_{date_str}.ftr"
        if file_type == "level2":
            level2_dir = base / "Level2" / symbol
            level2_dir.mkdir(parents=True, exist_ok=True)
            return level2_dir / f"{date_str}_snapshots.parquet"
        if file_type == "train_list":
            return ml_dir / f"Train_List-{symbol}.xlsx"
        if file_type in simple_mappings:
            return ml_dir / simple_mappings[file_type]
        raise ValueError(f"Unknown file type: {file_type}")

    def get_backup_path(self, original_path: Path) -> Path:
        """Get backup path for a given file"""
        relative_path = original_path.relative_to(self.data_paths.base_path)
        return self.data_paths.backup_path / relative_path

    def is_paper_trading(self) -> bool:
        """Check if system is configured for paper trading"""
        return self.ib_connection.paper_trading

    def get_ib_port(self) -> int:
        """Get appropriate IB port based on environment"""
        if self.env == Environment.PRODUCTION:
            return 7496  # Live trading
        else:
            return 7497  # Paper trading


# Global configuration instance
_config_manager = None


def get_config(env: Environment = Environment.DEVELOPMENT) -> ConfigManager:
    """Get global configuration manager instance"""
    global _config_manager
    if _config_manager is None:
        _config_manager = ConfigManager(env)
    return _config_manager


def reload_config():
    """Reload configuration from file"""
    global _config_manager
    _config_manager = None
    return get_config()


# Convenience functions for common operations
def get_data_path(file_type: str, **kwargs: str) -> Path:
    """Get data file path using global config"""
    config = get_config()
    return config.get_data_file_path(file_type, **kwargs)


def is_paper_trading() -> bool:
    """Check if paper trading is enabled"""
    config = get_config()
    return config.is_paper_trading()


def get_ib_connection_config() -> IBConnectionConfig:
    """Get IB connection configuration"""
    config = get_config()
    return config.ib_connection
