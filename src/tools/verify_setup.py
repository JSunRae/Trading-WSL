#!/usr/bin/env python3
"""
@agent.tool verify_setup

Interactive Brokers Trading System - Setup Verification
Verifies that the system is properly installed and configured.
"""

import importlib
import json
import logging
import sys
from pathlib import Path
from typing import Any

# Schema definitions for agent tool pattern
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "skip_ib_test": {"type": "boolean", "default": False, "description": "Skip IB connection test"},
        "verbose": {"type": "boolean", "default": False, "description": "Enable verbose output"}
    }
}

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "success": {"type": "boolean", "description": "Overall verification success"},
        "checks_passed": {"type": "integer", "description": "Number of checks that passed"},
        "total_checks": {"type": "integer", "description": "Total number of checks"},
        "missing_dependencies": {"type": "array", "items": {"type": "string"}, "description": "List of missing dependencies"},
        "issues": {"type": "array", "items": {"type": "string"}, "description": "List of issues found"},
        "recommendations": {"type": "array", "items": {"type": "string"}, "description": "Recommended actions"}
    }
}

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)


def check_python_version():
    """Check if Python version is adequate."""
    logger.debug("Checking Python version...")
    version = sys.version_info
    if version.major >= 3 and version.minor >= 8:
        logger.debug(f"Python {version.major}.{version.minor}.{version.micro} - OK")
        return True
    else:
        logger.error(f"Python {version.major}.{version.minor}.{version.micro} - Need 3.8+")
        return False


def check_dependencies() -> tuple[bool, list[str]]:
    """Check if required packages are installed."""
    logger.debug("Checking dependencies...")
    required_packages = [
        "ib_async",
        "pandas",
        "numpy",
        "pytz",
        "requests",
        "joblib",
    ]

    missing: list[str] = []
    for package in required_packages:
        try:
            importlib.import_module(package)
            logger.debug(f"{package} - Available")
        except ImportError:
            logger.debug(f"{package} - Not installed")
            missing.append(package)

    return len(missing) == 0, missing


def check_project_structure():
    """Check if required directories exist."""
    logger.debug("Checking project structure...")
    project_root = Path(__file__).parent.parent

    required_dirs = [
        "src/core",
        "src/data",
        "src/services",
        "config",
        "data",
        "logs",
        "tests",
    ]

    all_good = True
    for dir_path in required_dirs:
        full_path = project_root / dir_path
        if full_path.exists():
            logger.debug(f"{dir_path} - Available")
        else:
            logger.debug(f"{dir_path} - Missing")
            all_good = False

    return all_good


def check_configuration():
    """Check if configuration files exist."""
    logger.debug("Checking configuration...")
    project_root = Path(__file__).parent.parent

    config_file = project_root / "config" / "config.json"
    if config_file.exists():
        logger.debug("config/config.json exists")
        return True
    else:
        logger.debug("config/config.json missing - copy from config.example.json")
        return False


def check_ib_connection() -> bool:
    """Test IB connection (basic connectivity test)."""
    logger.debug("Testing IB connection...")
    try:
        import asyncio

        from src.infra.ib_client import close_ib, get_ib

        async def test_connection():
            try:
                await get_ib()  # Test connection
                logger.debug("IB Paper Trading connection successful")
                await close_ib()
                return True
            except Exception as e:
                logger.debug(f"IB connection failed: {str(e)}")
                logger.debug("Make sure TWS/Gateway is running on port 7497")
                return False

        # Run the async test
        return asyncio.run(test_connection())

    except ImportError:
        logger.debug("ib_insync not available")
        return False


def main(skip_ib_test: bool = False, verbose: bool = False) -> dict[str, Any]:
    """Run all verification checks and return JSON results."""
    logger.info("Interactive Brokers Trading System - Setup Verification")

    checks = [
        ("Python Version", check_python_version),
        ("Dependencies", lambda: check_dependencies()[0]),
        ("Project Structure", check_project_structure),
        ("Configuration", check_configuration),
    ]

    if not skip_ib_test:
        checks.append(("IB Connection", check_ib_connection))

    results: list[tuple[str, bool]] = []
    issues: list[str] = []
    recommendations: list[str] = []

    for name, check_func in checks:
        try:
            result = check_func()
            results.append((name, result))
            if not result:
                issues.append(f"{name} check failed")
        except Exception as e:
            logger.error(f"{name} check failed: {e}")
            results.append((name, False))
            issues.append(f"{name} check failed: {str(e)}")

    # Get missing dependencies for recommendations
    _, missing_deps = check_dependencies()
    if missing_deps:
        recommendations.extend([
            f"Install missing dependency: {dep}" for dep in missing_deps
        ])

    passed = sum(1 for _, result in results if result)
    success = passed == len(results)

    if not success:
        recommendations.extend([
            "Install missing dependencies: pip install -r requirements.txt",
            "Copy config: cp config/config.example.json config/config.json",
            "Start TWS/Gateway on port 7497 for connection test"
        ])

    return {
        "success": success,
        "checks_passed": passed,
        "total_checks": len(results),
        "missing_dependencies": missing_deps,
        "issues": issues,
        "recommendations": recommendations
    }


def run_cli() -> int:
    """CLI wrapper for the tool."""
    import argparse

    parser = argparse.ArgumentParser(description="Verify IB trading system setup")
    parser.add_argument("--skip-ib-test", action="store_true",
                      help="Skip IB connection test")
    parser.add_argument("--verbose", action="store_true",
                      help="Enable verbose output")
    parser.add_argument("--describe", action="store_true",
                      help="Show tool schemas")

    args = parser.parse_args()

    if args.describe:
        print(json.dumps({
            "input_schema": INPUT_SCHEMA,
            "output_schema": OUTPUT_SCHEMA
        }, indent=2))
        return 0

    result = main(skip_ib_test=args.skip_ib_test, verbose=args.verbose)
    print(json.dumps(result, indent=2))

    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(run_cli())
