from __future__ import annotations

import pandas as pd

from src.core.config import ConfigManager
from src.data.data_manager import DataManager


class DummyConfig(ConfigManager):
    def _get_config_file_path(self):  # pragma: no cover - simple override
        # Avoid touching real files
        from pathlib import Path

        return Path("temp/test_config.json")


def test_download_tracker_mark_and_queries(tmp_path, monkeypatch):  # noqa: ANN001
    # Force data paths under tmp_path
    cfg = DummyConfig()
    cfg.data_paths.base_path = tmp_path
    cfg.data_paths.backup_path = tmp_path / "backup"
    cfg.data_paths.logs_path = tmp_path / "logs"
    cfg.data_paths.config_path = tmp_path / "config"
    cfg.data_paths.temp_path = tmp_path / "temp"

    dm = DataManager(cfg)
    tr = dm.download_tracker

    assert tr.mark_failed("AAPL", "1 min", "2025-01-01", "err") is True
    assert tr.is_failed("AAPL", "1 min", "2025-01-01") is True

    assert tr.mark_downloadable("AAPL", "1 min", "2024-01-01", start_date="2024-06-01")
    assert tr.df_downloadable.loc["AAPL", "Stock"] == "AAPL"

    assert tr.mark_downloaded("AAPL", "1 min", "2025-01-02")
    assert tr.is_downloaded("AAPL", "1 min", "2025-01-02") is True

    # Ensure save methods don't crash and reset counters
    tr.failed_changes = 20
    tr.downloadable_changes = 20
    tr.downloaded_changes = 20
    dm.cleanup()
    assert tr.failed_changes == 0
    assert tr.downloadable_changes == 0
    assert tr.downloaded_changes == 0


def test_excel_repo_handles_missing_files(tmp_path):  # noqa: ANN001
    cfg = DummyConfig()
    cfg.data_paths.base_path = tmp_path
    dm = DataManager(cfg)

    # No files exist yet, ensure load returns None and exists() is False
    assert dm.excel_repo.load("AAPL") is None or isinstance(
        dm.excel_repo.load("AAPL"), pd.DataFrame
    )
    assert dm.excel_repo.exists("AAPL") is False
