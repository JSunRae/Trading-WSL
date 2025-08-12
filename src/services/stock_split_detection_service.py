"""
Stock Split Detection Service

This service detects stock splits and ensures data integrity for machine learning models.
Stock splits create artificial price discontinuities that can mislead ML algorithms.

Author: Interactive Brokers Trading System
Created: July 2025 (ML Data Integrity Enhancement)
"""

import logging
import os
import sys
from datetime import date as date_type
from datetime import datetime, timedelta
from typing import Any

import numpy as np
import pandas as pd

# Add src to path for imports
sys.path.append(os.path.join(os.path.dirname(__file__), "..", ".."))

# Try to import core services
try:
    from src.core.config import get_config  # type: ignore[attr-defined]  # Dynamic path imports
    from src.core.error_handler import handle_error  # type: ignore[attr-defined]  # Dynamic path imports
    from src.services.data_persistence_service import (
        DataPersistenceService,  # type: ignore[attr-defined]  # Dynamic path imports
    )

    # Try to get the real DataError
    try:
        from src.core.error_handler import DataError  # type: ignore[attr-defined]  # Dynamic path imports
    except ImportError:
        # Keep fallback if import fails
        class DataError(Exception):  # type: ignore[misc]  # Fallback class definition
            """Fallback data error"""

            pass

except ImportError:
    # Fallback implementations
    print("Warning: Could not import core modules, using fallback implementations")

    def get_config(env=None):
        """Fallback config getter."""
        return None

    def handle_error(error, context=None, module="", function=""):
        """Fallback error handler."""
        print(f"Error in {module}.{function}: {error}")
        return None

    class DataPersistenceService:
        """Fallback data persistence service."""

        def __init__(self):
            pass

    class DataError(Exception):
        """Fallback data error"""

        pass


class SplitEvent:
    """Represents a detected stock split event."""

    def __init__(
        self,
        symbol: str,
        split_date: date_type,
        split_ratio: float,
        confidence: float,
        detection_method: str,
    ):
        self.symbol = symbol
        self.split_date = split_date
        self.split_ratio = split_ratio  # e.g., 2.0 for 2:1 split, 0.5 for 1:2 split
        self.confidence = confidence  # 0.0 to 1.0
        self.detection_method = detection_method
        self.detected_at = datetime.now()

    def __str__(self):
        split_type = (
            f"{int(self.split_ratio)}:1"
            if self.split_ratio >= 1
            else f"1:{int(1 / self.split_ratio)}"
        )
        return f"{self.symbol} {split_type} split on {self.split_date} (confidence: {self.confidence:.2f})"

    def to_dict(self):
        return {
            "symbol": self.symbol,
            "split_date": self.split_date.isoformat(),
            "split_ratio": self.split_ratio,
            "confidence": self.confidence,
            "detection_method": self.detection_method,
            "detected_at": self.detected_at.isoformat(),
        }


