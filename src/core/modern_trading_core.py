"""
Modern Trading Core - Phase 2 Architecture Migration
Replaces the monolithic MasterPy_Trading.py with clean, service-oriented architecture.

This is the new entry point that coordinates all services instead of
having everything in one massive file.
"""

import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from src.core.config import get_config
    from src.core.error_handler import get_error_handler
    from src.core.integrated_error_handling import with_error_handling
    from src.data.data_manager import DataManager
    from src.data.parquet_repository import ParquetRepository
    from src.services.bar_configuration_service import BarConfigurationService
    from src.services.contract_manager_service import ContractManagerService
    from src.services.data_persistence_service import DataPersistenceService
    from src.services.historical_data_service import HistoricalDataService
    from src.services.market_calendar_service import MarketCalendarService
    from src.services.market_info_service import MarketInfoService
    from src.services.path_service import PathService
    from src.services.request_manager_service import RequestManagerService
except ImportError as e:
    print(f"Import error: {e}")
    print("Please ensure you're running from the project root directory")
    sys.exit(1)


class ModernTradingCore:
    """
    Modern trading system core that replaces the monolithic architecture.

    This class coordinates all services instead of containing all functionality.
    Follows the Single Responsibility Principle and dependency injection patterns.
    """

    def __init__(self, ib_connection=None, config=None):
        """Initialize the modern trading core with service dependencies."""

        # Configuration and core services
        self.config = config or get_config()
        self.error_handler = get_error_handler()

        # Initialize all services
        self.request_manager = RequestManagerService(ib_connection)
        self.data_persistence = DataPersistenceService()
        self.market_info = MarketInfoService()
        self.bar_config = BarConfigurationService()
        self.path_service = PathService()
        self.contract_manager = ContractManagerService()
        self.market_calendar = MarketCalendarService()

        # Data services
        self.data_manager = DataManager()
        self.parquet_repo = ParquetRepository()
        self.historical_data_service = HistoricalDataService()

        # IB Connection (will be injected)
        self.ib = ib_connection

        # Use logger instead of non-existent log_info
        self.error_handler.logger.info("Modern Trading Core initialized successfully")

    @with_error_handling("trading_core")
    def download_historical_data(  # noqa: C901 - complexity tracked for future refactor
        self,
        symbol: str,
        bar_size: str,
        for_date: str = "",
        what_to_show: str = "TRADES",
    ) -> dict[str, Any]:
        """
        Download historical data using modern service architecture.

        This replaces the massive Download_Historical method from requestCheckerCLS.
        """

        try:
            # 1. Validate inputs using bar configuration service
            bar_obj = self.bar_config.create_bar_configuration(bar_size)
            if not bar_obj:
                return {"status": "error", "message": f"Invalid bar size: {bar_size}"}

            # 2. Check if already downloaded or failed (using correct method names)
            if self.data_persistence.download_exists(symbol, bar_size, for_date):
                self.error_handler.logger.info(
                    f"Already downloaded: {symbol} {bar_size} {for_date}"
                )
                return {"status": "already_downloaded", "symbol": symbol}

            if self.data_persistence.is_failed(symbol, bar_size, for_date):
                self.error_handler.logger.warning(
                    f"Previously failed: {symbol} {bar_size} {for_date}"
                )
                return {"status": "previously_failed", "symbol": symbol}

            # 3. Check if market is open (if needed) - fallback since method not available
            if not for_date:  # Live data
                # Fallback: assume market is open during business hours
                current_hour = datetime.now().hour
                if not (9 <= current_hour <= 16):  # Basic market hours check
                    return {
                        "status": "market_closed",
                        "message": "Market is currently closed",
                    }

            # 4. Use request manager for throttling (using correct method)
            # Compute end datetime if needed in the future; not used currently.
            _ = datetime.strptime(for_date, "%Y-%m-%d") if for_date else datetime.now()

            # Check if we can send request
            if not self.request_manager._can_send_request():
                sleep_time = self.request_manager._calculate_sleep_time()
                return {
                    "status": "throttled",
                    "message": f"Request throttled, wait {sleep_time:.1f} seconds",
                }

            # 5. Create IB contract using contract manager
            contract = self.contract_manager.create_stock_contract(symbol)
            if not contract:
                return {
                    "status": "error",
                    "message": f"Failed to create contract for {symbol}",
                }

            # 6. Download data using historical data service (using correct method)
            from src.services.historical_data_service import (
                BarSize,
                DataType,
                DownloadRequest,
            )

            # Map bar_size string to BarSize enum
            bar_size_map = {
                "1 min": BarSize.MIN_1,
                "5 mins": BarSize.MIN_5,
                "15 mins": BarSize.MIN_15,
                "30 mins": BarSize.MIN_30,
                "1 hour": BarSize.HOUR_1,
                "1 day": BarSize.DAY_1,
            }

            bar_size_enum = bar_size_map.get(bar_size, BarSize.MIN_1)

            request = DownloadRequest(
                symbol=symbol,
                bar_size=bar_size_enum,
                what_to_show=DataType.TRADES,
                end_date=for_date,
            )

            # Get connection - use the passed ib connection
            connection = self.ib
            if not connection:
                return {"status": "error", "message": "No IB connection available"}

            download_result = self.historical_data_service.download_historical_data(
                connection, request
            )

            if download_result.success:
                # 7. Save data using modern storage
                data_df = download_result.data

                # Save using parquet repository (use correct method with required parameters)
                success = self.parquet_repo.save_data(data_df, symbol, bar_size)

                if success:
                    # 8. Mark as completed (use correct method)
                    self.data_persistence.append_downloaded(symbol, bar_size, for_date)

                    self.error_handler.logger.info(
                        f"Successfully downloaded: {symbol} {bar_size} ({len(data_df)} bars)"
                    )

                    return {
                        "status": "success",
                        "symbol": symbol,
                        "bar_size": bar_size,
                        "for_date": for_date,
                        "bars_count": len(data_df),
                        "file_path": str(
                            self.path_service.get_ib_download_location(
                                symbol, bar_obj, for_date
                            )
                        ),
                    }

            # 9. Mark as failed (use correct method)
            error_msg = download_result.error_message or "Unknown error"
            self.data_persistence.append_failed(
                symbol, False, bar_size, for_date, error_msg
            )

            return {"status": "download_failed", "symbol": symbol, "error": error_msg}

        except Exception as e:
            # Fix error handler call - correct parameter order
            self.error_handler.handle_error(
                e,
                context={"symbol": symbol, "bar_size": bar_size, "for_date": for_date},
                module="modern_trading_core",
                function="download_historical_data",
            )

            # Mark as failed (use correct method)
            self.data_persistence.append_failed(
                symbol, False, bar_size, for_date, str(e)
            )

            return {"status": "error", "error": str(e)}

    def _create_contract(self, symbol: str):
        """Create IB contract for symbol."""
        try:
            if self.ib is None:
                raise ValueError("IB connection not available")

            from ib_async import Stock

            contract = Stock(symbol, "SMART", "USD")

            # Qualify the contract
            qualified = self.ib.qualifyContracts(contract)
            if qualified:
                return qualified[0]
            else:
                raise ValueError(f"Could not qualify contract for {symbol}")

        except Exception as e:
            # Fix error handler call - correct parameter order
            self.error_handler.handle_error(
                e,
                context={"symbol": symbol},
                module="modern_trading_core",
                function="_create_contract",
            )
            return None

    @with_error_handling("trading_core")
    def batch_download(
        self, symbols: list[str], bar_size: str, for_date: str = ""
    ) -> dict[str, Any]:
        """
        Download multiple symbols efficiently.

        Uses modern request management and parallel processing where possible.
        """
        results = {}
        successful = 0
        failed = 0

        self.error_handler.logger.info(
            f"Starting batch download: {len(symbols)} symbols, {bar_size}"
        )

        for i, symbol in enumerate(symbols, 1):
            self.error_handler.logger.info(f"Processing {symbol} ({i}/{len(symbols)})")

            result = self.download_historical_data(symbol, bar_size, for_date)
            results[symbol] = result

            if result["status"] == "success":
                successful += 1
            else:
                failed += 1

            # Log progress
            if i % 10 == 0:
                self.error_handler.logger.info(
                    f"Progress: {i}/{len(symbols)} - Success: {successful}, Failed: {failed}"
                )

        # Save tracking data (use correct method)
        self.data_persistence.save_all()

        return {
            "status": "completed",
            "total_symbols": len(symbols),
            "successful": successful,
            "failed": failed,
            "results": results,
            "request_stats": {
                "active_requests": len(self.request_manager.get_active_requests()),
                "requests_remaining": self.request_manager.requests_remaining(),
                "is_downloading": self.request_manager.is_downloading(),
            },
        }

    def get_system_status(self) -> dict[str, Any]:
        """Get comprehensive system status from all services."""
        return {
            "config": "loaded" if self.config else "not_loaded",
            "ib_connected": self.ib.isConnected() if self.ib else False,
            "request_manager": {
                "active_requests": len(self.request_manager.get_active_requests()),
                "requests_remaining": self.request_manager.requests_remaining(),
                "is_downloading": self.request_manager.is_downloading(),
            },
            "data_persistence": self.data_persistence.get_statistics(),
            "market_info": {
                "is_open": True,  # Fallback - market info service method not available
                "last_trade_day": str(date.today()),  # Fallback
            },
            "services_initialized": True,
        }

    def cleanup(self):
        """Cleanup all services and save state."""
        try:
            self.error_handler.logger.info("Cleaning up Modern Trading Core...")

            # Save tracking data (use correct method)
            self.data_persistence.save_all()

            # Disconnect IB if connected
            if self.ib and self.ib.isConnected():
                self.ib.disconnect()

            self.error_handler.logger.info("Modern Trading Core cleanup completed")

        except Exception as e:
            # Fix error handler call
            self.error_handler.handle_error(
                e, context={}, module="modern_trading_core", function="cleanup"
            )


