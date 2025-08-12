"""
Smoke test for data_manager.py
Tests instantiation and public methods of DataManager.
"""

import os

os.environ["FORCE_FAKE_IB"] = "1"

from src.data.data_manager import DataManager


def test_smoke_data_manager():
    manager = DataManager()
    # Test all public methods
    assert callable(manager.save_historical_data)
    assert callable(manager.load_historical_data)
    assert callable(manager.data_exists)
    assert callable(manager.is_download_failed)
    assert callable(manager.get_download_summary)
    assert callable(manager.cleanup)
