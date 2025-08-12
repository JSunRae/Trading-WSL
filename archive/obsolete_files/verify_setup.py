#!/usr/bin/env python3
"""
Test script to verify the trading project setup.
Run this script to check if all dependencies are properly installed.
"""

import sys
from pathlib import Path


def test_dependencies():
    """Test that all required dependencies are available."""
    print("Testing dependencies...")

    dependencies = [
        ("pandas", "pd"),
        ("numpy", "np"),
        ("ib_async", None),
        ("ibapi", None),
        ("pytz", None),
        ("joblib", None),
        ("PyQt5", None),
        ("bs4", "BeautifulSoup"),
        ("requests", None),
        ("openpyxl", None),
    ]

    failed_imports = []

    for dep, alias in dependencies:
        try:
            if alias:
                exec(f"import {dep} as {alias}")
            else:
                exec(f"import {dep}")
            print(f"✓ {dep}")
        except ImportError as e:
            print(f"✗ {dep} - {e}")
            failed_imports.append(dep)

    if failed_imports:
        print(f"\nFailed to import: {', '.join(failed_imports)}")
        return False
    else:
        print("\nAll dependencies imported successfully!")
        return True


def test_project_structure():
    """Test that the project structure is correct."""
    print("\nTesting project structure...")

    project_root = Path(__file__).parent

    required_items = {
        "directories": ["src", "examples", "data", "config", "logs", "tests"],
        "files": ["README.md", "pyproject.toml", "requirements.txt", ".gitignore"],
    }

    missing_items = []

    for dir_name in required_items["directories"]:
        dir_path = project_root / dir_name
        if dir_path.exists():
            print(f"✓ Directory: {dir_name}")
        else:
            print(f"✗ Directory: {dir_name}")
            missing_items.append(f"directory: {dir_name}")

    for file_name in required_items["files"]:
        file_path = project_root / file_name
        if file_path.exists():
            print(f"✓ File: {file_name}")
        else:
            print(f"✗ File: {file_name}")
            missing_items.append(f"file: {file_name}")

    if missing_items:
        print(f"\nMissing items: {', '.join(missing_items)}")
        return False
    else:
        print("\nProject structure is correct!")
        return True


def test_basic_functionality():
    """Test basic functionality of key libraries."""
    print("\nTesting basic functionality...")

    try:
        # Test pandas
        import pandas as pd

        df = pd.DataFrame({"test": [1, 2, 3]})
        assert len(df) == 3
        print("✓ Pandas basic functionality")

        # Test numpy
        import numpy as np

        arr = np.array([1, 2, 3])
        assert arr.sum() == 6
        print("✓ NumPy basic functionality")

        # Test ib_async
        from ib_async import Stock

        stock = Stock("AAPL", "SMART", "USD")
        assert stock.symbol == "AAPL"
        print("✓ ib_async basic functionality")

        # Test pytz
        import pytz

        tz = pytz.timezone("US/Eastern")
        assert tz is not None
        print("✓ pytz basic functionality")

        print("\nAll basic functionality tests passed!")
        return True

    except Exception as e:
        print(f"✗ Basic functionality test failed: {e}")
        return False


def main():
    """Run all tests."""
    print("=" * 60)
    print("TRADING PROJECT SETUP VERIFICATION")
    print("=" * 60)

    tests = [
        ("Dependencies", test_dependencies),
        ("Project Structure", test_project_structure),
        ("Basic Functionality", test_basic_functionality),
    ]

    results = []
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"Error running {test_name} test: {e}")
            results.append((test_name, False))

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)

    all_passed = True
    for test_name, result in results:
        status = "PASS" if result else "FAIL"
        print(f"{test_name}: {status}")
        if not result:
            all_passed = False

    if all_passed:
        print("\n🎉 All tests passed! Your trading project is ready to use.")
        print("\nNext steps:")
        print("1. Copy config/config.example.json to config/config.json")
        print("2. Update config.json with your IB connection settings")
        print("3. Start Interactive Brokers TWS or Gateway")
        print("4. Run: python src/ib_main.py")
    else:
        print("\n❌ Some tests failed. Please check the errors above.")
        sys.exit(1)


if __name__ == "__main__":
    main()
