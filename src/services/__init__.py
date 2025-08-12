"""
Services Package

Contains all microservices extracted from the monolithic MasterPy_Trading.py

Current Services:
- market_data: Real-time market data, Level 2 depth, tick-by-tick streaming
- historical_data: (Coming soon) Historical data management
- order_management: (Coming soon) Order execution and management
- strategy: (Coming soon) Trading strategies and automation
"""

# Import available services
from . import market_data

__all__ = ["market_data"]
__version__ = "1.0.0"
