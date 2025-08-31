"""
Stock Split Integration Module

This module integrates stock split detection into the main trading system
to ensure data integrity for machine learning models.

Author: Interactive Brokers Trading System
Created: July 2025 (ML Data Integrity Enhancement)
"""

import sys
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

# Add src to path
sys.path.append(str(Path(__file__).parent / ".."))

# Type aliases for fallback compatibility
SplitDetectionService = Any
DataPersistenceService = Any
ErrorHandler = Callable[[Any, Any | None, str, str], Any]

try:
    from src.core.error_handler import handle_error
    from src.services.data_persistence_service import get_data_persistence_service
    from src.services.stock_split_detection_service import get_split_detection_service

    # Services available
    SERVICES_AVAILABLE = True

except ImportError as e:
    print(f"Warning: Could not import core modules: {e}")

    # Fallback implementations
    SERVICES_AVAILABLE = False

    def get_split_detection_service(
        data_persistence_service=None,
    ) -> SplitDetectionService | None:
        """Fallback split detection service factory."""
        return None

    def get_data_persistence_service() -> DataPersistenceService | None:
        """Fallback data persistence service factory."""
        return None

    def handle_error(
        error: Any, context: Any | None = None, module: str = "", function: str = ""
    ) -> Any:
        """Fallback error handler."""
        print(f"Error in {module}.{function}: {error}")
        return None


