#!/usr/bin/env python3
# ruff: noqa: C901,I001,E402
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
from typing import Any
from collections.abc import Sequence

import pandas as pd

project_root = Path(__file__).parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from src.automation.headless_gateway import HeadlessGateway
from src.infra.ib_conn import get_ib_connect_plan, try_connect_candidates
from src.lib.ib_async_wrapper import IBAsync

try:
    from src.core.config import get_config
    from src.services.market_data.artifact_check import (
        compute_bars_gaps as _compute_bars_gaps,
    )

    has_gap_api = True
except Exception:  # pragma: no cover

    def get_config(*_args, **_kwargs) -> Any:  # type: ignore
        class DummyIB:
            host = "127.0.0.1"
            gateway_paper_port = 4002
            gateway_live_port = 4001
            client_id = 1

        class Dummy:
            ib_connection = DummyIB()

        return Dummy()

    has_gap_api = False
    _compute_bars_gaps = None  # type: ignore[assignment]


async def fully_automated_trading(
    symbols: list[str],
    duration: str = "1 D",
    bar_size: str = "1 min",
    paper_trading: bool = True,
    save_data: bool = True,
    resume_gaps: bool = True,
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
        plan = get_ib_connect_plan()
        logger.info(
            "🔌 IB connection plan: host=%s candidates=%s clientId=%s",
            plan["host"],
            plan["candidates"],
            plan["client_id"],
        )
        ok, used_port = await try_connect_candidates(
            ib.connect,
            plan["host"],
            plan["candidates"],
            int(plan["client_id"]),
            autostart=True,
        )
        if not ok:
            logger.error("❌ Failed to connect to IB API with planned candidates")
            return False
        logger.info("✅ Connected to IB API on port %s!", used_port)

        async def _fetch_per_gap(
            symbol: str,
            bar_size: str,
            gaps_list: Sequence[Any],
        ) -> pd.DataFrame | None:
            """Issue one IB request per gap window and merge results.

            - Converts ISO-like gap times to IB endDateTime and duration strings.
            - Filters each returned frame to the exact [start, end] window.
            - Merges frames (outer) and sorts by index.
            """
            contract = ib.create_stock_contract(symbol)
            frames: list[pd.DataFrame] = []
            # Decide RTH behavior by bar granularity, mirroring backfill defaults
            use_rth = False if "sec" in bar_size else True
            for gap in gaps_list:
                start_iso: str
                end_iso: str
                try:
                    start_iso = str(gap.get("start", ""))  # type: ignore[call-arg, attr-defined]
                    end_iso = str(gap.get("end", ""))  # type: ignore[call-arg, attr-defined]
                except Exception:
                    try:
                        start_iso = str(gap["start"])  # type: ignore[index]
                        end_iso = str(gap["end"])  # type: ignore[index]
                    except Exception:
                        continue
                if len(start_iso) < 19 or len(end_iso) < 19:
                    continue
                try:
                    start_dt = datetime.fromisoformat(start_iso.replace("Z", ""))
                    end_dt = datetime.fromisoformat(end_iso.replace("Z", ""))
                    if end_dt <= start_dt:
                        continue
                    duration_s = int((end_dt - start_dt).total_seconds())
                    # IB expects duration like 'NNN S' for fine windows
                    duration_str = f"{max(1, duration_s)} S"
                    end_dt_str = end_dt.strftime("%Y%m%d %H:%M:%S")
                    df_part = await ib.req_historical_data(
                        contract,
                        duration=duration_str,
                        bar_size=bar_size,
                        end_datetime=end_dt_str,
                        use_rth=use_rth,
                    )
                    if df_part is None or df_part.empty:
                        continue
                    # filter to exact window
                    try:
                        df_part = df_part.loc[
                            (df_part.index >= start_dt) & (df_part.index <= end_dt)
                        ]
                    except Exception:
                        pass
                    frames.append(df_part)
                except Exception:
                    continue
            if not frames:
                return None
            try:
                df_all = pd.concat(frames).sort_index()
                # drop duplicates by index if any
                df_all = df_all[~df_all.index.duplicated(keep="last")]
                return df_all
            except Exception:
                return None

        # Step 3: Process each symbol
        logger.info(f"📊 Step 3: Processing {len(symbols)} symbols...")
        all_data: dict[str, pd.DataFrame] = {}
        for i, symbol in enumerate(symbols, 1):
            logger.info(f"📈 Processing {symbol} ({i}/{len(symbols)})...")
            try:
                contract = ib.create_stock_contract(symbol)
                # Gap-aware targeted fetches per gap window
                if resume_gaps and has_gap_api and _compute_bars_gaps is not None:
                    try:
                        today_str = datetime.now().strftime("%Y-%m-%d")
                        gaps_info = _compute_bars_gaps(symbol, today_str, bar_size)
                        if gaps_info.get("needed"):
                            gap_list = list(gaps_info.get("gaps") or [])
                            if gap_list:
                                logger.info(
                                    "Gap-aware fetch for %s %s: %d window(s)",
                                    symbol,
                                    bar_size,
                                    len(gap_list),
                                )
                                df_gap = await _fetch_per_gap(
                                    symbol, bar_size, gap_list
                                )
                                if df_gap is not None and not df_gap.empty:
                                    df = df_gap
                                    logger.info(
                                        "✅ Downloaded %d bars for %s via %d gap window(s)",
                                        len(df),
                                        symbol,
                                        len(gap_list),
                                    )
                                    all_data[symbol] = df
                                    # Basic analysis + pacing
                                    latest_price = df["close"].iloc[-1]
                                    avg_price = df["close"].mean()
                                    price_change = (
                                        (latest_price - df["close"].iloc[0])
                                        / df["close"].iloc[0]
                                    ) * 100
                                    volatility = df["close"].pct_change().std() * 100
                                    logger.info(f"💰 {symbol} Analysis:")
                                    logger.info(f"   Latest: ${latest_price:.2f}")
                                    logger.info(f"   Average: ${avg_price:.2f}")
                                    logger.info(f"   Change: {price_change:+.2f}%")
                                    logger.info(f"   Volatility: {volatility:.2f}%")
                                    if latest_price > avg_price * 1.02:
                                        signal = "🔥 STRONG BUY"
                                    elif latest_price > avg_price:
                                        signal = "📈 BUY"
                                        signal = "🔻 STRONG SELL"
                                    else:
                                        signal = "📉 SELL"
                                    logger.info(f"   Signal: {signal}")
                                    success_count += 1
                                    if i < len(symbols):
                                        await asyncio.sleep(1)
                                    continue
                    except Exception:
                        # fall through to generic request
                        pass

                # Fallback: single generic request (optionally aligned to policy end)
                end_dt_str: str | None = None
                if resume_gaps and has_gap_api and _compute_bars_gaps is not None:
                    try:
                        today_str = datetime.now().strftime("%Y-%m-%d")
                        gaps_info = _compute_bars_gaps(symbol, today_str, bar_size)
                        target_end = (gaps_info.get("target_window") or {}).get("end")
                        if target_end and len(target_end) >= 19:
                            dt_obj = datetime.fromisoformat(target_end.replace("Z", ""))
                            end_dt_str = dt_obj.strftime("%Y%m%d %H:%M:%S")
                    except Exception:
                        end_dt_str = None

                df = await ib.req_historical_data(
                    contract, duration, bar_size, end_datetime=end_dt_str
                )
                if df is None or df.empty:
                    logger.warning(f"⚠️  No data received for {symbol}")
                    continue
                logger.info(f"✅ Downloaded {len(df)} bars for {symbol}")
                all_data[symbol] = df
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
                if latest_price > avg_price * 1.02:
                    signal = "🔥 STRONG BUY"
                elif latest_price > avg_price:
                    signal = "📈 BUY"
                elif latest_price < avg_price * 0.98:
                    signal = "🔻 STRONG SELL"
                else:
                    signal = "📉 SELL"
                logger.info(f"   Signal: {signal}")
                success_count += 1
                if i < len(symbols):
                    await asyncio.sleep(1)
            except Exception as e:  # pragma: no cover
                logger.error(f"❌ Error processing {symbol}: {e}")
                continue

        # Step 4: Save data if requested
        if save_data and all_data:
            logger.info("💾 Step 4: Saving data...")
            data_dir = Path("data") / "automated_trading"
            data_dir.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            for symbol, df in all_data.items():
                parquet_file = (
                    data_dir
                    / f"{symbol}_{duration.replace(' ', '_')}_{bar_size.replace(' ', '_')}_{timestamp}.parquet"
                )
                df.to_parquet(parquet_file)
                csv_file = (
                    data_dir
                    / f"{symbol}_{duration.replace(' ', '_')}_{bar_size.replace(' ', '_')}_{timestamp}.csv"
                )
                df.to_csv(csv_file)
                logger.info(f"💾 Saved {symbol} data: {parquet_file}")
                try:
                    _append_bars_manifest(parquet_file, symbol, bar_size, df)
                except Exception:
                    pass
            summary_file = data_dir / f"trading_summary_{timestamp}.txt"
            with summary_file.open("w") as f:
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
        with env_file.open() as f:
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
        "--describe", action="store_true", help="Show tool description and exit"
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
    parser.add_argument(
        "--no-resume-gaps",
        action="store_true",
        help="Disable gap-aware planning for bars; always fetch based on duration/window",
    )
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")

    args = parser.parse_args()

    if args.describe:
        cfg = get_config().ib_connection
        describe_info = {
            "name": "run_trading_fully_automated",
            "description": "Fully automated trading pipeline (starts gateway, downloads data, runs analysis).",
            "inputs": [
                "--symbols",
                "--duration",
                "--bar-size",
                "--live",
                "--no-save",
                "--no-resume-gaps",
                "--verbose",
            ],
            "outputs": [
                "data/automated_trading/*.parquet",
                "data/automated_trading/*.csv",
                "data/automated_trading/trading_summary_*.txt",
            ],
            "env_keys": [
                "IB_USERNAME",
                "IB_PASSWORD",
                "IB_HOST",
                "IB_GATEWAY_PAPER_PORT",
                "IB_GATEWAY_LIVE_PORT",
                "IB_CLIENT_ID",
            ],
            "defaults": {
                "host": cfg.host,
                "gateway_paper_port": cfg.gateway_paper_port,
                "gateway_live_port": cfg.gateway_live_port,
                "client_id": cfg.client_id,
            },
            "dependencies": [
                "src.automation.headless_gateway",
                "src.lib.ib_async_wrapper",
                "ib_async",
                "pandas",
            ],
            "examples": [
                "python -m src.tools.run_trading_fully_automated --symbols TSLA",
                "python -m src.tools.run_trading_fully_automated --symbols AAPL MSFT --duration '5 D'",
                "python -m src.tools.run_trading_fully_automated --symbols SPY --bar-size '5 mins' --no-save",
            ],
            "version": "1.0.0",
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
                resume_gaps=not args.no_resume_gaps,
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


def _append_bars_manifest(
    path: Path, symbol: str, bar_size: str, df: pd.DataFrame
) -> None:
    """Append a JSONL entry for any saved bars to enable fast discovery.

    Schema mirrors auto_backfill bars manifest writer.
    """
    try:
        from src.core.config import get_config  # local import to avoid early heavy deps
    except Exception:  # pragma: no cover
        return

    cfg = get_config()
    manifest_path = cfg.data_paths.base_path / "bars_download_manifest.jsonl"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)

    time_start: str | None = None
    time_end: str | None = None
    try:
        idx = getattr(df, "index", None)
        if isinstance(idx, pd.DatetimeIndex) and len(idx) > 0:
            # Use first/last to avoid extra type-check noise on min/max
            t_start = idx[0].to_pydatetime()
            t_end = idx[-1].to_pydatetime()
            time_start = t_start.isoformat()
            time_end = t_end.isoformat()
    except Exception:
        time_start = None
        time_end = None

    record = {
        "schema_version": "bars_manifest.v1",
        "written_at": datetime.now().isoformat(),
        "vendor": "IBKR",
        "file_format": "parquet",
        "symbol": symbol,
        "bar_size": bar_size,
        "path": str(path),
        "filename": path.name,
        "rows": int(len(df)) if hasattr(df, "__len__") else 0,
        "columns": list(df.columns) if hasattr(df, "columns") else [],
        "time_start": time_start,
        "time_end": time_end,
    }

    with manifest_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    sys.exit(main())
