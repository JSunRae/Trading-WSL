#!/usr/bin/env python3
"""
Unit tests for the core configuration system
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from src.core.config import (
    ConfigManager,
    DataPathConfig,
    Environment,
    IBConnectionConfig,
    LoggingConfig,
)


class TestConfigManager(unittest.TestCase):
    """Test cases for ConfigManager"""

    def setUp(self):
        """Set up test fixtures"""
        self.temp_dir = tempfile.mkdtemp()
        self.config_path = Path(self.temp_dir) / "test_config.json"

    def test_default_configuration(self):
        """Test that default configuration loads correctly"""
        with patch("src.core.config.Path.home") as mock_home:
            mock_home.return_value = Path(self.temp_dir)

            manager = ConfigManager(Environment.DEVELOPMENT)

            # Test IB connection defaults
            self.assertEqual(manager.ib_connection.host, "127.0.0.1")
            self.assertEqual(manager.ib_connection.port, 7497)
            self.assertTrue(manager.ib_connection.paper_trading)

            # Test data paths
            self.assertIsInstance(manager.data_paths.base_path, Path)

    def test_environment_specific_config(self):
        """Test environment-specific configuration loading"""
        # Test development vs production differences
        dev_manager = ConfigManager(Environment.DEVELOPMENT)
        prod_manager = ConfigManager(Environment.PRODUCTION)

        # Development should use paper trading
        self.assertTrue(dev_manager.ib_connection.paper_trading)

        # Production should use live trading
        self.assertFalse(prod_manager.ib_connection.paper_trading)
        self.assertEqual(prod_manager.ib_connection.port, 7496)

    def test_config_validation(self):
        """Test configuration validation"""
        # Test invalid port
        with self.assertRaises(ValueError):
            config = IBConnectionConfig(port=9999)
            config.validate()

        # Test paper trading with live port
        with self.assertRaises(ValueError):
            config = IBConnectionConfig(port=7496, paper_trading=True)
            config.validate()

    def test_file_path_generation(self):
        """Test file path generation"""
        manager = ConfigManager(Environment.DEVELOPMENT)

        # Test IB download path
        ib_path = manager.get_data_file_path(
            "ib_download", symbol="AAPL", timeframe="1 min", date_str="2025-07-29"
        )
        self.assertTrue(str(ib_path).endswith("AAPL_USUSD_1 min_2025-07-29.ftr"))

        # Test level 2 path
        l2_path = manager.get_data_file_path(
            "level2", symbol="TSLA", date_str="2025-07-29"
        )
        self.assertTrue("Level2/TSLA" in str(l2_path))

    def test_config_save_load(self):
        """Test configuration saving and loading"""
        manager = ConfigManager(Environment.DEVELOPMENT)

        # Save configuration
        manager.save_config()

        # Load and verify
        loaded_manager = ConfigManager(Environment.DEVELOPMENT)
        self.assertEqual(manager.ib_connection.host, loaded_manager.ib_connection.host)
        self.assertEqual(manager.ib_connection.port, loaded_manager.ib_connection.port)


class TestDataclassConfigs(unittest.TestCase):
    """Test individual configuration dataclasses"""

    def test_ib_connection_config(self):
        """Test IBConnectionConfig dataclass"""
        config = IBConnectionConfig(
            host="localhost", port=7497, client_id=2, timeout=60, paper_trading=True
        )

        self.assertEqual(config.host, "localhost")
        self.assertEqual(config.client_id, 2)
        self.assertEqual(config.timeout, 60)

        # Test validation
        config.validate()  # Should not raise

    def test_data_path_config(self):
        """Test DataPathConfig dataclass"""
        config = DataPathConfig(
            base_path=Path("/test/data"),
            backup_path=Path("/test/backup"),
            logs_path=Path("/test/logs"),
            config_path=Path("/test/config"),
            temp_path=Path("/test/temp"),
        )

        # All paths should be Path objects
        self.assertIsInstance(config.base_path, Path)
        self.assertIsInstance(config.backup_path, Path)

    def test_logging_config(self):
        """Test LoggingConfig dataclass"""
        config = LoggingConfig(
            level="DEBUG",
            format="%(levelname)s: %(message)s",
            file="./test.log",
            max_file_size="5MB",
            backup_count=3,
            enable_console=False,
            enable_file=True,
        )

        self.assertEqual(config.level, "DEBUG")
        self.assertFalse(config.enable_console)
        self.assertTrue(config.enable_file)


class TestConfigIntegration(unittest.TestCase):
    """Integration tests for configuration system"""

    def test_get_config_singleton(self):
        """Test that get_config returns singleton"""
        from src.core.config import get_config

        config1 = get_config(Environment.DEVELOPMENT)
        config2 = get_config(Environment.DEVELOPMENT)

        # Should be the same instance
        self.assertIs(config1, config2)

    def test_config_with_custom_file(self):
        """Test loading configuration from custom file"""
        # Create test config file
        test_config = {
            "ib_connection": {"host": "test.host.com", "port": 7497, "client_id": 99},
            "logging": {"level": "DEBUG", "file": "./test.log"},
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(test_config, f)
            temp_config_path = f.name

        try:
            # Mock the config file loading
            with patch(
                "src.core.config.ConfigManager._get_config_file_path"
            ) as mock_path:
                mock_path.return_value = Path(temp_config_path)

                manager = ConfigManager(Environment.DEVELOPMENT)

                # Should load custom values
                self.assertEqual(manager.ib_connection.host, "test.host.com")
                self.assertEqual(manager.ib_connection.client_id, 99)
                self.assertEqual(manager.logging.level, "DEBUG")
        finally:
            Path(temp_config_path).unlink()


if __name__ == "__main__":
    unittest.main()
