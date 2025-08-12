"""
Historical Data Service Package

This service extracts and modernizes the historical data management
functionality from the monolithic requestCheckerCLS.

Critical Issue Fix #2: Monolithic Class Decomposition
Priority: IMMEDIATE (Week 1-2)
Impact: Maintainability, testability, separation of concerns
"""

from .availability_checker import AvailabilityChecker
from .download_tracker import DownloadTracker
from .historical_data_service import HistoricalDataService

__all__ = [
    "HistoricalDataService",
    "DownloadTracker",
    "AvailabilityChecker",
]


def get_historical_data_service():
    """Get a configured historical data service instance"""
    return HistoricalDataService()
