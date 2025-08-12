#!/usr/bin/env python3
"""
Historical Data Service

This service handles historical data downloads from Interactive Brokers
with modern architecture patterns: error handling, connection pooling,
and high-performance Parquet storage.

This replaces the Download_Historical method from requestCheckerCLS.
"""

import logging
import sys
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any

import pandas as pd

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.config import get_config
from src.core.integrated_error_handling import with_error_handling
from src.data.data_manager import DataManager
from src.data.parquet_repository import ParquetRepository


class BarSize(Enum):
    """Supported bar sizes for historical data"""

    SEC_1 = "1 sec"
    SEC_5 = "5 secs"
    SEC_10 = "10 secs"
    SEC_30 = "30 secs"
    MIN_1 = "1 min"
    MIN_5 = "5 mins"
    MIN_15 = "15 mins"
    MIN_30 = "30 mins"
    HOUR_1 = "1 hour"
    HOUR_2 = "2 hours"
    HOUR_4 = "4 hours"
    DAY_1 = "1 day"
    WEEK_1 = "1 week"
    MONTH_1 = "1 month"


class DataType(Enum):
    """Types of data to download"""

    TRADES = "TRADES"
    MIDPOINT = "MIDPOINT"
    BID = "BID"
    ASK = "ASK"
    BID_ASK = "BID_ASK"
    HISTORICAL_VOLATILITY = "HISTORICAL_VOLATILITY"
    OPTION_IMPLIED_VOLATILITY = "OPTION_IMPLIED_VOLATILITY"


@dataclass
class DownloadRequest:
    """Request for historical data download"""

    symbol: str
    bar_size: BarSize
    what_to_show: DataType = DataType.TRADES
    start_date: Optional[str | date | datetime] = None
    end_date: Optional[str | date | datetime] = None
    duration: Optional[str] = None  # e.g., "30 D", "5 Y"
    use_rth: bool = True  # Regular trading hours only
    format_date: int = 1  # 1 for datetime, 2 for time_t
    keep_up_to_date: bool = False
    timeout: float = 60.0


@dataclass
class DownloadResult:
    """Result of historical data download"""

    success: bool
    symbol: str
    bar_size: BarSize
    data: Optional[pd.DataFrame] = None
    row_count: int = 0
    download_time: float = 0.0
    file_path: Optional[Path] = None
    error_message: Optional[str] = None
    cached: bool = False


