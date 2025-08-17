"""
Modern IB Connection Helper

Replaces the legacy InitiateTWS function from MasterPy_Trading.py
with a clean modern implementation using the infra/ib_client.py
"""

import asyncio
import warnings
from typing import Any

try:
    from ..infra.ib_client import get_ib
    from ..services.historical_data.download_tracker import DownloadTracker
except ImportError:
    from src.infra.ib_client import get_ib
    from src.services.historical_data.download_tracker import DownloadTracker


async def get_ib_connection(
    live_mode: bool = False, client_id: int = 1
) -> tuple[Any, DownloadTracker]:
    """
    Modern replacement for InitiateTWS.

    Args:
        live_mode: True for live trading, False for paper trading
        client_id: IB client ID for the connection

    Returns:
        Tuple of (ib_client, download_tracker)

    Raises:
        ConnectionError: If unable to connect to IB Gateway/TWS
    """
    # Get IB connection using modern client
    ib = await get_ib()

    # Create modern download tracker instead of legacy requestCheckerCLS
    tracker = DownloadTracker()

    return ib, tracker


def get_ib_connection_sync(
    live_mode: bool = False, client_id: int = 1
) -> tuple[Any, DownloadTracker]:
    """
    Synchronous wrapper for get_ib_connection.

    For compatibility with existing synchronous code that used InitiateTWS.
    """
    return asyncio.run(get_ib_connection(live_mode, client_id))


# Legacy compatibility shim - will be removed in future version
async def initiate_tws(
    live_mode: bool = False, client_id: int = 1, use_gateway: bool = False
) -> tuple[Any, DownloadTracker]:  # noqa: ARG001
    """
    DEPRECATED: Use get_ib_connection instead.

    This function will be removed in a future version.
    """
    warnings.warn(
        "initiate_tws is deprecated. Use get_ib_connection instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    return await get_ib_connection(live_mode, client_id)
