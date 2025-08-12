"""
Level 2 Data Replay and Analysis Tools

This module provides tools for replaying and analyzing recorded Level 2 data,
including order flow analysis, spoofing detection, and market microstructure insights.

Author: Trading Project
Date: 2025-07-28
"""

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import click
import matplotlib.pyplot as plt
import pandas as pd


@dataclass
class OrderFlowMetrics:
    """Metrics for order flow analysis."""

    timestamp: str
    bid_ask_spread: float
    mid_price: float
    total_bid_volume: int
    total_ask_volume: int
    volume_imbalance: float  # (bid_vol - ask_vol) / (bid_vol + ask_vol)
    price_impact: float
    effective_spread: float


class Level2Analyzer:
    """Analyzer for Level 2 market depth data."""

    def __init__(self, data_dir: str, symbol: str):
        self.data_dir = Path(data_dir)
        self.symbol = symbol.upper()
        self.snapshots_df: pd.DataFrame | None = None
        self.messages_df: pd.DataFrame | None = None

    def load_data(self, date: str) -> bool:
        """
        Load Level 2 data for a specific date.

        Args:
            date: Date string in YYYY-MM-DD format

        Returns:
            True if data loaded successfully
        """
        try:
            symbol_dir = self.data_dir / self.symbol

            # Find snapshot files for the date
            snapshot_files = list(symbol_dir.glob(f"{date}_snapshots_*.parquet"))
            if not snapshot_files:
                print(f"No snapshot files found for {self.symbol} on {date}")
                return False

            # Load and combine all snapshot files for the date
            dfs = []
            for file in snapshot_files:
                df = pd.read_parquet(file)
                dfs.append(df)

            self.snapshots_df = pd.concat(dfs, ignore_index=True)
            self.snapshots_df["timestamp"] = pd.to_datetime(
                self.snapshots_df["timestamp"]
            )
            self.snapshots_df = self.snapshots_df.sort_values("timestamp").reset_index(
                drop=True
            )

            print(
                f"Loaded {len(self.snapshots_df)} snapshots for {self.symbol} on {date}"
            )

            # Load message files if available
            message_files = list(symbol_dir.glob(f"{date}_messages_*.json"))
            if message_files:
                messages = []
                for file in message_files:
                    with open(file) as f:
                        file_messages = json.load(f)
                        messages.extend(file_messages)

                self.messages_df = pd.DataFrame(messages)
                self.messages_df["timestamp"] = pd.to_datetime(
                    self.messages_df["timestamp"]
                )
                self.messages_df = self.messages_df.sort_values(
                    "timestamp"
                ).reset_index(drop=True)

                print(
                    f"Loaded {len(self.messages_df)} messages for {self.symbol} on {date}"
                )

            return True

        except Exception as e:
            print(f"Error loading data: {e}")
            return False

    def calculate_order_flow_metrics(self) -> list[OrderFlowMetrics]:
        """Calculate order flow metrics from snapshots."""
        if self.snapshots_df is None:
            raise ValueError("No snapshot data loaded")

        metrics = []

        for _, row in self.snapshots_df.iterrows():
            try:
                # Parse price and size arrays
                bid_prices = (
                    eval(row["bid_prices"])
                    if isinstance(row["bid_prices"], str)
                    else row["bid_prices"]
                )
                bid_sizes = (
                    eval(row["bid_sizes"])
                    if isinstance(row["bid_sizes"], str)
                    else row["bid_sizes"]
                )
                ask_prices = (
                    eval(row["ask_prices"])
                    if isinstance(row["ask_prices"], str)
                    else row["ask_prices"]
                )
                ask_sizes = (
                    eval(row["ask_sizes"])
                    if isinstance(row["ask_sizes"], str)
                    else row["ask_sizes"]
                )

                # Filter out zero prices/sizes
                valid_bids = [
                    (p, s)
                    for p, s in zip(bid_prices, bid_sizes, strict=False)
                    if p > 0 and s > 0
                ]
                valid_asks = [
                    (p, s)
                    for p, s in zip(ask_prices, ask_sizes, strict=False)
                    if p > 0 and s > 0
                ]

                if not valid_bids or not valid_asks:
                    continue

                # Best bid/ask
                best_bid_price = max(p for p, s in valid_bids)
                best_ask_price = min(p for p, s in valid_asks)

                # Spread and mid price
                spread = best_ask_price - best_bid_price
                mid_price = (best_bid_price + best_ask_price) / 2

                # Volume calculations
                total_bid_volume = sum(s for p, s in valid_bids)
                total_ask_volume = sum(s for p, s in valid_asks)

                # Volume imbalance
                total_volume = total_bid_volume + total_ask_volume
                volume_imbalance = (
                    (total_bid_volume - total_ask_volume) / total_volume
                    if total_volume > 0
                    else 0
                )

                # Price impact (simplified - depth at 1% of mid price)
                impact_threshold = mid_price * 0.01
                bid_impact_vol = sum(
                    s for p, s in valid_bids if best_bid_price - p <= impact_threshold
                )
                ask_impact_vol = sum(
                    s for p, s in valid_asks if p - best_ask_price <= impact_threshold
                )
                price_impact = (bid_impact_vol + ask_impact_vol) / 2

                # Effective spread (half spread as percentage of mid price)
                effective_spread = (spread / 2) / mid_price * 10000  # in basis points

                metrics.append(
                    OrderFlowMetrics(
                        timestamp=row["timestamp"].isoformat(),
                        bid_ask_spread=spread,
                        mid_price=mid_price,
                        total_bid_volume=total_bid_volume,
                        total_ask_volume=total_ask_volume,
                        volume_imbalance=volume_imbalance,
                        price_impact=price_impact,
                        effective_spread=effective_spread,
                    )
                )

            except Exception as e:
                print(f"Error calculating metrics for row: {e}")
                continue

        return metrics

    def detect_spoofing_patterns(
        self, window_seconds: int = 60
    ) -> list[dict[str, Any]]:
        """
        Detect potential spoofing patterns in the order book.

        Args:
            window_seconds: Time window for pattern detection

        Returns:
            List of potential spoofing events
        """
        if self.messages_df is None:
            print("No message data available for spoofing detection")
            return []

        spoofing_events = []

        # Look for rapid add/remove patterns
        window_delta = timedelta(seconds=window_seconds)

        for i in range(len(self.messages_df) - 1):
            msg = self.messages_df.iloc[i]

            if msg["operation"] == "add":
                # Look for quick removal of the same order
                end_time = msg["timestamp"] + window_delta

                # Find potential removal of the same order
                mask = (
                    (self.messages_df["timestamp"] > msg["timestamp"])
                    & (self.messages_df["timestamp"] <= end_time)
                    & (self.messages_df["operation"] == "remove")
                    & (self.messages_df["side"] == msg["side"])
                    & (self.messages_df["level"] == msg["level"])
                    & (abs(self.messages_df["price"] - msg["price"]) < 0.01)
                )

                removals = self.messages_df[mask]

                if len(removals) > 0:
                    time_diff = (
                        removals.iloc[0]["timestamp"] - msg["timestamp"]
                    ).total_seconds()

                    # Flag as potential spoofing if removed within short time
                    if time_diff < 10:  # Less than 10 seconds
                        spoofing_events.append(
                            {
                                "timestamp": msg["timestamp"],
                                "side": msg["side"],
                                "level": msg["level"],
                                "price": msg["price"],
                                "size": msg["size"],
                                "removal_time": removals.iloc[0]["timestamp"],
                                "duration_seconds": time_diff,
                                "type": "quick_removal",
                            }
                        )

        print(f"Detected {len(spoofing_events)} potential spoofing events")
        return spoofing_events

    def generate_analysis_report(
        self, output_file: str | None = None
    ) -> dict[str, Any]:
        """Generate comprehensive analysis report."""
        if self.snapshots_df is None:
            raise ValueError("No data loaded")

        # Calculate metrics
        metrics = self.calculate_order_flow_metrics()
        metrics_df = pd.DataFrame([m.__dict__ for m in metrics])

        # Basic statistics
        report = {
            "symbol": self.symbol,
            "analysis_timestamp": datetime.now().isoformat(),
            "data_summary": {
                "total_snapshots": len(self.snapshots_df),
                "time_range": {
                    "start": self.snapshots_df["timestamp"].min().isoformat(),
                    "end": self.snapshots_df["timestamp"].max().isoformat(),
                },
                "duration_minutes": (
                    self.snapshots_df["timestamp"].max()
                    - self.snapshots_df["timestamp"].min()
                ).total_seconds()
                / 60,
            },
            "order_flow_stats": {
                "avg_spread_bps": metrics_df["effective_spread"].mean(),
                "avg_volume_imbalance": metrics_df["volume_imbalance"].mean(),
                "price_volatility": metrics_df["mid_price"].std(),
                "avg_bid_volume": metrics_df["total_bid_volume"].mean(),
                "avg_ask_volume": metrics_df["total_ask_volume"].mean(),
            },
        }

        # Spoofing analysis if message data available
        if self.messages_df is not None:
            spoofing_events = self.detect_spoofing_patterns()
            report["spoofing_analysis"] = {
                "total_events": len(spoofing_events),
                "events_per_hour": len(spoofing_events)
                / (report["data_summary"]["duration_minutes"] / 60),
                "events": spoofing_events[:10],  # First 10 events as examples
            }

        # Save report if output file specified
        if output_file:
            with open(output_file, "w") as f:
                json.dump(report, f, indent=2, default=str)
            print(f"Analysis report saved to {output_file}")

        return report

    def plot_order_book_evolution(
        self,
        start_time: str | None = None,
        end_time: str | None = None,
        save_file: str | None = None,
    ):
        """Plot order book evolution over time."""
        if self.snapshots_df is None:
            raise ValueError("No data loaded")

        # Filter by time range if specified
        df = self.snapshots_df.copy()
        if start_time:
            df = df[df["timestamp"] >= pd.to_datetime(start_time)]
        if end_time:
            df = df[df["timestamp"] <= pd.to_datetime(end_time)]

        # Calculate mid prices
        mid_prices = []
        spreads = []
        timestamps = []

        for _, row in df.iterrows():
            try:
                bid_prices = (
                    eval(row["bid_prices"])
                    if isinstance(row["bid_prices"], str)
                    else row["bid_prices"]
                )
                ask_prices = (
                    eval(row["ask_prices"])
                    if isinstance(row["ask_prices"], str)
                    else row["ask_prices"]
                )

                valid_bids = [p for p in bid_prices if p > 0]
                valid_asks = [p for p in ask_prices if p > 0]

                if valid_bids and valid_asks:
                    best_bid = max(valid_bids)
                    best_ask = min(valid_asks)
                    mid_price = (best_bid + best_ask) / 2
                    spread = best_ask - best_bid

                    mid_prices.append(mid_price)
                    spreads.append(spread)
                    timestamps.append(row["timestamp"])

            except Exception:
                continue

        # Create plots
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(15, 10), sharex=True)

        # Mid price plot
        ax1.plot(timestamps, mid_prices, linewidth=1, alpha=0.8)
        ax1.set_ylabel("Mid Price ($)")
        ax1.set_title(f"{self.symbol} Order Book Evolution")
        ax1.grid(True, alpha=0.3)

        # Spread plot
        ax2.plot(timestamps, spreads, linewidth=1, alpha=0.8, color="orange")
        ax2.set_ylabel("Bid-Ask Spread ($)")
        ax2.set_xlabel("Time")
        ax2.grid(True, alpha=0.3)

        plt.xticks(rotation=45)
        plt.tight_layout()

        if save_file:
            plt.savefig(save_file, dpi=300, bbox_inches="tight")
            print(f"Plot saved to {save_file}")

        plt.show()