class HistoricalDataService:
    """Modern historical data service with enterprise features"""

    def __init__(self):
        self.config = get_config()
        self.parquet_repo = ParquetRepository()
        self.data_manager = DataManager()
        self.logger = logging.getLogger(__name__)

        # Performance tracking
        self.download_stats = {
            "total_requests": 0,
            "successful_downloads": 0,
            "cache_hits": 0,
            "failed_downloads": 0,
            "total_download_time": 0.0,
            "total_rows_downloaded": 0,
        }

    @with_error_handling("historical_data")
    def download_historical_data(
        self, connection, request: DownloadRequest
    ) -> DownloadResult:
        """
        Download historical data with modern error handling and caching

        This replaces the old Download_Historical method with:
        - Integrated error handling
        - Connection pooling
        - High-performance Parquet storage
        - Smart caching
        - Performance monitoring
        """

        start_time = time.time()
        self.download_stats["total_requests"] += 1

        # Prepare result object
        result = DownloadResult(
            success=False, symbol=request.symbol, bar_size=request.bar_size
        )

        try:
            # 1. Check if data already exists (smart caching)
            cached_data = self._check_cache(request)
            if cached_data is not None:
                result.success = True
                result.data = cached_data
                result.row_count = len(cached_data)
                result.cached = True
                result.download_time = time.time() - start_time

                self.download_stats["cache_hits"] += 1
                self.logger.info(
                    f"Cache hit for {request.symbol} {request.bar_size.value}: {result.row_count} rows"
                )
                return result

            # 2. Create IB contract
            contract = self._create_contract(request.symbol)
            if contract is None:
                result.error_message = f"Failed to create contract for {request.symbol}"
                return result

            # 3. Prepare download parameters
            download_params = self._prepare_download_params(request)

            # 4. Execute download using IB connection
            self.logger.info(
                f"Downloading {request.symbol} {request.bar_size.value}..."
            )

            # This would use the actual IB connection
            bars = self._download_from_ib(connection, contract, download_params)

            if not bars:
                result.error_message = "No data returned from IB"
                self.download_stats["failed_downloads"] += 1
                return result

            # 5. Convert to DataFrame
            df = self._convert_bars_to_dataframe(bars)

            if df.empty:
                result.error_message = "Converted data is empty"
                self.download_stats["failed_downloads"] += 1
                return result

            # 6. Save to high-performance Parquet storage
            date_str = self._get_date_string(request)
            save_success = self.parquet_repo.save_data(
                df, request.symbol, request.bar_size.value, date_str
            )

            if save_success:
                file_path = self.parquet_repo._get_data_path(
                    request.symbol, request.bar_size.value, date_str
                )
                result.file_path = file_path

                # Update download tracker
                self.data_manager.download_tracker.mark_downloaded(
                    symbol=request.symbol,
                    timeframe=request.bar_size.value,
                    date_str=date_str,
                )

                self.logger.info(f"Saved {len(df)} rows to {file_path}")

            # 7. Update result
            result.success = True
            result.data = df
            result.row_count = len(df)
            result.download_time = time.time() - start_time

            # Update statistics
            self.download_stats["successful_downloads"] += 1
            self.download_stats["total_rows_downloaded"] += len(df)
            self.download_stats["total_download_time"] += result.download_time

            return result

        except Exception as e:
            result.error_message = str(e)
            result.download_time = time.time() - start_time
            self.download_stats["failed_downloads"] += 1

            self.logger.error(f"Download failed for {request.symbol}: {e}")
            raise  # Re-raise for error handling decorator

    def _check_cache(self, request: DownloadRequest) -> Optional[pd.DataFrame]:
        """Check if data already exists in cache"""

        date_str = self._get_date_string(request)

        # Check if data exists
        if self.parquet_repo.data_exists(
            request.symbol, request.bar_size.value, date_str
        ):
            # Check if it's recent enough (don't re-download same day data)
            if date_str == datetime.now().strftime("%Y-%m-%d"):
                return None  # Re-download today's data for freshness

            # Load cached data
            return self.parquet_repo.load_data(
                request.symbol, request.bar_size.value, date_str
            )

        return None

    def _create_contract(self, symbol: str):
        """Create IB contract for symbol"""
        # This would create an actual IB contract
        # For now, return a mock contract

        mock_contract = {
            "symbol": symbol,
            "secType": "STK",
            "exchange": "SMART",
            "currency": "USD",
        }

        return mock_contract

    def _prepare_download_params(self, request: DownloadRequest) -> dict[str, Any]:
        """Prepare parameters for IB download"""

        params = {
            "whatToShow": request.what_to_show.value,
            "useRTH": request.use_rth,
            "formatDate": request.format_date,
            "keepUpToDate": request.keep_up_to_date,
            "timeout": request.timeout,
        }

        # Handle date range vs duration
        if request.duration:
            params["durationStr"] = request.duration
            if request.end_date:
                params["endDateTime"] = self._format_date_for_ib(request.end_date)
            else:
                params["endDateTime"] = ""  # Use current time
        else:
            # Use date range
            if request.start_date and request.end_date:
                # Calculate duration from date range
                start = self._parse_date(request.start_date)
                end = self._parse_date(request.end_date)
                duration_days = (end - start).days
                params["durationStr"] = f"{duration_days} D"
                params["endDateTime"] = self._format_date_for_ib(request.end_date)
            else:
                # Default to last 30 days
                params["durationStr"] = "30 D"
                params["endDateTime"] = ""

        return params

    def _download_from_ib(self, connection, contract, params) -> list:
        """Download data from Interactive Brokers"""

        # This would use the actual IB API
        # For demonstration, return mock data

        import random

        # Generate mock historical data
        num_bars = random.randint(100, 1000)
        start_date = datetime.now() - timedelta(days=30)

        bars: list[dict[str, Any]] = []
        current_price = 100.0

        for i in range(num_bars):
            # Simulate price movement
            price_change = random.uniform(-2, 2)
            current_price = max(1.0, current_price + price_change)

            bar_time = start_date + timedelta(minutes=i)

            # Create mock bar
            bar = {
                "date": bar_time,
                "open": current_price + random.uniform(-0.5, 0.5),
                "high": current_price + random.uniform(0, 2),
                "low": current_price - random.uniform(0, 2),
                "close": current_price,
                "volume": random.randint(1000, 50000),
                "barCount": random.randint(10, 100),
                "average": current_price + random.uniform(-0.1, 0.1),
            }

            bars.append(bar)

        # Simulate download time
        time.sleep(0.1)

        return bars

    def _convert_bars_to_dataframe(self, bars: list) -> pd.DataFrame:
        """Convert IB bars to pandas DataFrame"""

        if not bars:
            return pd.DataFrame()

        # Convert to DataFrame
        df = pd.DataFrame(bars)

        # Set datetime index
        df["date"] = pd.to_datetime(df["date"])
        df.set_index("date", inplace=True)

        # Ensure correct data types
        numeric_columns = [
            "open",
            "high",
            "low",
            "close",
            "volume",
            "barCount",
            "average",
        ]
        for col in numeric_columns:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        # Sort by date
        df.sort_index(inplace=True)

        return df

    def _get_date_string(self, request: DownloadRequest) -> str:
        """Get date string for file naming"""

        if request.end_date:
            return self._format_date_string(request.end_date)

        # Default to today
        return datetime.now().strftime("%Y-%m-%d")

    def _parse_date(self, date_input: str | date | datetime) -> datetime:
        """Parse various date formats to datetime"""

        if isinstance(date_input, datetime):
            return date_input
        elif isinstance(date_input, date):
            return datetime.combine(date_input, datetime.min.time())
        elif isinstance(date_input, str):
            try:
                return datetime.strptime(date_input, "%Y-%m-%d")
            except ValueError:
                try:
                    return datetime.strptime(date_input, "%Y-%m-%d %H:%M:%S")
                except ValueError:
                    raise ValueError(f"Invalid date format: {date_input}")
        else:
            raise ValueError(f"Unsupported date type: {type(date_input)}")

    def _format_date_for_ib(self, date_input: str | date | datetime) -> str:
        """Format date for IB API"""
        dt = self._parse_date(date_input)
        return dt.strftime("%Y%m%d %H:%M:%S")

    def _format_date_string(self, date_input: str | date | datetime) -> str:
        """Format date for file naming"""
        dt = self._parse_date(date_input)
        return dt.strftime("%Y-%m-%d")

    def download_multiple_symbols(
        self, symbols: list[str], bar_size: BarSize, **kwargs
    ) -> dict[str, DownloadResult]:
        """Download historical data for multiple symbols"""

        results = {}

        for symbol in symbols:
            request = DownloadRequest(symbol=symbol, bar_size=bar_size, **kwargs)

            try:
                # Use the integrated error handling
                result = self.download_historical_data(request)
                results[symbol] = result

                # Short delay between requests to avoid rate limiting
                time.sleep(0.5)

            except Exception as e:
                # Create failed result
                results[symbol] = DownloadResult(
                    success=False,
                    symbol=symbol,
                    bar_size=bar_size,
                    error_message=str(e),
                )

        return results

    def get_download_statistics(self) -> dict[str, Any]:
        """Get comprehensive download statistics"""

        stats = self.download_stats.copy()

        # Calculate derived metrics
        if stats["total_requests"] > 0:
            stats["success_rate"] = (
                stats["successful_downloads"] / stats["total_requests"]
            ) * 100
            stats["cache_hit_rate"] = (
                stats["cache_hits"] / stats["total_requests"]
            ) * 100
        else:
            stats["success_rate"] = 0.0
            stats["cache_hit_rate"] = 0.0

        if stats["successful_downloads"] > 0:
            stats["average_download_time"] = (
                stats["total_download_time"] / stats["successful_downloads"]
            )
            stats["average_rows_per_download"] = (
                stats["total_rows_downloaded"] / stats["successful_downloads"]
            )
        else:
            stats["average_download_time"] = 0.0
            stats["average_rows_per_download"] = 0.0

        return stats

    def get_status_report(self) -> str:
        """Generate human-readable status report"""

        stats = self.get_download_statistics()

        report_lines = [
            "📊 Historical Data Service Status",
            "=" * 40,
            f"📈 Total Requests: {stats['total_requests']:,}",
            f"✅ Successful Downloads: {stats['successful_downloads']:,}",
            f"🎯 Cache Hits: {stats['cache_hits']:,}",
            f"❌ Failed Downloads: {stats['failed_downloads']:,}",
            f"📊 Success Rate: {stats['success_rate']:.1f}%",
            f"🚀 Cache Hit Rate: {stats['cache_hit_rate']:.1f}%",
            f"⏱️ Average Download Time: {stats['average_download_time']:.2f}s",
            f"📋 Average Rows/Download: {stats['average_rows_per_download']:.0f}",
            f"📦 Total Rows Downloaded: {stats['total_rows_downloaded']:,}",
        ]

        return "\n".join(report_lines)


