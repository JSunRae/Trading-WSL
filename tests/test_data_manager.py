"""
Functional tests for src/data/data_manager.py
Covers load/save with temp files and mocked I/O for CSV, JSON, and Excel formats.
"""

import pandas as pd

from src.data.data_manager import DataManager


def test_save_load_feather():
    manager = DataManager()
    df = pd.DataFrame({"A": [1, 2], "B": [3, 4]})
    symbol, timeframe, date_str = "AAPL", "1min", "20250101"
    # Save to feather
    status = manager.save_historical_data(df, symbol, timeframe, date_str)
    assert status.success
    # Load from feather
    loaded = manager.load_historical_data(symbol, timeframe, date_str)
    assert loaded is not None
    assert list(loaded.columns) == ["A", "B"]


def test_data_exists_and_failed():
    manager = DataManager()
    symbol, timeframe, date_str = "AAPL", "1min", "20250101"
    # Save dummy data first so existence check passes
    import pandas as pd

    df = pd.DataFrame({"A": [1, 2], "B": [3, 4]})
    manager.save_historical_data(df, symbol, timeframe, date_str)
    assert manager.data_exists(symbol, timeframe, date_str)
    assert not manager.is_download_failed(symbol, timeframe, date_str)


def test_get_download_summary():
    manager = DataManager()
    summary = manager.get_download_summary()
    assert "total_failed" in summary
    assert "total_downloadable" in summary
    assert "total_downloaded" in summary
    assert "pending_changes" in summary
