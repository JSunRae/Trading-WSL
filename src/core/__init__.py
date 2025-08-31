# Core module for trading system infrastructure
"""
Core infrastructure components for the trading system

This module provides the essential building blocks for the new architecture:
- Configuration management
- Error handling
- Performance monitoring
- Caching and optimization utilities
"""

# Configuration system
from .config import (
    ConfigManager,
    DataPathConfig,
    Environment,
    IBConnectionConfig,
    LoggingConfig,
    get_config,
)

# Error handling system
from .error_handler import (
    ConnectionError,
    DataError,
    ErrorCategory,
    ErrorHandler,
    ErrorReport,
    ErrorSeverity,
    TradingSystemError,
    get_error_handler,
    handle_error,
)

# Performance monitoring system
from .performance import (
    LRUCache,
    PerformanceMonitor,
    batch_operations,
    cached,
    get_cache,
    get_performance_monitor,
    optimize_dataframe_memory,
    performance_monitor,
)

# Convenient imports for common usage
__all__ = [
    # Configuration
    "get_config",
    "ConfigManager",
    "Environment",
    "IBConnectionConfig",
    "DataPathConfig",
    "LoggingConfig",
    # Error handling
    "get_error_handler",
    "handle_error",
    "ErrorHandler",
    "TradingSystemError",
    "DataError",
    "ConnectionError",
    "ErrorSeverity",
    "ErrorCategory",
    "ErrorReport",
    # Performance
    "get_performance_monitor",
    "get_cache",
    "performance_monitor",
    "cached",
    "PerformanceMonitor",
    "LRUCache",
    "batch_operations",
    "optimize_dataframe_memory",
]


# Quick setup function for common usage
def setup_trading_system(environment=None):
    """
    Quick setup function to initialize all core components

    Args:
        environment: Environment to use (defaults to auto-detection)

    Returns:
        dict: Dictionary with all initialized components
    """
    if environment is None:
        environment = Environment.DEVELOPMENT

    components = {
        "config": get_config(environment),
        "error_handler": get_error_handler(),
        "performance_monitor": get_performance_monitor(),
        "cache": get_cache(),
    }

    return components


# The following import is intentionally placed after initial exports to avoid circulars
# ruff: noqa: E402
from .error_handler import ConfigurationError, TradingError, error_context

__all__ = [
    # Configuration
    "get_config",
    "ConfigManager",
    "Environment",
    # Error handling
    "get_error_handler",
    "ErrorHandler",
    "TradingSystemError",
    "ConnectionError",
    "DataError",
    "TradingError",
    "ConfigurationError",
    "handle_error",
    "error_context",
]
