"""
Smoke test for ports.py
Tests protocol classes MarketDataClient and DepthDataHandle.
Skips if no public API is present.
"""

from src.domain.ports import DepthDataHandle, MarketDataClient


def test_smoke_ports():
    # Protocol classes should be present
    assert MarketDataClient is not None
    assert DepthDataHandle is not None
