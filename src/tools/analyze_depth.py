"""Level 2 Market Depth Analysis Tool.

Restored logic with standardized ultra-early --describe guard. The guard must
remain at the very top to avoid importing heavy optional modules (pandas,
matplotlib) when only metadata is requested.
"""

# --- ultra-early describe guard (do NOT move below heavy imports) ---
from typing import Any, cast

from src.tools._cli_helpers import emit_describe_early, print_json  # type: ignore


def tool_describe() -> dict[str, Any]:  # standardized schema (must reflect actual CLI)
    return {
        "name": "analyze_depth",
        "description": "Analyze market depth snapshots or streams.",
        "inputs": {
            "--data-dir": {"type": "str", "required": False},
            "--symbol": {"type": "str", "required": False},
            "--date": {"type": "str", "required": False},
            "--output": {"type": "str", "required": False},
            "--plot": {"type": "flag", "required": False},
            "--show-describe": {"type": "flag", "required": False},
        },
        "outputs": {"stdout": "analysis summary JSON"},
        "dependencies": ["optional:ib_async", "config:ML_BASE_PATH"],
        "examples": ["python -m src.tools.analyze_depth --describe"],
    }


def describe() -> dict[str, Any]:  # backward compat wrapper used by --show-describe
    return tool_describe()


if emit_describe_early(tool_describe):  # pragma: no cover
    raise SystemExit(0)
