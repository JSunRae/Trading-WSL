#!/usr/bin/env python3
# ruff: noqa: E402
"""
Interactive Brokers Trading System - Setup Verification
Verifies that the system is properly installed and configured.

Adds standardized --describe JSON output.
"""

import importlib
import json
import logging
import sys
from pathlib import Path
from typing import Any

try:  # optional config import for --describe resilience
    from src.core.config import get_config  # type: ignore
except Exception:  # pragma: no cover

    def get_config():  # type: ignore
        class C:
            host = "127.0.0.1"
            gateway_paper_port = 4002
            gateway_live_port = 4001
            paper_port = 7497
            live_port = 7496
            client_id = 1

        class Dummy:
            ib_connection = C()

        return Dummy()


def _describe() -> dict[str, Any]:
    cfg = get_config().ib_connection
    return {
        "name": "verify_setup",
        "description": "Verify installation, dependencies, configuration files, and (optionally) IB connectivity.",
        "inputs": {
            "--skip-ib-test": {"type": "flag", "required": False, "default": False},
            "--verbose": {"type": "flag", "required": False, "default": False},
            "--describe": {"type": "flag", "required": False, "default": False},
        },
        "outputs": {"stdout": "JSON summary of verification checks", "files": []},
        "dependencies": [
            "config:IB_HOST",
            "config:IB_GATEWAY_PAPER_PORT",
            "config:IB_GATEWAY_LIVE_PORT",
            "config:IB_PAPER_PORT",
            "config:IB_LIVE_PORT",
            "optional:ib_async",
        ],
        "examples": [
            "python -m src.tools.verify_setup --describe",
            "python -m src.tools.verify_setup --skip-ib-test",
            "python -m src.tools.verify_setup --verbose",
        ],
        "ports": {
            "gateway_paper": cfg.gateway_paper_port,
            "gateway_live": cfg.gateway_live_port,
            "tws_paper": cfg.paper_port,
            "tws_live": cfg.live_port,
        },
        "version": "1.0.0",
    }


# Setup logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def check_python_version():
    """Check if Python version is adequate."""
    logger.debug("Checking Python version...")
    version = sys.version_info
    if version.major >= 3 and version.minor >= 8:
        logger.debug(f"Python {version.major}.{version.minor}.{version.micro} - OK")
        return True
    else:
        logger.error(
            f"Python {version.major}.{version.minor}.{version.micro} - Need 3.8+"
        )
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
                cfg = get_config().ib_connection
                logger.debug(
                    "Ensure IB Gateway/TWS is running on one of: "
                    f"gateway_paper={cfg.gateway_paper_port}, gateway_live={cfg.gateway_live_port}, "
                    f"tws_paper={cfg.paper_port}, tws_live={cfg.live_port}"
                )
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
        recommendations.extend(
            [f"Install missing dependency: {dep}" for dep in missing_deps]
        )

    passed = sum(1 for _, result in results if result)
    success = passed == len(results)

    if not success:
        cfg = get_config().ib_connection
        recommendations.extend(
            [
                "Install missing dependencies: pip install -r requirements.txt",
                "Copy config: cp config/config.example.json config/config.json",
                (
                    "Start IB Gateway/TWS (paper: "
                    f"{cfg.gateway_paper_port}/{cfg.paper_port}, live: {cfg.gateway_live_port}/{cfg.live_port})"
                ),
            ]
        )

    return {
        "success": success,
        "checks_passed": passed,
        "total_checks": len(results),
        "missing_dependencies": missing_deps,
        "issues": issues,
        "recommendations": recommendations,
    }


def run_cli() -> int:
    """CLI wrapper for the tool."""
    import argparse

    parser = argparse.ArgumentParser(description="Verify IB trading system setup")
    parser.add_argument(
        "--skip-ib-test", action="store_true", help="Skip IB connection test"
    )
    parser.add_argument("--verbose", action="store_true", help="Enable verbose output")
    parser.add_argument("--describe", action="store_true", help="Show tool schemas")

    args = parser.parse_args()

    if args.describe:
        print(json.dumps(_describe(), indent=2))
        return 0

    result = main(skip_ib_test=args.skip_ib_test, verbose=args.verbose)
    print(json.dumps(result, indent=2))

    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(run_cli())
