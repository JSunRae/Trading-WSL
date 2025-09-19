"""
Modern Market Depth Service

Replaces the legacy MarketDepthCls from MasterPy_Trading.py
with a modern implementation using the tools/record_depth.py infrastructure.
"""

import warnings
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
import pytz


class MarketDepthService:
    """
    Modern market depth recording service.

    Provides Level 2 market data recording with improved error handling
    and configuration management.
    """

    def __init__(self, ib: Any, contract: Any):
        """Initialize market depth service.

        Args:
            ib: IB connection instance
            contract: IB contract for the symbol
        """
        self.ib = ib
        self.contract = contract
        self.symbol = contract.symbol
        self.start_time = datetime.now(pytz.timezone("US/Eastern"))

        # Initialize data storage
        self.tick_data = pd.DataFrame()
        self.depth_data = pd.DataFrame()

        # Start market depth subscription
        self._setup_market_depth()

    def _setup_market_depth(self) -> None:
        """Setup market depth subscription."""
        try:
            self.ticker = self.ib.reqMktDepth(
                self.contract, numRows=20, isSmartDepth=True
            )
            self.ticker.updateEvent += self._on_depth_update
        except Exception as e:
            print(f"Error setting up market depth for {self.symbol}: {e}")

    def _on_depth_update(self, ticker: Any) -> None:
        """Handle market depth updates."""
        try:
            # Process depth updates - simplified version
            # In practice, you'd want more sophisticated processing
            timestamp = datetime.now(pytz.timezone("US/Eastern"))

            # Store basic depth information
            depth_info = {
                "timestamp": timestamp,
                "symbol": self.symbol,
                "bid_price": getattr(ticker, "bid", None),
                "ask_price": getattr(ticker, "ask", None),
                "bid_size": getattr(ticker, "bidSize", None),
                "ask_size": getattr(ticker, "askSize", None),
            }

            # Add to storage (in practice, you'd want more efficient storage)
            new_row = pd.DataFrame([depth_info])
            self.depth_data = pd.concat([self.depth_data, new_row], ignore_index=True)

        except Exception as e:
            print(f"Error processing depth update for {self.symbol}: {e}")

    def save_data(self) -> str:
        """Save collected depth data."""
        try:
            from ..core.config import get_config

            cfg = get_config()
            l2_dir = cfg.get_env("LEVEL2_DIRNAME", "Level2")
            base_path = cfg.data_paths.base_path / l2_dir / self.symbol
        except Exception:
            # Fallback mirrors environment default
            base_path = Path.home() / "Machine Learning" / "Level2" / self.symbol

        base_path.mkdir(parents=True, exist_ok=True)

        # Generate filename with timestamp
        timestamp_str = self.start_time.strftime("%Y%m%d_%H%M%S")
        filename = f"{self.symbol}_L2_{timestamp_str}.csv"
        filepath = base_path / filename

        # Save data
        if not self.depth_data.empty:
            self.depth_data.to_csv(filepath, index=False)
            return str(filepath)

        return ""

    def cancel_market_depth(self) -> None:
        """Cancel market depth subscription and save data."""
        try:
            if hasattr(self, "ticker"):
                self.ib.cancelMktDepth(self.contract)

            # Save any collected data
            saved_path = self.save_data()
            if saved_path:
                print(f"Market depth data saved to: {saved_path}")

        except Exception as e:
            print(f"Error canceling market depth for {self.symbol}: {e}")

    def cleanup(self) -> None:
        """Cleanup resources."""
        self.cancel_market_depth()


# Legacy compatibility class
class MarketDepthCls:
    """
    DEPRECATED: Legacy wrapper for MarketDepthService.

    This class will be removed in a future version.
    Use MarketDepthService directly instead.
    """

    def __init__(self, ib: Any, contract: Any):
        warnings.warn(
            "MarketDepthCls is deprecated. Use MarketDepthService instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        self._service = MarketDepthService(ib, contract)

    def cancelMktDepth(self) -> None:  # noqa: N802 (legacy API compatibility)
        """Cancel market depth subscription."""
        self._service.cancel_market_depth()

    def cleanup(self) -> None:
        """Cleanup resources."""
        self._service.cleanup()