# -----------------------------------------------------------------------------

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

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
            dfs: list[pd.DataFrame] = []
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
                messages: list[dict[str, Any]] = []
                for file in message_files:
                    for_json = file  # Path object
                    with for_json.open() as f:
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
        """Calculate order flow metrics from snapshots (restored logic)."""
        if self.snapshots_df is None:  # guard
            raise ValueError("No snapshot data loaded")

        metrics: list[OrderFlowMetrics] = []
        for _, row in self.snapshots_df.iterrows():
            try:
                # Parse price and size arrays (stored as list or repr string)
                bid_prices = (
                    eval(row["bid_prices"])  # noqa: S307 (trusted internal data)
                    if isinstance(row["bid_prices"], str)
                    else row["bid_prices"]
                )
                bid_sizes = (
                    eval(row["bid_sizes"])  # noqa: S307
                    if isinstance(row["bid_sizes"], str)
                    else row["bid_sizes"]
                )
                ask_prices = (
                    eval(row["ask_prices"])  # noqa: S307
                    if isinstance(row["ask_prices"], str)
                    else row["ask_prices"]
                )
                ask_sizes = (
                    eval(row["ask_sizes"])  # noqa: S307
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

                best_bid_price = max(p for p, _s in valid_bids)
                best_ask_price = min(p for p, _s in valid_asks)
                spread = best_ask_price - best_bid_price
                mid_price = (best_bid_price + best_ask_price) / 2
                total_bid_volume = sum(s for _p, s in valid_bids)
                total_ask_volume = sum(s for _p, s in valid_asks)
                total_volume = total_bid_volume + total_ask_volume
                volume_imbalance = (
                    (total_bid_volume - total_ask_volume) / total_volume
                    if total_volume > 0
                    else 0
                )
                impact_threshold = mid_price * 0.01
                bid_impact_vol = sum(
                    s for p, s in valid_bids if best_bid_price - p <= impact_threshold
                )
                ask_impact_vol = sum(
                    s for p, s in valid_asks if p - best_ask_price <= impact_threshold
                )
                price_impact = (bid_impact_vol + ask_impact_vol) / 2
                effective_spread = (spread / 2) / mid_price * 10000  # bps

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
            except Exception as e:  # defensive per-row
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

        spoofing_events: list[dict[str, Any]] = []

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

                removals = cast("pd.DataFrame", self.messages_df[mask])

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
            data_summary = cast(dict[str, Any], report["data_summary"])  # type: ignore[index]
            duration_minutes_val = float(
                cast(float, data_summary.get("duration_minutes", 0.0)) or 0.0
            )
            events_per_hour = (
                (len(spoofing_events) / (duration_minutes_val / 60.0))
                if duration_minutes_val > 0
                else 0.0
            )
            report["spoofing_analysis"] = {
                "total_events": len(spoofing_events),
                "events_per_hour": events_per_hour,
                "events": spoofing_events[:10],  # First 10 events as examples
            }

        # Save report if output file specified
        if output_file:
            from pathlib import Path as _Path

            with _Path(output_file).open("w") as f:
                json.dump(report, f, indent=2, default=str)
            print(f"Analysis report saved to {output_file}")

        return report

    def plot_order_book_evolution(
        self,
        start_time: str | None = None,
        end_time: str | None = None,
        save_file: str | None = None,
    ) -> None:
        """Plot order book evolution over time (restored indentation)."""
        if self.snapshots_df is None:
            raise ValueError("No data loaded")

        df = self.snapshots_df.copy()
        if start_time:
            df = df[df["timestamp"] >= pd.to_datetime(start_time)]
        if end_time:
            df = df[df["timestamp"] <= pd.to_datetime(end_time)]

        mid_prices: list[float] = []
        spreads: list[float] = []
        timestamps: list[pd.Timestamp] = []
        for _, row in df.iterrows():
            try:
                bid_prices = (
                    eval(row["bid_prices"])  # noqa: S307
                    if isinstance(row["bid_prices"], str)
                    else row["bid_prices"]
                )
                ask_prices = (
                    eval(row["ask_prices"])  # noqa: S307
                    if isinstance(row["ask_prices"], str)
                    else row["ask_prices"]
                )
                valid_bids = [p for p in bid_prices if p > 0]
                valid_asks = [p for p in ask_prices if p > 0]
                if valid_bids and valid_asks:
                    best_bid = max(valid_bids)
                    best_ask = min(valid_asks)
                    mid_prices.append((best_bid + best_ask) / 2)
                    spreads.append(best_ask - best_bid)
                    timestamps.append(row["timestamp"])
            except Exception:
                continue
        _fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(15, 10), sharex=True)  # noqa: F841  # type: ignore[assignment]
        ax1.plot(timestamps, mid_prices, linewidth=1, alpha=0.8)  # type: ignore[attr-defined]
        ax1.set_ylabel("Mid Price ($)")
        ax1.set_title(f"{self.symbol} Order Book Evolution")
        ax1.grid(True, alpha=0.3)
        ax2.plot(timestamps, spreads, linewidth=1, alpha=0.8, color="orange")  # type: ignore[attr-defined]
        ax2.set_ylabel("Bid-Ask Spread ($)")
        ax2.set_xlabel("Time")
        ax2.grid(True, alpha=0.3)
        plt.xticks(rotation=45)  # type: ignore[attr-defined]
        plt.tight_layout()  # type: ignore[attr-defined]
        if save_file:
            plt.savefig(save_file, dpi=300, bbox_inches="tight")  # type: ignore[attr-defined]
            print(f"Plot saved to {save_file}")
        plt.show()  # type: ignore[attr-defined]


## legacy describe() handled above; early guard removed (now centralized)


@click.command()
@click.option(
    "--show-describe",
    "show_describe",
    is_flag=True,
    help="Show tool description and exit",
)
@click.option("--data-dir", "-d", help="Data directory containing Level 2 files")
@click.option("--symbol", "-s", help="Stock symbol to analyze")
@click.option("--date", help="Date to analyze (YYYY-MM-DD)")
@click.option("--output", "-o", help="Output file for analysis report")
@click.option("--plot", is_flag=True, help="Generate plots")
def main(
    show_describe: bool,
    data_dir: str | None,
    symbol: str | None,
    date: str | None,
    output: str | None,
    plot: bool,
) -> None:
    """
    Analyze recorded Level 2 market depth data.

    Example:
    python analyze_depth.py -d ./data/level2 -s AAPL --date 2025-07-28 --plot
    """
    if show_describe:  # early pure-JSON describe path
        print_json(describe())
        return

    if not data_dir or not symbol or not date:
        print(
            "Error: --data-dir, --symbol, and --date are required when not using --describe"
        )
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


if __name__ == "__main__":  # pragma: no cover
    main()