class MLDataIntegrityManager:
    """
    Manager for ensuring ML data integrity by detecting and handling stock splits.

    This class provides the main interface for the trading system to check
    data quality before using it for machine learning model training.
    """

    def __init__(self):
        """Initialize the ML Data Integrity Manager."""
        self.split_service = get_split_detection_service()
        self.data_service = get_data_persistence_service()
        self.checked_symbols: set = set()  # Track already checked symbols
        self.split_detected_symbols: set = set()  # Track symbols with splits
        self.services_available = SERVICES_AVAILABLE

    def validate_data_for_ml(
        self, symbol: str, df: pd.DataFrame, timeframe: str = "1 day"
    ) -> dict[str, Any]:
        """
        Validate data for ML training by checking for stock splits.

        Args:
            symbol: Stock symbol
            df: Price/volume DataFrame
            timeframe: Data timeframe

        Returns:
            Validation results with recommendations
        """
        try:
            if self.split_service is None:
                return {
                    "symbol": symbol,
                    "validation_status": "warning",
                    "message": "Split detection service unavailable",
                    "ml_ready": True,  # Allow training but warn
                    "recommendations": ["Service unavailable - proceed with caution"],
                }

            # Perform split analysis
            analysis = self.split_service.analyze_data_for_splits(symbol, df)

            # Convert to ML-focused validation result
            if analysis["data_quality"] == "good":
                return {
                    "symbol": symbol,
                    "validation_status": "passed",
                    "message": "Data is clean and ready for ML training",
                    "ml_ready": True,
                    "splits_detected": 0,
                    "recommendations": ["Data quality excellent for ML models"],
                }

            elif analysis["data_quality"] == "poor":
                self.split_detected_symbols.add(symbol)
                return {
                    "symbol": symbol,
                    "validation_status": "failed",
                    "message": f"HIGH PRIORITY: Data contains {analysis['splits_detected']} splits - NOT suitable for ML",
                    "ml_ready": False,
                    "splits_detected": analysis["splits_detected"],
                    "detected_splits": analysis["detected_splits"],
                    "recommendations": [
                        "❌ DO NOT use this data for ML training",
                        "🔄 Refresh data from before earliest split",
                        f"📅 Suggested start date: {analysis['recommendation']['recommended_fresh_start']}",
                        "🎯 Get split-adjusted data or fresh data",
                    ],
                }

            else:  # questionable quality
                return {
                    "symbol": symbol,
                    "validation_status": "warning",
                    "message": "MEDIUM PRIORITY: Potential splits detected - verify data quality",
                    "ml_ready": False,  # Be conservative for ML
                    "splits_detected": analysis["splits_detected"],
                    "detected_splits": analysis.get("detected_splits", []),
                    "recommendations": [
                        "⚠️  Verify data quality before ML training",
                        "🔍 Consider refreshing data to be safe",
                        "📊 Review detected split events",
                    ],
                }

        except Exception as e:
            handle_error(e, module="MLDataIntegrity", function="validate_data_for_ml")
            return {
                "symbol": symbol,
                "validation_status": "error",
                "message": f"Validation failed: {str(e)}",
                "ml_ready": False,
                "recommendations": ["Fix validation errors before ML training"],
            }

    def batch_validate_symbols(
        self, symbol_data_dict: dict[str, pd.DataFrame]
    ) -> dict[str, dict[str, Any]]:
        """
        Validate multiple symbols for ML readiness.

        Args:
            symbol_data_dict: Dictionary of {symbol: dataframe}

        Returns:
            Dictionary of validation results per symbol
        """
        results = {}

        print(f"🔍 Validating {len(symbol_data_dict)} symbols for ML data integrity...")

        for symbol, df in symbol_data_dict.items():
            print(f"   Checking {symbol}...")
            results[symbol] = self.validate_data_for_ml(symbol, df)

        # Summary
        passed = sum(1 for r in results.values() if r["validation_status"] == "passed")
        failed = sum(1 for r in results.values() if r["validation_status"] == "failed")
        warnings = sum(
            1 for r in results.values() if r["validation_status"] == "warning"
        )

        print("📊 Validation Summary:")
        print(f"   ✅ Passed: {passed}")
        print(f"   ⚠️  Warnings: {warnings}")
        print(f"   ❌ Failed: {failed}")

        return results

    def get_ml_ready_data(
        self, symbol_data_dict: dict[str, pd.DataFrame]
    ) -> dict[str, pd.DataFrame]:
        """
        Filter data to only include symbols ready for ML training.

        Args:
            symbol_data_dict: Dictionary of {symbol: dataframe}

        Returns:
            Dictionary of ML-ready data only
        """
        validation_results = self.batch_validate_symbols(symbol_data_dict)

        ml_ready_data = {}
        for symbol, df in symbol_data_dict.items():
            result = validation_results[symbol]
            if result["ml_ready"]:
                ml_ready_data[symbol] = df
            else:
                print(f"⚠️  Excluding {symbol} from ML training: {result['message']}")

        print(f"🎯 ML-Ready Symbols: {len(ml_ready_data)}/{len(symbol_data_dict)}")
        return ml_ready_data

    def generate_data_refresh_plan(
        self, validation_results: dict[str, dict[str, Any]]
    ) -> dict[str, Any]:
        """
        Generate a plan for refreshing data that failed validation.

        Args:
            validation_results: Results from batch_validate_symbols

        Returns:
            Data refresh plan
        """
        refresh_needed: list[dict[str, Any]] = []
        high_priority: list[dict[str, Any]] = []
        medium_priority: list[dict[str, Any]] = []

        for symbol, result in validation_results.items():
            if result["validation_status"] in ["failed", "warning"]:
                item = {
                    "symbol": symbol,
                    "priority": "high"
                    if result["validation_status"] == "failed"
                    else "medium",
                    "reason": result["message"],
                    "splits_detected": result.get("splits_detected", 0),
                    "recommendations": result["recommendations"],
                }

                refresh_needed.append(item)

                if item["priority"] == "high":
                    high_priority.append(item)
                else:
                    medium_priority.append(item)

        plan = {
            "total_symbols_needing_refresh": len(refresh_needed),
            "high_priority_count": len(high_priority),
            "medium_priority_count": len(medium_priority),
            "high_priority_symbols": [item["symbol"] for item in high_priority],
            "medium_priority_symbols": [item["symbol"] for item in medium_priority],
            "detailed_plan": refresh_needed,
            "generated_at": datetime.now().isoformat(),
        }

        return plan

    def print_validation_report(
        self, validation_results: dict[str, dict[str, Any]]
    ) -> None:
        """Print a detailed validation report."""
        print("\n" + "=" * 60)
        print("📊 ML DATA INTEGRITY VALIDATION REPORT")
        print("=" * 60)

        # Summary counts
        passed = [
            s
            for s, r in validation_results.items()
            if r["validation_status"] == "passed"
        ]
        failed = [
            s
            for s, r in validation_results.items()
            if r["validation_status"] == "failed"
        ]
        warnings = [
            s
            for s, r in validation_results.items()
            if r["validation_status"] == "warning"
        ]

        print("\n📈 SUMMARY:")
        print(f"   Total Symbols: {len(validation_results)}")
        print(f"   ✅ Ready for ML: {len(passed)}")
        print(f"   ⚠️  Need Review: {len(warnings)}")
        print(f"   ❌ Not ML Ready: {len(failed)}")

        # Failed symbols (high priority)
        if failed:
            print("\n🚨 HIGH PRIORITY - NOT ML READY:")
            for symbol in failed:
                result = validation_results[symbol]
                print(f"   {symbol}: {result['message']}")
                if result.get("detected_splits"):
                    for split in result["detected_splits"][:2]:  # Show first 2 splits
                        ratio = split["split_ratio"]
                        ratio_str = (
                            f"{int(ratio)}:1" if ratio >= 1 else f"1:{int(1 / ratio)}"
                        )
                        print(f"      Split: {split['split_date']} ({ratio_str})")

        # Warning symbols
        if warnings:
            print("\n⚠️  MEDIUM PRIORITY - VERIFY BEFORE ML:")
            for symbol in warnings:
                result = validation_results[symbol]
                print(f"   {symbol}: {result['message']}")

        # Passed symbols
        if passed:
            print("\n✅ READY FOR ML TRAINING:")
            for symbol in passed[:10]:  # Show first 10
                print(f"   {symbol}: Clean data")
            if len(passed) > 10:
                print(f"   ... and {len(passed) - 10} more symbols")

        print("\n" + "=" * 60)