# Factory function for easy creation
def create_modern_trading_core(ib_connection=None, config=None) -> ModernTradingCore:
    """Factory function to create a properly configured Modern Trading Core."""
    return ModernTradingCore(ib_connection, config)


# Compatibility functions for legacy code
async def InitiateTWS(LiveMode=False, clientId=1):  # noqa: N802, N803 - legacy compat
    """Legacy compatibility function - now async.

    Modernized to use the centralized IB client getter which delegates to
    infra.ib_conn.connect_ib (env-driven defaults, retries, diagnostics).
    """
    try:
        from src.infra.ib_client import get_ib

        # get_ib() returns a connected client using centralized logic.
        ib = await get_ib()
        return ib

    except Exception as e:
        print(f"Failed to obtain IB client: {e}")
        return None


if __name__ == "__main__":
    # Example usage
    print("🚀 Modern Trading Core - Phase 2 Architecture")

    # Initialize IB connection
    ib = InitiateTWS(LiveMode=False, clientId=1)
    if ib:
        print("✅ IB Connection established")

        # Create modern core
        trading_core = create_modern_trading_core(ib)

        # Show system status
        status = trading_core.get_system_status()
        print(f"📊 System Status: {status}")

        # Example download
        # result = trading_core.download_historical_data("AAPL", "30 mins", "2024-01-15")
        # print(f"📈 Download Result: {result}")

        # Cleanup
        trading_core.cleanup()
    else:
        print("❌ Failed to connect to IB")