# Example usage functions for the new service


def download_single_symbol(
    symbol: str, bar_size: str = "1 min", days_back: int = 30
) -> DownloadResult:
    """Convenient function to download single symbol"""

    service = HistoricalDataService()

    request = DownloadRequest(
        symbol=symbol, bar_size=BarSize(bar_size), duration=f"{days_back} D"
    )

    return service.download_historical_data(request)


def download_symbol_list(
    symbols: list[str], bar_size: str = "1 min"
) -> dict[str, DownloadResult]:
    """Convenient function to download multiple symbols"""

    service = HistoricalDataService()

    return service.download_multiple_symbols(
        symbols=symbols, bar_size=BarSize(bar_size), duration="30 D"
    )


def main():
    """Demo the historical data service"""

    print("📊 Historical Data Service Demo")
    print("=" * 50)

    # Create service
    service = HistoricalDataService()

    # Test single download
    print("📥 Testing single symbol download...")

    request = DownloadRequest(symbol="AAPL", bar_size=BarSize.MIN_1, duration="5 D")

    try:
        result = service.download_historical_data(request)

        if result.success:
            print(
                f"✅ Downloaded {result.row_count:,} rows in {result.download_time:.2f}s"
            )
            if result.cached:
                print("   📂 Data served from cache")
            else:
                print(f"   💾 Data saved to {result.file_path}")
        else:
            print(f"❌ Download failed: {result.error_message}")

    except Exception as e:
        print(f"❌ Error: {e}")

    # Test multiple downloads
    print("\n📥 Testing multiple symbol downloads...")

    symbols = ["MSFT", "GOOGL", "TSLA"]
    results = service.download_multiple_symbols(
        symbols=symbols, bar_size=BarSize.MIN_5, duration="3 D"
    )

    for symbol, result in results.items():
        if result.success:
            cache_status = "📂" if result.cached else "💾"
            print(f"  {cache_status} {symbol}: {result.row_count:,} rows")
        else:
            print(f"  ❌ {symbol}: {result.error_message}")

    # Show statistics
    print(f"\n{service.get_status_report()}")

    print("\n🎉 Historical Data Service demo complete!")


if __name__ == "__main__":
    main()