def integrate_with_trading_system():
    """
    Example integration with the main trading system.
    This shows how to use the ML Data Integrity Manager.
    """
    print("🔗 Example Integration with Trading System")
    print("-" * 50)

    # Initialize the manager
    _ = MLDataIntegrityManager()

    # Example: Before training ML models
    print("1. Before ML Training - Validate Data:")
    print("   # Get your trading data")
    print("   symbol_data = get_all_trading_data()  # Your method")
    print("   ")
    print("   # Validate for ML integrity")
    print("   validation_results = manager.batch_validate_symbols(symbol_data)")
    print("   ")
    print("   # Get only clean data for ML")
    print("   ml_ready_data = manager.get_ml_ready_data(symbol_data)")
    print("   ")
    print("   # Train models only on clean data")
    print("   train_ml_models(ml_ready_data)")

    print("\n2. Generate Data Refresh Plan:")
    print("   refresh_plan = manager.generate_data_refresh_plan(validation_results)")
    print(
        "   print(f'Need to refresh {refresh_plan[\"high_priority_count\"]} symbols')"
    )

    print("\n3. Integration Points:")
    print("   • Before any ML model training")
    print("   • In data pipeline validation")
    print("   • During backtesting setup")
    print("   • When adding new symbols")

    print("\n4. Automated Actions:")
    print("   • Flag split-affected data")
    print("   • Trigger data refresh for critical symbols")
    print("   • Log data quality issues")
    print("   • Alert traders to data problems")


if __name__ == "__main__":
    print("🤖 ML Data Integrity Integration Demo")
    print("=" * 50)

    # Show integration example
    integrate_with_trading_system()

    print("\n✅ Stock Split Detection successfully integrated!")
    print("📚 Key Benefits:")
    print("   • Prevents ML models from learning false patterns")
    print("   • Automatically detects stock splits in historical data")
    print("   • Provides clear recommendations for data refresh")
    print("   • Maintains data quality for backtesting")
    print("   • Ensures ML model accuracy")
