#!/usr/bin/env python3
"""
Service Manager

Central orchestration for all trading services with health monitoring,
dependency management, and unified API.

This replaces the monolithic requestCheckerCLS with a modern
microservices architecture.
"""

import logging
import sys
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.config import get_config
from src.core.integrated_error_handling import with_error_handling
from src.services.historical_data_service import (
    BarSize,
    DownloadRequest,
    HistoricalDataService,
)
from src.services.market_data_service import MarketDataService, StreamConfig
from src.services.order_management_service import (
    OrderAction,
    OrderManagementService,
    OrderRequest,
    OrderType,
)


class ServiceStatus(Enum):
    """Service status values"""

    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    ERROR = "error"
    DEGRADED = "degraded"


@dataclass
class ServiceInfo:
    """Information about a service"""

    name: str
    service: Any
    status: ServiceStatus = ServiceStatus.STOPPED
    start_time: datetime | None = None
    last_health_check: datetime | None = None
    error_count: int = 0
    last_error: str | None = None
    dependencies: list[str] = None  # type: ignore[assignment]  # TODO: Use Optional[list[str]]

    def __post_init__(self):
        if self.dependencies is None:
            self.dependencies: list[str] = []


class TradingServiceManager:
    """Central manager for all trading services"""

    def __init__(self):
        self.config = get_config()
        self.logger = logging.getLogger(__name__)

        # Service registry
        self.services: dict[str, ServiceInfo] = {}
        self.executor = ThreadPoolExecutor(
            max_workers=10, thread_name_prefix="ServiceManager"
        )

        # Connection management
        self.ib_connection = None
        self.connection_status = "disconnected"
        self.connection_retry_count = 0

        # Event handlers
        self.service_status_handlers: list[Callable[[str, ServiceStatus], None]] = []

        # Manager statistics
        self.manager_stats: dict[str, Any] = {
            "start_time": datetime.now(),
            "total_service_starts": 0,
            "total_service_stops": 0,
            "total_service_errors": 0,
            "total_health_checks": 0,
            "connection_attempts": 0,
            "successful_connections": 0,
        }

        # Initialize services
        self._initialize_services()

    def _initialize_services(self):
        """Initialize all trading services"""

        try:
            # Historical Data Service
            historical_service = HistoricalDataService()
            self.services["historical_data"] = ServiceInfo(
                name="historical_data", service=historical_service, dependencies=[]
            )

            # Market Data Service
            market_service = MarketDataService()
            self.services["market_data"] = ServiceInfo(
                name="market_data", service=market_service, dependencies=[]
            )

            # Order Management Service
            order_service = OrderManagementService()
            self.services["order_management"] = ServiceInfo(
                name="order_management", service=order_service, dependencies=[]
            )

            self.logger.info(f"Initialized {len(self.services)} services")

        except Exception as e:
            self.logger.error(f"Error initializing services: {e}")
            raise

    @with_error_handling("service_manager")
    def start_service(self, service_name: str) -> bool:
        """Start a specific service"""

        if service_name not in self.services:
            raise ValueError(f"Unknown service: {service_name}")

        service_info = self.services[service_name]

        if service_info.status == ServiceStatus.RUNNING:
            self.logger.warning(f"Service {service_name} is already running")
            return True

        try:
            # Check dependencies
            for dep_name in service_info.dependencies:
                dep_info = self.services.get(dep_name)
                if not dep_info or dep_info.status != ServiceStatus.RUNNING:
                    raise RuntimeError(f"Dependency {dep_name} is not running")

            # Update status
            service_info.status = ServiceStatus.STARTING
            self._notify_service_status_handlers(service_name, ServiceStatus.STARTING)

            # Start the service (most services don't need explicit startup)
            service_info.start_time = datetime.now()
            service_info.status = ServiceStatus.RUNNING

            self.manager_stats["total_service_starts"] += 1

            self.logger.info(f"Started service: {service_name}")
            self._notify_service_status_handlers(service_name, ServiceStatus.RUNNING)

            return True

        except Exception as e:
            service_info.status = ServiceStatus.ERROR
            service_info.last_error = str(e)
            service_info.error_count += 1

            self.manager_stats["total_service_errors"] += 1

            self.logger.error(f"Failed to start service {service_name}: {e}")
            self._notify_service_status_handlers(service_name, ServiceStatus.ERROR)

            raise

    @with_error_handling("service_manager")
    def stop_service(self, service_name: str) -> bool:
        """Stop a specific service"""

        if service_name not in self.services:
            raise ValueError(f"Unknown service: {service_name}")

        service_info = self.services[service_name]

        if service_info.status == ServiceStatus.STOPPED:
            self.logger.warning(f"Service {service_name} is already stopped")
            return True

        try:
            # Update status
            service_info.status = ServiceStatus.STOPPING
            self._notify_service_status_handlers(service_name, ServiceStatus.STOPPING)

            # Stop service-specific components
            if service_name == "market_data":
                service_info.service.shutdown()

            # Update status
            service_info.status = ServiceStatus.STOPPED
            service_info.start_time = None

            self.manager_stats["total_service_stops"] += 1

            self.logger.info(f"Stopped service: {service_name}")
            self._notify_service_status_handlers(service_name, ServiceStatus.STOPPED)

            return True

        except Exception as e:
            service_info.status = ServiceStatus.ERROR
            service_info.last_error = str(e)
            service_info.error_count += 1

            self.logger.error(f"Failed to stop service {service_name}: {e}")
            self._notify_service_status_handlers(service_name, ServiceStatus.ERROR)

            raise

    def start_all_services(self) -> dict[str, bool]:
        """Start all services in dependency order"""

        results: dict[str, bool] = {}

        # Calculate startup order based on dependencies
        startup_order = self._calculate_startup_order()

        for service_name in startup_order:
            try:
                results[service_name] = self.start_service(service_name)
            except Exception as e:
                results[service_name] = False
                self.logger.error(f"Failed to start {service_name}: {e}")

        return results

    def stop_all_services(self) -> dict[str, bool]:
        """Stop all services in reverse dependency order"""

        results: dict[str, bool] = {}

        # Calculate shutdown order (reverse of startup)
        shutdown_order = list(reversed(self._calculate_startup_order()))

        for service_name in shutdown_order:
            try:
                results[service_name] = self.stop_service(service_name)
            except Exception as e:
                results[service_name] = False
                self.logger.error(f"Failed to stop {service_name}: {e}")

        return results

    def _calculate_startup_order(self) -> list[str]:
        """Calculate service startup order based on dependencies"""

        ordered: list[str] = []
        remaining = set(self.services.keys())

        while remaining:
            # Find services with no unresolved dependencies
            ready: list[str] = []
            for service_name in remaining:
                service_info = self.services[service_name]
                deps_satisfied = all(
                    dep in ordered for dep in service_info.dependencies
                )
                if deps_satisfied:
                    ready.append(service_name)

            if not ready:
                # Circular dependency or missing dependency
                raise RuntimeError(f"Circular or missing dependencies: {remaining}")

            # Add ready services to ordered list
            for service_name in ready:
                ordered.append(service_name)
                remaining.remove(service_name)

        return ordered

    def health_check_all_services(self) -> dict[str, dict[str, Any]]:
        """Perform health check on all services"""

        health_results: dict[str, dict[str, Any]] = {}

        for service_name, service_info in self.services.items():
            try:
                self.manager_stats["total_health_checks"] += 1

                # Basic health check
                health_status: dict[str, Any] = {
                    "status": service_info.status.value,
                    "uptime_seconds": 0,
                    "error_count": service_info.error_count,
                    "last_error": service_info.last_error,
                    "healthy": service_info.status == ServiceStatus.RUNNING,
                }

                # Calculate uptime
                if service_info.start_time:
                    uptime = (datetime.now() - service_info.start_time).total_seconds()
                    health_status["uptime_seconds"] = uptime

                # Service-specific health checks
                if (
                    service_name == "historical_data"
                    and service_info.status == ServiceStatus.RUNNING
                ):
                    stats = service_info.service.get_download_statistics()
                    health_status["service_stats"] = stats

                elif (
                    service_name == "market_data"
                    and service_info.status == ServiceStatus.RUNNING
                ):
                    stats = service_info.service.get_stream_statistics()
                    health_status["service_stats"] = stats

                elif (
                    service_name == "order_management"
                    and service_info.status == ServiceStatus.RUNNING
                ):
                    stats = service_info.service.get_order_statistics()
                    health_status["service_stats"] = stats

                service_info.last_health_check = datetime.now()
                health_results[service_name] = health_status

            except Exception as e:
                health_results[service_name] = {
                    "status": "error",
                    "healthy": False,
                    "error": str(e),
                }

                service_info.error_count += 1
                service_info.last_error = str(e)

        return health_results

    def get_service(self, service_name: str) -> Any | None:
        """Get a service instance"""

        service_info = self.services.get(service_name)
        if service_info and service_info.status == ServiceStatus.RUNNING:
            return service_info.service
        return None

    def get_historical_data_service(self) -> HistoricalDataService | None:
        """Get historical data service"""
        return self.get_service("historical_data")

    def get_market_data_service(self) -> MarketDataService | None:
        """Get market data service"""
        return self.get_service("market_data")

    def get_order_management_service(self) -> OrderManagementService | None:
        """Get order management service"""
        return self.get_service("order_management")

    # Convenient wrapper methods for common operations

    def download_historical_data(
        self, symbol: str, bar_size: str = "1 min", duration: str = "30 D"
    ) -> Any | None:
        """Download historical data using the historical data service"""

        service = self.get_historical_data_service()
        if not service:
            raise RuntimeError("Historical data service is not available")

        request = DownloadRequest(
            symbol=symbol, bar_size=BarSize(bar_size), duration=duration
        )

        return service.download_historical_data(self.ib_connection, request)

    def start_market_data_stream(self, symbol: str) -> bool:
        """Start market data stream using the market data service"""

        service = self.get_market_data_service()
        if not service:
            raise RuntimeError("Market data service is not available")

        config = StreamConfig(symbol=symbol)
        return service.start_market_data_stream(self.ib_connection, config)

    def place_market_order(self, symbol: str, action: str, quantity: int) -> Any | None:
        """Place market order using the order management service"""

        service = self.get_order_management_service()
        if not service:
            raise RuntimeError("Order management service is not available")

        request = OrderRequest(
            symbol=symbol,
            action=OrderAction(action.upper()),
            quantity=quantity,
            order_type=OrderType.MARKET,
        )

        return service.place_order(self.ib_connection, request)

    def place_limit_order(
        self, symbol: str, action: str, quantity: int, limit_price: float
    ) -> Any | None:
        """Place limit order using the order management service"""

        service = self.get_order_management_service()
        if not service:
            raise RuntimeError("Order management service is not available")

        request = OrderRequest(
            symbol=symbol,
            action=OrderAction(action.upper()),
            quantity=quantity,
            order_type=OrderType.LIMIT,
            limit_price=limit_price,
        )

        return service.place_order(self.ib_connection, request)

    def add_service_status_handler(self, handler: Callable[[str, ServiceStatus], None]):
        """Add callback for service status changes"""
        self.service_status_handlers.append(handler)

    def _notify_service_status_handlers(self, service_name: str, status: ServiceStatus):
        """Notify service status handlers"""
        for handler in self.service_status_handlers:
            try:
                handler(service_name, status)
            except Exception as e:
                self.logger.error(f"Error in service status handler: {e}")

    def get_manager_statistics(self) -> dict[str, Any]:
        """Get comprehensive manager statistics"""

        stats = self.manager_stats.copy()

        # Add runtime info
        uptime = (datetime.now() - stats["start_time"]).total_seconds()
        stats["uptime_seconds"] = uptime
        stats["uptime_minutes"] = uptime / 60

        # Add service counts
        stats["total_services"] = len(self.services)
        stats["running_services"] = len(
            [s for s in self.services.values() if s.status == ServiceStatus.RUNNING]
        )
        stats["stopped_services"] = len(
            [s for s in self.services.values() if s.status == ServiceStatus.STOPPED]
        )
        stats["error_services"] = len(
            [s for s in self.services.values() if s.status == ServiceStatus.ERROR]
        )

        # Connection info
        stats["connection_status"] = self.connection_status
        stats["connection_retry_count"] = self.connection_retry_count

        return stats

    def get_comprehensive_status(self) -> dict[str, Any]:
        """Get comprehensive status of all services"""

        return {
            "manager": self.get_manager_statistics(),
            "services": self.health_check_all_services(),
            "connection": {
                "status": self.connection_status,
                "retry_count": self.connection_retry_count,
            },
        }

    def get_status_report(self) -> str:
        """Generate human-readable status report"""

        status = self.get_comprehensive_status()
        manager_stats = status["manager"]

        report_lines = [
            "🎛️ Trading Service Manager Status",
            "=" * 50,
            f"⏱️ Uptime: {manager_stats['uptime_minutes']:.1f} minutes",
            f"🟢 Running Services: {manager_stats['running_services']}/{manager_stats['total_services']}",
            f"🔴 Error Services: {manager_stats['error_services']}",
            f"🔌 Connection: {self.connection_status}",
            f"📊 Service Starts: {manager_stats['total_service_starts']}",
            f"🛑 Service Stops: {manager_stats['total_service_stops']}",
            f"❌ Service Errors: {manager_stats['total_service_errors']}",
            f"💓 Health Checks: {manager_stats['total_health_checks']}",
            "",
            "📋 Service Details:",
        ]

        for service_name, health in status["services"].items():
            status_icon = "🟢" if health["healthy"] else "🔴"
            uptime = health.get("uptime_seconds", 0)
            uptime_str = f"({uptime / 60:.1f}m)" if uptime > 0 else ""

            report_lines.append(
                f"  {status_icon} {service_name}: {health['status']} {uptime_str}"
            )

            if health.get("service_stats"):
                stats = health["service_stats"]
                if "total_requests" in stats:
                    report_lines.append(
                        f"    📊 Requests: {stats['total_requests']}, Success: {stats.get('success_rate', 0):.1f}%"
                    )
                elif "total_ticks_received" in stats:
                    report_lines.append(
                        f"    📡 Ticks: {stats['total_ticks_received']}, TPS: {stats.get('ticks_per_second', 0):.1f}"
                    )
                elif "total_orders" in stats:
                    report_lines.append(
                        f"    📋 Orders: {stats['total_orders']}, Fill Rate: {stats.get('fill_rate', 0):.1f}%"
                    )

        return "\n".join(report_lines)

    def shutdown(self):
        """Gracefully shutdown all services and the manager"""

        self.logger.info("Shutting down Trading Service Manager...")

        # Stop all services
        stop_results = self.stop_all_services()

        successful_stops = sum(1 for success in stop_results.values() if success)
        self.logger.info(
            f"Stopped {successful_stops}/{len(stop_results)} services successfully"
        )

        # Shutdown executor
        self.executor.shutdown(wait=True)

        self.logger.info("Trading Service Manager shutdown complete")


