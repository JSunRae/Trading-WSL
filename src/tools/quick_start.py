#!/usr/bin/env python3
"""Quick Start Guide for Trading Project (with unified --describe guard)."""

# --- ultra-early describe guard (keep above heavy imports) ---
from typing import Any

from src.tools._cli_helpers import emit_describe_early, print_json  # type: ignore


def tool_describe() -> dict[str, Any]:
    return {
        "name": "quick_start",
        "description": "Display project structure, IB setup guidance, and usage examples.",
        "inputs": {},
        "outputs": {"stdout": "Guidance text or schema"},
        "dependencies": [
            "config:IB_HOST",
            "config:IB_PAPER_PORT",
            "config:IB_LIVE_PORT",
        ],
        "examples": [
            "python -m src.tools.quick_start",
            "python -m src.tools.quick_start --describe",
        ],
    }


def describe() -> dict[str, Any]:  # backward compatibility
    return tool_describe()


if emit_describe_early(tool_describe):  # pragma: no cover
    raise SystemExit(0)
# ----------------------------------------------------------------

import sys
from pathlib import Path

from src.core.config import get_config  # heavy import after guard

# Add src directory to path
project_root = Path(__file__).parent
src_path = project_root / "src"
sys.path.insert(0, str(src_path))


def show_project_info():
    """Display project information and structure."""
    print("=" * 60)
    print("🚀 TRADING PROJECT - QUICK START GUIDE")
    print("=" * 60)

    print("\n📁 Project Structure:")
    structure = {
        "src/": "Main source code (trading modules)",
        "examples/": "Example scripts and demonstrations",
        "data/": "Data storage (ignored by git)",
        "config/": "Configuration files",
        "logs/": "Log files (ignored by git)",
        "tests/": "Unit tests",
        "docs/": "Documentation",
    }

    for folder, description in structure.items():
        print(f"  {folder:<15} - {description}")

    print("\n🔧 Key Files:")
    files = {
        "src/ib_Main.py": "Main trading application with Level 2 data",
        "src/ib_Trader.py": "Core trading functionality",
        "src/MasterPy_Trading.py": "Trading utilities and classes",
        "src/data/record_depth.py": "Level 2 market depth recorder",
        "src/data/analyze_depth.py": "Level 2 data analysis tools",
        "src/lib/ib_async_wrapper.py": "Modern async IB API wrapper",
        "src/automation/headless_gateway.py": "Automated IB Gateway management",
        "run_trading_fully_automated.py": "Fully automated trading script",
        "config/config.json": "Configuration settings",
        "pyproject.toml": "Project metadata, dependencies & modern Ruff config",
    }

    for file, description in files.items():
        print(f"  {file:<25} - {description}")


def check_ib_connection():
    """Check if IB connection is possible."""
    print("\n🔌 Interactive Brokers Connection:")
    print("  Before running the trading system:")
    print("  1. Install and start TWS (Trader Workstation) or IB Gateway")
    print("  2. Enable API connections in TWS/Gateway settings:")
    print("     - Go to API -> Settings")
    print("     - Enable 'Enable ActiveX and Socket Clients'")
    cfg = get_config()
    host = cfg.ib_connection.host
    paper_port = cfg.ib_connection.paper_port
    live_port = cfg.ib_connection.live_port
    print(f"     - Set Socket port: {paper_port} (paper trading) or {live_port} (live)")
    print(f"     - Add your computer's IP to trusted IPs ({host} for local)")
    print("  3. Update config/config.json with correct port and settings")


def show_usage_examples():
    """Show usage examples."""
    print("\n💡 Usage Examples:")

    print("\n  🚀 AUTOMATED TRADING (Recommended):")
    print("     python run_trading_fully_automated.py --symbols AAPL")
    print("     python setup_automated_trading.py      # One-time setup")

    print("\n  🔧 MANUAL SETUP:")
    print("     python verify_setup.py                 # Verify installation")
    print("     python src/ib_Main.py                  # Main trading app")

    print("\n  📊 EXAMPLES & TESTING:")
    print("     python examples/example_ib_qt_ticker_table.py")
    print("     python examples/example_Tkinter.py")

    print("\n  📈 LEVEL 2 DATA:")
    print("     python test_level2.py                          # Test connection")
    print("     python src/data/record_depth.py --symbol AAPL  # Record data")
    print("     make level2-record SYMBOL=AAPL DURATION=60     # Using Makefile")

    print("\n  🛠️ DEVELOPMENT TOOLS:")
    print("     ruff check . --fix     # Modern linting & auto-fix")
    print("     ruff format .          # Code formatting")
    print("     pyright               # Advanced type checking")
    print("     make verify           # Full verification")
    print("     make test            # Run test suite")


def show_next_steps():
    """Show next steps for customization."""
    print("\n🎯 Next Steps:")
    print("  1. Update config/config.json with your IB settings")
    print("  2. Test Level 2 recording: python test_level2.py")
    print("  3. Record sample data: make level2-record SYMBOL=AAPL DURATION=5")
    print("  4. Modify trading strategies in src/MasterPy_Trading.py")
    print("  5. Add your stock symbols and watchlists")
    print("  6. Test with paper trading first!")
    print("  7. Set up proper logging and monitoring")

    print("\n📊 Level 2 Data Features:")
    print("  - Real-time order book recording (100ms snapshots)")
    print("  - 10-level bid/ask data with nanosecond timestamps")
    print("  - Individual message logging for spoofing detection")
    print("  - Parquet storage for efficient analysis")
    print("  - Built-in analysis and visualization tools")

    print("\n⚠️  Important Reminders:")
    print("  - Always test with paper trading accounts first")
    print("  - Understand the risks of algorithmic trading")
    print("  - Monitor your positions and system status")
    print("  - Keep backups of your data and configurations")
    print("  - Ensure proper Level 2 data permissions with IB")


def main(argv: list[str] | None = None):
    import argparse

    parser = argparse.ArgumentParser(
        description="Quick start helper for the trading system"
    )
    parser.add_argument(
        "--describe",
        action="store_true",
        help="(Deprecated) Show JSON tool description and exit",
    )
    args = parser.parse_args(argv)

    if args.describe:  # legacy path
        return print_json(tool_describe())

    show_project_info()
    check_ib_connection()
    show_usage_examples()
    show_next_steps()

    print("\n" + "=" * 60)
    print("🎉 Your trading project is ready!")
    print("Start with 'python verify_setup.py' to test everything.")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
