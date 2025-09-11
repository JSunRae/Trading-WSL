from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from src.core.configuration import services
from src.infra.events.config_events import subscribe, unsubscribe


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


@pytest.fixture()
def tmp_services_paths(tmp_path: Path):
    # Redirect config and backup directories to a temp sandbox for all tests
    orig_config = services.CONFIG_DIR
    orig_backup = services.BACKUP_DIR
    services.CONFIG_DIR = tmp_path / "config"
    services.BACKUP_DIR = tmp_path / "backups"
    try:
        yield services
    finally:
        services.CONFIG_DIR = orig_config
        services.BACKUP_DIR = orig_backup


def _valid_config_payload() -> dict[str, Any]:
    return {
        "ib_connection": {
            "host": "localhost",
            "port": 4001,
            "client_id": 1,
            "timeout": 10,
            "paper_trading": True,
            "live_port": 7496,
            "paper_port": 7497,
            "gateway_live_port": 4002,
            "gateway_paper_port": 4003,
        },
        "data_update": {
            "default_timeframes": ["1min"],
            "max_retry_attempts": 3,
            "retry_delay_seconds": 5,
            "batch_size": 100,
            "max_file_age_days": 7,
        },
        "logging": {
            "level": "INFO",
            "format": "%(asctime)s %(levelname)s %(message)s",
            "file": "trading.log",
            "max_file_size": "10MB",
            "backup_count": 5,
            "enable_console": True,
            "enable_file": True,
        },
    }


def _valid_ib_gateway_payload() -> dict[str, Any]:
    return {
        "ib_gateway": {
            "paper_trading": {
                "host": "localhost",
                "port": 7497,
                "client_id": 2,
                "timeout": 10,
                "enabled": True,
            },
            "live_trading": {
                "host": "localhost",
                "port": 7496,
                "client_id": 3,
                "timeout": 10,
                "enabled": False,
            },
        },
        "connection_settings": {
            "auto_reconnect": True,
            "max_reconnect_attempts": 5,
            "reconnect_delay": 2,
            "heartbeat_interval": 5,
        },
        "api_settings": {
            "request_pacing": True,
            "max_requests_per_minute": 60,
            "enable_logging": True,
            "log_level": "INFO",
        },
    }


def _valid_symbol_mapping_payload() -> dict[str, Any]:
    return {"AAPL": {"symbol": "AAPL", "dataset": "stocks", "schema": "level2"}}


def test_validate_and_load_configs(tmp_services_paths):
    # Arrange: write three valid config files under the sandboxed CONFIG_DIR
    cfg_dir = tmp_services_paths.CONFIG_DIR
    _write_json(cfg_dir / "config.json", _valid_config_payload())
    _write_json(cfg_dir / "ib_gateway_config.json", _valid_ib_gateway_payload())
    _write_json(cfg_dir / "symbol_mapping.json", _valid_symbol_mapping_payload())

    # Act + Assert: load and validate each
    for fname in ("config.json", "ib_gateway_config.json", "symbol_mapping.json"):
        data = tmp_services_paths.load_config(fname)
        result = tmp_services_paths.validate_config(fname, data)
        assert result.valid, f"Expected valid schema for {fname}: {result.errors}"


def test_diff_dict_changed_added_removed(tmp_services_paths):
    old = {"a": 1, "b": 2, "c": 3}
    new = {"a": 10, "b": 2, "d": 4}
    d = tmp_services_paths.diff_dict(old, new)
    assert d["changed"] == {"a": {"from": 1, "to": 10}}
    assert d["added"] == {"d": 4}
    assert d["removed"] == {"c": 3}


def test_save_creates_backup_and_emits_event(tmp_services_paths):
    # Arrange: initial files
    cfg_dir = tmp_services_paths.CONFIG_DIR
    _write_json(cfg_dir / "symbol_mapping.json", _valid_symbol_mapping_payload())

    received: list[tuple[str, dict[str, Any]]] = []

    def on_change(filename: str, diff: dict[str, Any]) -> None:
        received.append((filename, diff))

    subscribe(on_change)
    try:
        # Act: modify and save
        data = tmp_services_paths.load_config("symbol_mapping.json")
        data["MSFT"] = {"symbol": "MSFT", "dataset": "stocks", "schema": "level2"}
        result = tmp_services_paths.save_config("symbol_mapping.json", data)

        # Assert: valid save
        assert result.valid

        # Backup exists
        backups = sorted((tmp_services_paths.BACKUP_DIR).glob("*/symbol_mapping.json"))
        assert backups, "Expected at least one backup created"
        assert backups[-1].stat().st_size > 0

        # Event emitted
        assert received, "Expected a config_changed event"
        fname, diff = received[-1]
        assert fname == "symbol_mapping.json"
        # Should reflect at least an 'added' key for MSFT
        assert "added" in diff and "MSFT" in diff["added"]
    finally:
        unsubscribe(on_change)
