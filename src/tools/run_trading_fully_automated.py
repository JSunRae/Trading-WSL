#!/usr/bin/env python3
"""
FULLY AUTOMATED TRADING SCRIPT
===============================

Just run this script - no manual intervention required!

This script:
1. Automatically starts IB Gateway in headless mode
2. Logs in with your credentials
3. Connects to the API
4. Downloads market data
5. Runs your trading analysis
6. Cleans up everything automatically

Usage:
    python run_trading_fully_automated.py --symbol TSLA --duration "1 D"

Environment Variables (recommended):
    export IB_USERNAME="your_username"
    export IB_PASSWORD="your_password"

Or create .env file:
    echo "IB_USERNAME=your_username" > .env
    echo "IB_PASSWORD=your_password" >> .env
"""

import argparse
import asyncio
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

# Add project to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# Import our modules
from src.automation.headless_gateway import HeadlessGateway
from src.lib.ib_async_wrapper import IBAsync


async def fully_automated_trading(
    symbols: list,
    duration: str = "1 D",
    bar_size: str = "1 min",
    paper_trading: bool = True,
    save_data: bool = True,
) -> bool:
    """
    Complete automated trading pipeline

    Args:
        symbols: List of symbols to analyze (e.g., ['TSLA', 'AAPL'])
        duration: Data duration (e.g., "1 D", "5 D", "1 W")
        bar_size: Bar size (e.g., "1 min", "5 mins", "1 hour")
        paper_trading: Use paper trading (True) or live (False)
        save_data: Save data to files (True) or just analyze (False)

    Returns:
        True if successful, False otherwise
    """
    # Setup logging
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
    )
    logger = logging.getLogger(__name__)

    # Get credentials
    username = os.getenv("IB_USERNAME")
    password = os.getenv("IB_PASSWORD")

    if not username or not password:
        logger.error("❌ Please set IB_USERNAME and IB_PASSWORD environment variables")
        logger.info("💡 Run: export IB_USERNAME='your_username'")
        logger.info("💡 Run: export IB_PASSWORD='your_password'")
        return False

    gateway = None
    ib = None
    success_count = 0

    try:
        logger.info("🚀 Starting Fully Automated Trading Pipeline")
        logger.info("=" * 60)

        # Step 1: Start Gateway automatically
        logger.info("🔧 Step 1: Starting IB Gateway automatically...")
        gateway = HeadlessGateway(
            username=username, password=password, paper_trading=paper_trading
        )

        if not await gateway.start_gateway():
            logger.error("❌ Failed to start IB Gateway")
            return False

        logger.info("✅ IB Gateway running and ready!")

        # Step 2: Connect to API
        logger.info("🔌 Step 2: Connecting to IB API...")
        ib = IBAsync()

        port = 4002 if paper_trading else 4001
        if not await ib.connect("127.0.0.1", port, 1):
            logger.error("❌ Failed to connect to IB API")
            return False

        logger.info("✅ Connected to IB API!")

        # Step 3: Process each symbol
        logger.info(f"📊 Step 3: Processing {len(symbols)} symbols...")

        all_data = {}

        for i, symbol in enumerate(symbols, 1):
            logger.info(f"📈 Processing {symbol} ({i}/{len(symbols)})...")

            try:
                # Create contract
                contract = ib.create_stock_contract(symbol)

                # Download historical data
                df = await ib.req_historical_data(contract, duration, bar_size)

                if df is None or df.empty:
                    logger.warning(f"⚠️  No data received for {symbol}")
                    continue

                logger.info(f"✅ Downloaded {len(df)} bars for {symbol}")

                # Store data
                all_data[symbol] = df

                # Basic analysis
                latest_price = df["close"].iloc[-1]
                avg_price = df["close"].mean()
                price_change = (
                    (latest_price - df["close"].iloc[0]) / df["close"].iloc[0]
                ) * 100
                volatility = df["close"].pct_change().std() * 100

                logger.info(f"💰 {symbol} Analysis:")
                logger.info(f"   Latest: ${latest_price:.2f}")
                logger.info(f"   Average: ${avg_price:.2f}")
                logger.info(f"   Change: {price_change:+.2f}%")
                logger.info(f"   Volatility: {volatility:.2f}%")

                # Simple signal
                if latest_price > avg_price * 1.02:  # 2% above average
                    signal = "🔥 STRONG BUY"
                elif latest_price > avg_price:
                    signal = "📈 BUY"
                elif latest_price < avg_price * 0.98:  # 2% below average
                    signal = "🔻 STRONG SELL"
                else:
                    signal = "📉 SELL"

                logger.info(f"   Signal: {signal}")

                success_count += 1

                # Small delay between requests
                if i < len(symbols):
                    await asyncio.sleep(1)

            except Exception as e:
                logger.error(f"❌ Error processing {symbol}: {e}")
                continue

        # Step 4: Save data if requested
        if save_data and all_data:
            logger.info("💾 Step 4: Saving data...")

            # Create data directory
            data_dir = Path("data") / "automated_trading"
            data_dir.mkdir(parents=True, exist_ok=True)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

            for symbol, df in all_data.items():
                # Save as Parquet (efficient)
                parquet_file = (
                    data_dir
                    / f"{symbol}_{duration.replace(' ', '_')}_{bar_size.replace(' ', '_')}_{timestamp}.parquet"
                )
                df.to_parquet(parquet_file)

                # Save as CSV (readable)
                csv_file = (
                    data_dir
                    / f"{symbol}_{duration.replace(' ', '_')}_{bar_size.replace(' ', '_')}_{timestamp}.csv"
                )
                df.to_csv(csv_file)

                logger.info(f"💾 Saved {symbol} data: {parquet_file}")

            # Create summary report
            summary_file = data_dir / f"trading_summary_{timestamp}.txt"
            with open(summary_file, "w") as f:
                f.write("AUTOMATED TRADING SUMMARY\n")
                f.write("=" * 50 + "\n")
                f.write(f"Timestamp: {datetime.now()}\n")
                f.write(f"Symbols: {', '.join(symbols)}\n")
                f.write(f"Duration: {duration}\n")
                f.write(f"Bar Size: {bar_size}\n")
                f.write(f"Trading Mode: {'Paper' if paper_trading else 'Live'}\n")
                f.write(
                    f"Success Rate: {success_count}/{len(symbols)} ({success_count / len(symbols) * 100:.1f}%)\n\n"
                )

                for symbol, df in all_data.items():
                    latest_price = df["close"].iloc[-1]
                    avg_price = df["close"].mean()
                    price_change = (
                        (latest_price - df["close"].iloc[0]) / df["close"].iloc[0]
                    ) * 100

                    f.write(f"{symbol}:\n")
                    f.write(f"  Latest Price: ${latest_price:.2f}\n")
                    f.write(f"  Average Price: ${avg_price:.2f}\n")
                    f.write(f"  Price Change: {price_change:+.2f}%\n")
                    f.write(f"  Data Points: {len(df)}\n\n")

            logger.info(f"📄 Created summary: {summary_file}")

        # Step 5: Results
        logger.info("📊 Step 5: Results Summary")
        logger.info("=" * 40)
        logger.info(
            f"✅ Successfully processed: {success_count}/{len(symbols)} symbols"
        )
        logger.info(f"📈 Data timeframe: {duration}")
        logger.info(f"⏱️  Bar size: {bar_size}")
        logger.info(f"🎯 Trading mode: {'Paper' if paper_trading else 'Live'}")

        if all_data:
            total_bars = sum(len(df) for df in all_data.values())
            logger.info(f"📊 Total data points: {total_bars:,}")

        return success_count > 0

    except KeyboardInterrupt:
        logger.info("🛑 Interrupted by user")
        return False

    except Exception as e:
        logger.error(f"❌ Unexpected error: {e}")
        return False

    finally:
        # Step 6: Cleanup
        logger.info("🧹 Step 6: Cleaning up...")

        if ib:
            try:
                await ib.disconnect()
                logger.info("✅ Disconnected from IB API")
            except Exception as e:
                logger.warning(f"Warning during IB disconnect: {e}")

        if gateway:
            try:
                await gateway.stop_gateway()
                logger.info("✅ IB Gateway stopped")
            except Exception as e:
                logger.warning(f"Warning during Gateway shutdown: {e}")

        logger.info("🎉 Automated trading pipeline complete!")


