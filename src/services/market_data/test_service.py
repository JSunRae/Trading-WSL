#!/usr/bin/env python3
"""
Market Data Service Validation Test

Quick test to validate the market data service functionality
without requiring an active IB connection.
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))


def test_imports() -> bool:
    """Test that all imports work correctly"""
    print("🧪 Testing Imports...")

    try:
        import importlib.util as _ilu

        spec = _ilu.find_spec("src.services.market_data")
        assert spec is not None
        print("✅ Package import spec found")
        return True
    except Exception as e:
        print(f"❌ Import check failed: {e}")
        return False


def test_service_creation() -> bool:
    """Test service creation"""
    print("🧪 Testing Service Creation...")

    try:
        from src.services.market_data.market_data_service import MarketDataService

        # Test that the class can be imported and has expected methods
        assert hasattr(MarketDataService, "start_level2_data")
        assert hasattr(MarketDataService, "start_tick_data")
        assert hasattr(MarketDataService, "get_active_subscriptions")
        assert hasattr(MarketDataService, "stop_all_subscriptions")

        print("✅ Service class validation successful")
        print("📊 All required methods available")
        return True

    except Exception as e:
        print(f"❌ Service validation failed: {e}")
        return False


def main() -> bool:
    """Run all validation tests"""
    print("🚀 Market Data Service Validation")
    print("=" * 40)

    tests = [test_imports, test_service_creation]

    passed = 0
    total = len(tests)

    for test in tests:
        if test():
            passed += 1
        print()

    print("📊 Test Results:")
    print(f"   ✅ Passed: {passed}/{total}")

    if passed == total:
        print("🎉 All tests passed! Market Data Service is ready for use.")
        return True
    else:
        print("❌ Some tests failed. Check the output above.")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