@click.command()
@click.option("--describe", is_flag=True, help="Show tool description")
@click.option(
    "--data-dir", "-d", help="Data directory containing Level 2 files"
)
@click.option("--symbol", "-s", help="Stock symbol to analyze")
@click.option("--date", help="Date to analyze (YYYY-MM-DD)")
@click.option("--output", "-o", help="Output file for analysis report")
@click.option("--plot", is_flag=True, help="Generate plots")
def main(describe, data_dir, symbol, date, output, plot):
    """
    Analyze recorded Level 2 market depth data.

    Example:
    python analyze_depth.py -d ./data/level2 -s AAPL --date 2025-07-28 --plot
    """
    if describe:
        describe_info = {
            "name": "analyze_depth.py",
            "description": "Analyze recorded Level 2 market depth data for order flow and spoofing detection",
            "inputs": ["--data-dir", "--symbol", "--date", "--output", "--plot"],
            "outputs": ["JSON analysis report", "optional plots"],
            "dependencies": ["click", "pandas", "matplotlib"]
        }
        print(json.dumps(describe_info, indent=2))
        return

    if not data_dir or not symbol or not date:
        print("Error: --data-dir, --symbol, and --date are required when not using --describe")
        return

    print("=" * 60)
    print("📈 LEVEL 2 DATA ANALYZER")
    print("=" * 60)

    analyzer = Level2Analyzer(data_dir, symbol)

    if not analyzer.load_data(date):
        print("Failed to load data")
        return

    # Generate analysis report
    report = analyzer.generate_analysis_report(output)

    # Print summary
    print("\n📊 Analysis Summary:")
    print(f"Symbol: {report['symbol']}")
    print(f"Snapshots: {report['data_summary']['total_snapshots']:,}")
    print(f"Duration: {report['data_summary']['duration_minutes']:.1f} minutes")
    print(f"Avg Spread: {report['order_flow_stats']['avg_spread_bps']:.2f} bps")
    print(
        f"Avg Volume Imbalance: {report['order_flow_stats']['avg_volume_imbalance']:.3f}"
    )

    if "spoofing_analysis" in report:
        print(f"Spoofing Events: {report['spoofing_analysis']['total_events']}")

    # Generate plots if requested
    if plot:
        try:
            analyzer.plot_order_book_evolution(
                save_file=f"{symbol}_{date}_evolution.png"
            )
        except Exception as e:
            print(f"Error generating plots: {e}")


if __name__ == "__main__":
    main()