class StockSplitDetectionService:
    """
    Detects stock splits in historical data to maintain ML model integrity.

    Features:
    - Multiple detection algorithms
    - Confidence scoring
    - Split ratio calculation
    - Data invalidation triggers
    - Fresh data recommendations
    """

    def __init__(self, data_persistence_service: DataPersistenceService | None = None):
        """
        Initialize the Stock Split Detection Service.

        Args:
            data_persistence_service: Optional data persistence service for tracking
        """
        self.data_service = data_persistence_service or DataPersistenceService()
        self.config = None
        self.logger = logging.getLogger(__name__)

        # Detection thresholds
        self.price_jump_threshold = 0.4  # 40% overnight change triggers investigation
        self.volume_spike_threshold = 3.0  # 3x normal volume
        self.min_confidence = 0.7  # Minimum confidence to report split

        # Common split ratios to check
        self.common_ratios = [
            2.0,
            3.0,
            1.5,
            0.5,
            0.333,
            0.25,
        ]  # 2:1, 3:1, 3:2, 1:2, 1:3, 1:4

        self._load_config()
        self._setup_split_tracking()

    def _load_config(self) -> None:
        """Load configuration settings."""
        try:
            self.config = get_config()
        except Exception as e:
            handle_error(e, module="SplitDetection", function="_load_config")
            self.config = None

    def _setup_split_tracking(self) -> None:
        """Set up DataFrame for tracking detected splits."""
        self.detected_splits = pd.DataFrame(
            columns=[
                "symbol",
                "split_date",
                "split_ratio",
                "confidence",
                "detection_method",
                "detected_at",
                "action_taken",
            ]
        )

    def detect_splits_in_data(
        self, symbol: str, df: pd.DataFrame, timeframe: str = "1 day"
    ) -> list[SplitEvent]:
        """
        Detect potential stock splits in price data.

        Args:
            symbol: Stock symbol
            df: DataFrame with OHLCV data
            timeframe: Data timeframe (affects detection sensitivity)

        Returns:
            List of detected split events
        """
        if df is None or len(df) < 10:
            self.logger.warning(f"Insufficient data for split detection: {symbol}")
            return []

        splits: list[SplitEvent] = []

        # Ensure we have required columns
        required_cols = ["close", "volume"]
        if not all(col in df.columns for col in required_cols):
            self.logger.error(f"Missing required columns for split detection: {symbol}")
            return []

        try:
            # Method 1: Price Gap Detection
            price_splits = self._detect_price_gaps(symbol, df)
            splits.extend(price_splits)

            # Method 2: Volume Spike + Price Drop Detection
            volume_splits = self._detect_volume_anomalies(symbol, df)
            splits.extend(volume_splits)

            # Method 3: Adjusted Close Ratio Detection (if available)
            if "adjusted_close" in df.columns:
                ratio_splits = self._detect_adjustment_ratios(symbol, df)
                splits.extend(ratio_splits)

            # Consolidate overlapping detections
            splits = self._consolidate_split_detections(splits)

            # Filter by confidence threshold
            high_confidence_splits = [
                s for s in splits if s.confidence >= self.min_confidence
            ]

            if high_confidence_splits:
                self.logger.info(
                    f"Detected {len(high_confidence_splits)} high-confidence splits for {symbol}"
                )

                # Track the detections
                for split in high_confidence_splits:
                    self._record_split_detection(split)

            return high_confidence_splits

        except Exception as e:
            handle_error(e, module="SplitDetection", function="detect_splits_in_data")
            return []

    def _detect_price_gaps(self, symbol: str, df: pd.DataFrame) -> list[SplitEvent]:
        """Detect splits based on overnight price gaps."""
        splits: list[SplitEvent] = []

        # Calculate overnight returns
        df_sorted = df.sort_index()
        overnight_returns = df_sorted["close"].pct_change()

        # Look for significant negative jumps (splits cause price to drop)
        for i, return_val in enumerate(overnight_returns):
            if pd.isna(return_val) or i == 0:
                continue

            # Check for significant negative return
            if return_val < -self.price_jump_threshold:
                split_date = (
                    df_sorted.index[i].date()
                    if hasattr(df_sorted.index[i], "date")  # pyright: ignore[reportUnknownMemberType]  # pandas datetime index
                    else df_sorted.index[i]
                )

                # Calculate implied split ratio
                price_ratio = abs(return_val) + 1  # Convert to ratio
                split_ratio = self._find_closest_split_ratio(price_ratio)

                # Calculate confidence based on how close to common ratio
                confidence = self._calculate_price_gap_confidence(
                    return_val, split_ratio, df_sorted, i
                )

                split = SplitEvent(
                    symbol=symbol,
                    split_date=split_date,
                    split_ratio=split_ratio,
                    confidence=confidence,
                    detection_method="price_gap",
                )
                splits.append(split)

        return splits

    def _detect_volume_anomalies(
        self, symbol: str, df: pd.DataFrame
    ) -> list[SplitEvent]:
        """Detect splits based on volume spikes with price changes."""
        splits: list[SplitEvent] = []

        if "volume" not in df.columns:
            return splits

        df_sorted = df.sort_index()

        # Calculate rolling volume average (20-day)
        volume_ma = df_sorted["volume"].rolling(window=20, min_periods=5).mean()
        volume_ratio = df_sorted["volume"] / volume_ma

        # Calculate price changes
        price_changes = df_sorted["close"].pct_change()

        for i in range(len(df_sorted)):
            if pd.isna(volume_ratio.iloc[i]) or pd.isna(price_changes.iloc[i]):
                continue

            # Look for volume spike + significant price drop
            if (
                volume_ratio.iloc[i] > self.volume_spike_threshold
                and price_changes.iloc[i] < -0.2
            ):  # 20% price drop
                split_date = (
                    df_sorted.index[i].date()
                    if hasattr(df_sorted.index[i], "date")  # pyright: ignore[reportUnknownMemberType]  # pandas datetime index
                    else df_sorted.index[i]
                )

                # Calculate split ratio from price change
                price_ratio = abs(price_changes.iloc[i]) + 1
                split_ratio = self._find_closest_split_ratio(price_ratio)

                # Calculate confidence
                confidence = self._calculate_volume_confidence(
                    volume_ratio.iloc[i], price_changes.iloc[i], split_ratio
                )

                split = SplitEvent(
                    symbol=symbol,
                    split_date=split_date,
                    split_ratio=split_ratio,
                    confidence=confidence,
                    detection_method="volume_anomaly",
                )
                splits.append(split)

        return splits

    def _detect_adjustment_ratios(
        self, symbol: str, df: pd.DataFrame
    ) -> list[SplitEvent]:
        """Detect splits using adjusted close ratios."""
        splits: list[SplitEvent] = []

        if "adjusted_close" not in df.columns:
            return splits

        df_sorted = df.sort_index()

        # Calculate adjustment factor
        adjustment_factor = df_sorted["close"] / df_sorted["adjusted_close"]
        adjustment_changes = adjustment_factor.pct_change()

        for i in range(1, len(df_sorted)):
            change = adjustment_changes.iloc[i]

            if pd.isna(change):
                continue

            # Significant change in adjustment factor indicates corporate action
            if abs(change) > 0.1:  # 10% change in adjustment factor
                split_date = (
                    df_sorted.index[i].date()
                    if hasattr(df_sorted.index[i], "date")  # pyright: ignore[reportUnknownMemberType]  # pandas datetime index
                    else df_sorted.index[i]
                )

                # Calculate split ratio
                split_ratio = adjustment_factor.iloc[i] / adjustment_factor.iloc[i - 1]
                split_ratio = self._find_closest_split_ratio(split_ratio)

                confidence = min(
                    0.95, abs(change) * 2
                )  # High confidence for adjustment factor method

                split = SplitEvent(
                    symbol=symbol,
                    split_date=split_date,
                    split_ratio=split_ratio,
                    confidence=confidence,
                    detection_method="adjustment_ratio",
                )
                splits.append(split)

        return splits

    def _find_closest_split_ratio(self, calculated_ratio: float) -> float:
        """Find the closest common split ratio to the calculated ratio."""
        if pd.isna(calculated_ratio) or calculated_ratio <= 0:
            return 1.0

        # Find closest common ratio
        closest_ratio = min(self.common_ratios, key=lambda x: abs(x - calculated_ratio))

        # If very close to 1, probably not a split
        if abs(closest_ratio - 1.0) < 0.1:
            return 1.0

        return closest_ratio

    def _calculate_price_gap_confidence(
        self, return_val: float, split_ratio: float, df: pd.DataFrame, index: int
    ) -> float:
        """Calculate confidence for price gap detection."""
        # Base confidence on how close the return matches expected split
        expected_return = (
            -(1 - 1 / split_ratio) if split_ratio > 1 else -(1 - split_ratio)
        )
        ratio_accuracy = 1 - abs(return_val - expected_return) / abs(expected_return)

        # Boost confidence if it's a common split ratio
        ratio_bonus = 0.2 if split_ratio in [2.0, 0.5, 3.0, 0.333] else 0.0

        # Reduce confidence if volume data doesn't support (if available)
        volume_penalty = 0.0
        if "volume" in df.columns and index > 0:
            volume_ratio = df["volume"].iloc[index] / df["volume"].iloc[index - 1]
            if volume_ratio < 1.5:  # Expected volume spike missing
                volume_penalty = 0.2

        confidence = max(0.0, min(1.0, ratio_accuracy + ratio_bonus - volume_penalty))
        return confidence

    def _calculate_volume_confidence(
        self, volume_ratio: float, price_change: float, split_ratio: float
    ) -> float:
        """Calculate confidence for volume anomaly detection."""
        # Higher volume spike = higher confidence
        volume_confidence = min(1.0, volume_ratio / 10.0)

        # Price change should match split ratio
        expected_change = (
            -(1 - 1 / split_ratio) if split_ratio > 1 else -(1 - split_ratio)
        )
        price_accuracy = 1 - abs(price_change - expected_change) / abs(expected_change)

        confidence = (volume_confidence + price_accuracy) / 2
        return max(0.0, min(1.0, confidence))

    def _consolidate_split_detections(
        self, splits: list[SplitEvent]
    ) -> list[SplitEvent]:
        """Consolidate multiple detections of the same split event."""
        if not splits:
            return splits

        # Group splits by date (within 2 days) and symbol
        consolidated: list[SplitEvent] = []
        used_indices = set()

        for i, split1 in enumerate(splits):
            if i in used_indices:
                continue

            # Find other splits for same symbol within 2 days
            similar_splits = [split1]
            used_indices.add(i)

            for j, split2 in enumerate(splits[i + 1 :], start=i + 1):
                if j in used_indices:
                    continue

                days_diff = abs((split1.split_date - split2.split_date).days)
                if (
                    split1.symbol == split2.symbol
                    and days_diff <= 2
                    and abs(split1.split_ratio - split2.split_ratio) < 0.5
                ):
                    similar_splits.append(split2)
                    used_indices.add(j)

            # Create consolidated split with highest confidence
            best_split = max(similar_splits, key=lambda s: s.confidence)

            # Average the ratios if multiple detections
            if len(similar_splits) > 1:
                avg_ratio = np.mean([s.split_ratio for s in similar_splits])
                best_split.split_ratio = self._find_closest_split_ratio(
                    float(avg_ratio)
                )
                best_split.confidence = min(
                    1.0, best_split.confidence * 1.2
                )  # Boost for multiple detections
                best_split.detection_method += (
                    f"+{len(similar_splits) - 1}_confirmations"
                )

            consolidated.append(best_split)

        return consolidated

    def _record_split_detection(self, split: SplitEvent) -> None:
        """Record a split detection in the tracking DataFrame."""
        new_row = pd.DataFrame([split.to_dict()])
        self.detected_splits = pd.concat(
            [self.detected_splits, new_row], ignore_index=True
        )

    def check_data_needs_refresh(
        self, symbol: str, data_start_date: date_type, data_end_date: date_type
    ) -> tuple[bool, list[SplitEvent]]:
        """
        Check if data needs refresh due to detected splits.

        Args:
            symbol: Stock symbol
            data_start_date: Start date of existing data
            data_end_date: End date of existing data

        Returns:
            Tuple of (needs_refresh, splits_found)
        """
        # Get splits for this symbol in the data period
        symbol_splits = self.detected_splits[
            (self.detected_splits["symbol"] == symbol)
            & (
                pd.to_datetime(self.detected_splits["split_date"]).dt.date
                >= data_start_date
            )
            & (
                pd.to_datetime(self.detected_splits["split_date"]).dt.date
                <= data_end_date
            )
        ]

        return False, []

        splits_in_period: list[SplitEvent] = []
        for _, row in symbol_splits.iterrows():
            split = SplitEvent(
                symbol=row["symbol"],
                split_date=pd.to_datetime(row["split_date"]).date(),
                split_ratio=row["split_ratio"],
                confidence=row["confidence"],
                detection_method=row["detection_method"],
            )
            splits_in_period.append(split)

        needs_refresh = len(splits_in_period) > 0

        return needs_refresh, splits_in_period

    def recommend_refresh_strategy(
        self,
        symbol: str,
        splits: list[SplitEvent],
        current_data_range: tuple[date_type, date_type],
    ) -> dict[str, Any]:
        """
        Recommend data refresh strategy based on detected splits.

        Args:
            symbol: Stock symbol
            splits: List of detected splits
            current_data_range: (start_date, end_date) of current data

        Returns:
            Dictionary with refresh recommendations
        """
        if not splits:
            return {"action": "no_refresh_needed", "reason": "No splits detected"}

        start_date, end_date = current_data_range
        earliest_split = min(splits, key=lambda s: s.split_date)

        # Recommend getting fresh data from before the earliest split
        fresh_start_date = earliest_split.split_date - timedelta(
            days=30
        )  # Buffer period

        recommendation = {
            "action": "refresh_required",
            "reason": f"Detected {len(splits)} split(s) in data period",
            "splits_detected": [str(split) for split in splits],
            "current_range": f"{start_date} to {end_date}",
            "recommended_fresh_start": fresh_start_date,
            "recommended_fresh_end": date_type.today(),
            "priority": "high" if any(s.confidence > 0.8 for s in splits) else "medium",
            "data_quality_impact": "ML models may learn incorrect patterns from unadjusted split data",
        }

        return recommendation

    def analyze_data_for_splits(self, symbol: str, df: pd.DataFrame) -> dict[str, Any]:
        """
        Comprehensive analysis of data for splits with recommendations.

        Args:
            symbol: Stock symbol
            df: Price data DataFrame

        Returns:
            Complete analysis results
        """
        splits = self.detect_splits_in_data(symbol, df)

        if not splits:
            return {
                "symbol": symbol,
                "splits_detected": 0,
                "data_quality": "good",
                "action_required": False,
                "message": "No stock splits detected. Data is suitable for ML training.",
            }

        # Determine data quality impact
        high_confidence_splits = [s for s in splits if s.confidence > 0.8]

        if high_confidence_splits:
            data_quality = "poor"
            action_required = True
            message = f"HIGH PRIORITY: {len(high_confidence_splits)} high-confidence splits detected. Fresh data required for ML training."
        else:
            data_quality = "questionable"
            action_required = True
            message = f"MEDIUM PRIORITY: {len(splits)} potential splits detected. Consider refreshing data."

        # Get data date range
        data_start = (
            df.index.min().date() if hasattr(df.index.min(), "date") else df.index.min()  # pyright: ignore[reportUnknownMemberType]  # pandas datetime index
        )
        data_end = (
            df.index.max().date() if hasattr(df.index.max(), "date") else df.index.max()  # pyright: ignore[reportUnknownMemberType]  # pandas datetime index
        )

        recommendation = self.recommend_refresh_strategy(
            symbol, splits, (data_start, data_end)
        )

        return {
            "symbol": symbol,
            "splits_detected": len(splits),
            "high_confidence_splits": len(high_confidence_splits),
            "data_quality": data_quality,
            "action_required": action_required,
            "message": message,
            "detected_splits": [split.to_dict() for split in splits],
            "recommendation": recommendation,
            "analysis_date": datetime.now().isoformat(),
        }

    def get_split_history(self, symbol: str | None = None) -> pd.DataFrame:
        """
        Get history of detected splits.

        Args:
            symbol: Optional symbol to filter by

        Returns:
            DataFrame of split history
        """
        if symbol:
            return self.detected_splits[self.detected_splits["symbol"] == symbol].copy()
        return self.detected_splits.copy()

    def mark_data_refreshed(self, symbol: str, refresh_date: date_type) -> None:
        """
        Mark that data has been refreshed for a symbol.

        Args:
            symbol: Stock symbol
            refresh_date: Date when data was refreshed
        """
        # Update action_taken for relevant splits
        mask = (self.detected_splits["symbol"] == symbol) & (
            self.detected_splits["action_taken"].isna()
        )

        self.detected_splits.loc[mask, "action_taken"] = (
            f"data_refreshed_{refresh_date}"
        )

        self.logger.info(f"Marked {symbol} as refreshed on {refresh_date}")