# Convenient functions for external use


def create_trading_manager() -> TradingServiceManager:
    """Create and initialize trading service manager"""

    manager = TradingServiceManager()

    # Start all services and summarize
    start_results = manager.start_all_services()
    successful_starts = sum(1 for success in start_results.values() if success)
    total_services = len(start_results)

    print(f"✅ Started {successful_starts}/{total_services} services successfully")

    if successful_starts < total_services:
        print("⚠️ Some services failed to start. Check logs for details.")

    return manager


def main():
    """Demo the trading service manager"""

    print("🎛️ Trading Service Manager Demo")
    print("=" * 50)

    # Create manager
    print("🚀 Creating Trading Service Manager...")
    manager = TradingServiceManager()

    # Add status handler
    def status_handler(service_name: str, status: ServiceStatus):
        status_icon = {
            "running": "🟢",
            "stopped": "🔴",
            "error": "❌",
            "starting": "🟡",
            "stopping": "🟠",
        }.get(status.value, "❓")
        print(f"  {status_icon} {service_name}: {status.value}")

    manager.add_service_status_handler(status_handler)

    # Start all services
    print("\n🚀 Starting all services...")
    manager.start_all_services()

    # Show initial status
    print(f"\n{manager.get_status_report()}")

    # Demo some operations
    print("\n📊 Testing service operations...")

    try:
        # Historical data download
        print("📥 Testing historical data download...")
        result = manager.download_historical_data("AAPL", "1 min", "5 D")
        if result and result.success:
            print(f"✅ Downloaded {result.row_count} rows for AAPL")
        else:
            error_msg = result.error_message if result else "No result returned"
            print(f"❌ Download failed: {error_msg}")
    except Exception as e:
        print(f"❌ Error: {e}")

    try:
        # Start market data stream
        print("📡 Testing market data stream...")
        success = manager.start_market_data_stream("MSFT")
        if success:
            print("✅ Started market data stream for MSFT")
        else:
            print("❌ Failed to start market data stream")
    except Exception as e:
        print(f"❌ Error: {e}")

    try:
        # Place an order
        print("📋 Testing order placement...")
        order = manager.place_market_order("GOOGL", "BUY", 10)
        if order:
            print(f"✅ Placed order {order.order_id} for GOOGL")
        else:
            print("❌ Failed to place order")
    except Exception as e:
        print(f"❌ Error: {e}")

    # Wait a bit and show updated status
    print("\n⏱️ Waiting 3 seconds...")
    time.sleep(3)

    print(f"\n{manager.get_status_report()}")

    # Health check
    print("\n💓 Performing health check...")
    health = manager.health_check_all_services()

    healthy_services = sum(1 for h in health.values() if h.get("healthy", False))
    print(f"💚 {healthy_services}/{len(health)} services are healthy")

    # Shutdown
    print("\n🛑 Shutting down...")
    manager.shutdown()

    print("\n🎉 Trading Service Manager demo complete!")


if __name__ == "__main__":
    main()
