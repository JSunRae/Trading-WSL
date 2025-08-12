"""
Market Data Service Package

Modern market data service extracted from monolithic MasterPy_Trading.py

Features:
- Level 2 market depth (order book) data
- Tick-by-tick real-time data streaming
- High-performance Parquet storage (25-100x faster than Excel)
- Enterprise error handling with automatic recovery
- Cross-platform notification support
- Clean service interfaces for integration

Usage:
    from src.services.market_data import get_market_data_service

    service = get_market_data_service(ib_connection)
    service.start_level2_data("AAPL", num_levels=20)
    service.start_tick_data("AAPL")
"""

from .market_data_service import (
    MarketDataService,
    MarketDepthManager,
    TickByTickManager,
    get_market_data_service,
)

__all__ = [
    "MarketDataService",
    "MarketDepthManager",
    "TickByTickManager",
    "get_market_data_service",
]

__version__ = "1.0.0"