def load_env_file():
    """Load environment variables from .env file if it exists"""
    env_file = Path(".env")
    if env_file.exists():
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    os.environ[key] = value


def main():
    """Main entry point"""
    # Load .env file if it exists
    load_env_file()

    parser = argparse.ArgumentParser(
        description="Fully Automated Trading System",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run_trading_fully_automated.py --symbols TSLA
  python run_trading_fully_automated.py --symbols AAPL MSFT GOOGL --duration "5 D"
  python run_trading_fully_automated.py --symbols SPY --bar-size "5 mins" --no-save
        """,
    )

    parser.add_argument(
        "--describe",
        action="store_true",
        help="Show tool description and exit"
    )
    parser.add_argument(
        "--symbols",
        nargs="+",
        default=["TSLA"],
        help="Stock symbols to analyze (default: TSLA)",
    )
    parser.add_argument(
        "--duration", default="1 D", help="Data duration (default: 1 D)"
    )
    parser.add_argument("--bar-size", default="1 min", help="Bar size (default: 1 min)")
    parser.add_argument(
        "--live", action="store_true", help="Use live trading (default: paper trading)"
    )
    parser.add_argument(
        "--no-save",
        action="store_true",
        help="Don't save data files (default: save data)",
    )
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")

    args = parser.parse_args()

    if args.describe:
        describe_info = {
            "name": "run_trading_fully_automated.py",
            "description": "Fully automated trading system that manages IB Gateway and runs trading analysis",
            "inputs": ["--symbols", "--duration", "--bar-size", "--live", "--no-save", "--verbose"],
            "outputs": ["data/automated_trading/*.parquet", "data/automated_trading/*.csv", "logs/automated_trading.log"],
            "dependencies": ["src.automation.headless_gateway", "src.lib.ib_async_wrapper", "ib_insync", "pandas"]
        }
        print(json.dumps(describe_info, indent=2))
        return 0

    # Setup logging level
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Validate symbols
    symbols = [s.upper().strip() for s in args.symbols]

    print("🚀 FULLY AUTOMATED TRADING SYSTEM")
    print("=" * 50)
    print(f"📊 Symbols: {', '.join(symbols)}")
    print(f"⏱️  Duration: {args.duration}")
    print(f"📈 Bar Size: {args.bar_size}")
    print(f"🎯 Mode: {'Live Trading' if args.live else 'Paper Trading'}")
    print(f"💾 Save Data: {'No' if args.no_save else 'Yes'}")
    print()

    # Check credentials
    if not os.getenv("IB_USERNAME") or not os.getenv("IB_PASSWORD"):
        print("❌ CREDENTIALS REQUIRED")
        print("Please set your IB credentials:")
        print()
        print("Option 1 - Environment Variables:")
        print("  export IB_USERNAME='your_username'")
        print("  export IB_PASSWORD='your_password'")
        print()
        print("Option 2 - Create .env file:")
        print("  echo 'IB_USERNAME=your_username' > .env")
        print("  echo 'IB_PASSWORD=your_password' >> .env")
        print()
        return 1

    print("✅ Credentials found!")
    print("🚀 Starting automated pipeline...")
    print()

    # Run the automated pipeline
    try:
        success = asyncio.run(
            fully_automated_trading(
                symbols=symbols,
                duration=args.duration,
                bar_size=args.bar_size,
                paper_trading=not args.live,
                save_data=not args.no_save,
            )
        )

        if success:
            print()
            print("🎉 SUCCESS! Automated trading completed successfully!")
            print("📊 Check the 'data/automated_trading' folder for results")
            return 0
        else:
            print()
            print("❌ FAILED! Check logs for details")
            return 1

    except KeyboardInterrupt:
        print("\n🛑 Stopped by user")
        return 0
    except Exception as e:
        print(f"\n❌ FATAL ERROR: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