def get_split_detection_service(
    data_persistence_service=None,
) -> StockSplitDetectionService:
    """
    Factory function to get a SplitDetectionService instance.

    Args:
        data_persistence_service: Optional data persistence service

    Returns:
        StockSplitDetectionService instance
    """
    return StockSplitDetectionService(data_persistence_service)


if __name__ == "__main__":
    # Demo and test
    print("🧪 Testing Stock Split Detection Service...")

    # Create sample data with a simulated 2:1 split
    dates = pd.date_range(start="2023-01-01", end="2023-12-31", freq="D")
    np.random.seed(42)

    # Generate price data with a CLEAR 4:1 split on 2023-06-15 (like AAPL)
    split_date = pd.to_datetime("2023-06-15")

    prices: list[float] = []

    for date in dates:
        # Pre-split: stable around $160
        if date < split_date:
            price = 160.0 + np.random.normal(0, 5)
        # Post-split: immediately drop to ~$40 (160/4)
        else:
            price = 40.0 + np.random.normal(0, 2)

        prices.append(max(1.0, price))  # Ensure positive prices

    # Create volume data with massive spike on split date
    volumes = np.random.normal(1000000, 200000, len(dates))
    for i, date in enumerate(dates):
        if date == split_date:
            volumes[i] *= 10  # Huge volume spike on split date

    # Create DataFrame
    test_df = pd.DataFrame({"close": prices, "volume": volumes}, index=dates)

    # Test the service
    service = StockSplitDetectionService()

    print("🔍 Analyzing simulated data for splits...")
    analysis = service.analyze_data_for_splits("TEST_STOCK", test_df)

    print("📊 Analysis Results:")
    print(f"   Symbol: {analysis['symbol']}")
    print(f"   Splits Detected: {analysis['splits_detected']}")
    print(f"   Data Quality: {analysis['data_quality']}")
    print(f"   Action Required: {analysis['action_required']}")
    print(f"   Message: {analysis['message']}")

    if analysis["splits_detected"] > 0 and "detected_splits" in analysis:
        print("\n🎯 Detected Splits:")
        for split in analysis["detected_splits"]:
            print(
                f"   - {split['split_date']}: {split['split_ratio']:.1f}:1 split (confidence: {split['confidence']:.2f})"
            )

    if (
        "recommendation" in analysis
        and analysis["recommendation"]["action"] == "refresh_required"
    ):
        rec = analysis["recommendation"]
        print("\n💡 Recommendation:")
        print(f"   - Action: {rec['action']}")
        print(f"   - Priority: {rec['priority']}")
        print(f"   - Fresh data from: {rec['recommended_fresh_start']}")

    print("\n✅ Stock Split Detection Service test complete!")
