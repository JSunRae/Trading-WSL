#!/usr/bin/env python3
"""
Order Management Service

This service handles order placement, modification, and tracking
from Interactive Brokers with modern architecture patterns.

This extracts and modernizes order management from the monolithic system.
"""

import logging
import sys
import threading
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.config import get_config
from src.core.integrated_error_handling import with_error_handling
from src.data.parquet_repository import ParquetRepository

# Type aliases for IB API compatibility
IBConnection = Any  # Placeholder for IB connection type
IBContract = dict[str, Any]  # IB contract representation
IBOrder = dict[str, Any]  # IB order representation


class OrderType(Enum):
    """Types of orders"""

    MARKET = "MKT"
    LIMIT = "LMT"
    STOP = "STP"
    STOP_LIMIT = "STP LMT"
    TRAIL = "TRAIL"
    TRAIL_LIMIT = "TRAIL LIMIT"
    RELATIVE = "REL"
    MARKET_ON_CLOSE = "MOC"
    LIMIT_ON_CLOSE = "LOC"
    PEGGED_TO_MARKET = "PEG MKT"
    PEGGED_TO_MIDPOINT = "PEG MID"


class OrderAction(Enum):
    """Order actions"""

    BUY = "BUY"
    SELL = "SELL"


class OrderStatus(Enum):
    """Order status values"""

    PENDING_SUBMIT = "PendingSubmit"
    PENDING_CANCEL = "PendingCancel"
    PRE_SUBMITTED = "PreSubmitted"
    SUBMITTED = "Submitted"
    CANCELLED = "Cancelled"
    FILLED = "Filled"
    INACTIVE = "Inactive"
    PARTIAL_FILLED = "PartiallyFilled"
    API_CANCELLED = "ApiCancelled"
    API_PENDING = "ApiPending"
    UNKNOWN = "Unknown"


class TimeInForce(Enum):
    """Time in force values"""

    DAY = "DAY"
    GTC = "GTC"  # Good Till Cancelled
    IOC = "IOC"  # Immediate or Cancel
    GTD = "GTD"  # Good Till Date
    OPG = "OPG"  # Market on Open
    FOK = "FOK"  # Fill or Kill


@dataclass
class OrderRequest:
    """Request to place an order"""

    symbol: str
    action: OrderAction
    quantity: int
    order_type: OrderType
    limit_price: float | None = None
    stop_price: float | None = None
    time_in_force: TimeInForce = TimeInForce.DAY
    good_till_date: str | None = None
    outside_rth: bool = False
    hidden: bool = False
    trail_stop_price: float | None = None
    trail_percent: float | None = None
    parent_id: int | None = None
    transmit: bool = True
    block_order: bool = False
    account: str | None = None

    def __post_init__(self):
        """Validate order request"""
        if self.quantity <= 0:
            raise ValueError("Quantity must be positive")

        if (
            self.order_type in [OrderType.LIMIT, OrderType.STOP_LIMIT]
            and not self.limit_price
        ):
            raise ValueError(f"{self.order_type.value} orders require limit_price")

        if (
            self.order_type in [OrderType.STOP, OrderType.STOP_LIMIT]
            and not self.stop_price
        ):
            raise ValueError(f"{self.order_type.value} orders require stop_price")


@dataclass
class Order:
    """Order object with all details"""

    order_id: int
    symbol: str
    action: OrderAction
    quantity: int
    order_type: OrderType
    limit_price: float | None = None
    stop_price: float | None = None
    time_in_force: TimeInForce = TimeInForce.DAY
    status: OrderStatus = OrderStatus.PENDING_SUBMIT
    filled_quantity: int = 0
    remaining_quantity: int = 0
    avg_fill_price: float | None = None
    last_fill_price: float | None = None
    last_fill_quantity: int = 0
    commission: float = 0.0
    created_time: datetime = field(default_factory=datetime.now)
    updated_time: datetime = field(default_factory=datetime.now)
    submitted_time: datetime | None = None
    filled_time: datetime | None = None
    parent_id: int | None = None
    client_order_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    error_message: str | None = None

    @property
    def is_active(self) -> bool:
        """Check if order is still active"""
        return self.status in [
            OrderStatus.PENDING_SUBMIT,
            OrderStatus.PRE_SUBMITTED,
            OrderStatus.SUBMITTED,
            OrderStatus.PARTIAL_FILLED,
        ]

    @property
    def is_filled(self) -> bool:
        """Check if order is completely filled"""
        return self.status == OrderStatus.FILLED

    @property
    def is_cancelled(self) -> bool:
        """Check if order is cancelled"""
        return self.status in [OrderStatus.CANCELLED, OrderStatus.API_CANCELLED]

    @property
    def fill_percentage(self) -> float:
        """Get fill percentage"""
        if self.quantity > 0:
            return (self.filled_quantity / self.quantity) * 100
        return 0.0


@dataclass
class Fill:
    """Execution/fill details"""

    order_id: int
    execution_id: str
    symbol: str
    side: OrderAction
    quantity: int
    price: float
    time: datetime
    exchange: str
    commission: float = 0.0
    commission_currency: str = "USD"
    realized_pnl: float = 0.0

    @property
    def value(self) -> float:
        """Total execution value"""
        return self.quantity * self.price


@dataclass
class Position:
    """Current position in a symbol"""

    symbol: str
    quantity: int
    average_cost: float
    market_price: float | None = None
    market_value: float | None = None
    unrealized_pnl: float | None = None
    realized_pnl: float = 0.0
    account: str | None = None

    @property
    def is_long(self) -> bool:
        """Check if position is long"""
        return self.quantity > 0

    @property
    def is_short(self) -> bool:
        """Check if position is short"""
        return self.quantity < 0

    @property
    def is_flat(self) -> bool:
        """Check if position is flat"""
        return self.quantity == 0


class OrderManagementService:
    """Modern order management service with enterprise features"""

    def __init__(self) -> None:
        super().__init__()
        self.config = get_config()
        self.parquet_repo = ParquetRepository()
        self.logger = logging.getLogger(__name__)

        # Order tracking
        self.orders: dict[int, Order] = {}
        self.fills: dict[str, Fill] = {}  # execution_id -> Fill
        self.positions: dict[str, Position] = {}  # symbol -> Position

        # Event handlers
        self.order_status_handlers: list[Callable[[Order], None]] = []
        self.fill_handlers: list[Callable[[Fill], None]] = []
        self.position_handlers: list[Callable[[Position], None]] = []

        # Order ID management
        self.next_order_id = 1
        self._order_id_lock = threading.Lock()

        # Performance tracking
        self.order_stats = {
            "total_orders": 0,
            "filled_orders": 0,
            "cancelled_orders": 0,
            "rejected_orders": 0,
            "active_orders": 0,
            "total_fills": 0,
            "total_volume_traded": 0.0,
            "total_commission": 0.0,
            "total_pnl": 0.0,
        }

    def get_next_order_id(self) -> int:
        """Get next available order ID"""
        with self._order_id_lock:
            order_id = self.next_order_id
            self.next_order_id += 1
            return order_id

    @with_error_handling("order_management")
    def place_order(
        self, connection: IBConnection | None, order_request: OrderRequest
    ) -> Order:
        """Place a new order"""

        try:
            # Generate order ID
            order_id = self.get_next_order_id()

            # Create order object
            order = Order(
                order_id=order_id,
                symbol=order_request.symbol,
                action=order_request.action,
                quantity=order_request.quantity,
                order_type=order_request.order_type,
                limit_price=order_request.limit_price,
                stop_price=order_request.stop_price,
                time_in_force=order_request.time_in_force,
                remaining_quantity=order_request.quantity,
                parent_id=order_request.parent_id,
            )

            # Store order
            self.orders[order_id] = order
            self.order_stats["total_orders"] += 1

            # Create IB contract and order
            contract = self._create_contract(order_request.symbol)
            ib_order = self._create_ib_order(order_request, order_id)

            # Submit to IB
            success = self._submit_order_to_ib(connection, contract, ib_order)

            if success:
                order.status = OrderStatus.SUBMITTED
                order.submitted_time = datetime.now()
                self.logger.info(
                    f"Order {order_id} submitted for {order_request.symbol}"
                )

                # Call event handlers
                self._notify_order_status_handlers(order)

                # Save order to persistent storage
                self._save_order_to_storage(order)

            else:
                order.status = OrderStatus.API_CANCELLED
                order.error_message = "Failed to submit to IB"
                self.order_stats["rejected_orders"] += 1
                self.logger.error(f"Failed to submit order {order_id}")

            order.updated_time = datetime.now()
            self._update_stats()

            return order

        except Exception as e:
            self.logger.error(f"Error placing order: {e}")
            raise

    @with_error_handling("order_management")
    def cancel_order(self, connection: IBConnection | None, order_id: int) -> bool:
        """Cancel an existing order"""

        try:
            if order_id not in self.orders:
                self.logger.warning(f"Order {order_id} not found")
                return False

            order = self.orders[order_id]

            if not order.is_active:
                self.logger.warning(
                    f"Order {order_id} is not active (status: {order.status.value})"
                )
                return False

            # Update order status
            order.status = OrderStatus.PENDING_CANCEL
            order.updated_time = datetime.now()

            # Submit cancellation to IB
            success = self._cancel_order_in_ib(connection, order_id)

            if success:
                order.status = OrderStatus.CANCELLED
                self.order_stats["cancelled_orders"] += 1
                self.logger.info(f"Order {order_id} cancelled")

                # Call event handlers
                self._notify_order_status_handlers(order)

                # Save updated order
                self._save_order_to_storage(order)

            else:
                order.status = OrderStatus.SUBMITTED  # Revert to previous status
                order.error_message = "Failed to cancel in IB"
                self.logger.error(f"Failed to cancel order {order_id}")

            self._update_stats()

            return success

        except Exception as e:
            self.logger.error(f"Error cancelling order {order_id}: {e}")
            raise

    @with_error_handling("order_management")
    def modify_order(
        self, connection: IBConnection | None, order_id: int, **modifications: Any
    ) -> bool:
        """Modify an existing order"""

        try:
            if order_id not in self.orders:
                self.logger.warning(f"Order {order_id} not found")
                return False

            order = self.orders[order_id]

            if not order.is_active:
                self.logger.warning(f"Order {order_id} is not active")
                return False

            # Update order fields
            updated_fields: list[str] = []
            if "quantity" in modifications:
                order.quantity = modifications["quantity"]
                order.remaining_quantity = (
                    modifications["quantity"] - order.filled_quantity
                )
                updated_fields.append("quantity")

            if "limit_price" in modifications:
                order.limit_price = modifications["limit_price"]
                updated_fields.append("limit_price")

            if "stop_price" in modifications:
                order.stop_price = modifications["stop_price"]
                updated_fields.append("stop_price")

            order.updated_time = datetime.now()

            # Submit modification to IB
            success = self._modify_order_in_ib(connection, order_id, modifications)

            if success:
                self.logger.info(
                    f"Order {order_id} modified: {', '.join(updated_fields)}"
                )

                # Call event handlers
                self._notify_order_status_handlers(order)

                # Save updated order
                self._save_order_to_storage(order)

            else:
                order.error_message = "Failed to modify in IB"
                self.logger.error(f"Failed to modify order {order_id}")

            return success

        except Exception as e:
            self.logger.error(f"Error modifying order {order_id}: {e}")
            raise

    def process_fill(self, execution_details: dict[str, Any]):
        """Process an execution/fill from IB"""

        try:
            order_id = execution_details["orderId"]
            execution_id = execution_details["execId"]

            # Create fill object
            fill = Fill(
                order_id=order_id,
                execution_id=execution_id,
                symbol=execution_details["symbol"],
                side=OrderAction(execution_details["side"]),
                quantity=execution_details["shares"],
                price=execution_details["price"],
                time=datetime.now(),  # In real implementation, use execution time
                exchange=execution_details.get("exchange", "UNKNOWN"),
                commission=execution_details.get("commission", 0.0),
                realized_pnl=execution_details.get("realizedPNL", 0.0),
            )

            # Store fill
            self.fills[execution_id] = fill
            self.order_stats["total_fills"] += 1
            self.order_stats["total_volume_traded"] += fill.value
            self.order_stats["total_commission"] += fill.commission
            self.order_stats["total_pnl"] += fill.realized_pnl

            # Update order
            if order_id in self.orders:
                order = self.orders[order_id]
                order.filled_quantity += fill.quantity
                order.remaining_quantity = order.quantity - order.filled_quantity
                order.last_fill_price = fill.price
                order.last_fill_quantity = fill.quantity
                order.commission += fill.commission
                order.updated_time = datetime.now()

                # Calculate average fill price
                if order.avg_fill_price is None:
                    order.avg_fill_price = fill.price
                else:
                    total_value = (
                        order.avg_fill_price * (order.filled_quantity - fill.quantity)
                        + fill.price * fill.quantity
                    )
                    order.avg_fill_price = total_value / order.filled_quantity

                # Update order status
                if order.remaining_quantity <= 0:
                    order.status = OrderStatus.FILLED
                    order.filled_time = datetime.now()
                    self.order_stats["filled_orders"] += 1
                else:
                    order.status = OrderStatus.PARTIAL_FILLED

                # Save updated order
                self._save_order_to_storage(order)

                # Call event handlers
                self._notify_order_status_handlers(order)

            # Update position
            self._update_position(fill)

            # Call fill handlers
            self._notify_fill_handlers(fill)

            # Save fill to storage
            self._save_fill_to_storage(fill)

            self._update_stats()

            self.logger.info(
                f"Processed fill: {fill.quantity} {fill.symbol} @ {fill.price}"
            )

        except Exception as e:
            self.logger.error(f"Error processing fill: {e}")

    def _update_position(self, fill: Fill):
        """Update position based on fill"""

        symbol = fill.symbol

        if symbol not in self.positions:
            self.positions[symbol] = Position(
                symbol=symbol, quantity=0, average_cost=0.0, realized_pnl=0.0
            )

        position = self.positions[symbol]

        # Calculate new position
        if fill.side == OrderAction.BUY:
            new_quantity = position.quantity + fill.quantity
        else:  # SELL
            new_quantity = position.quantity - fill.quantity

        # Update average cost
        if new_quantity == 0:
            position.average_cost = 0.0
        elif position.quantity == 0:
            position.average_cost = fill.price
        elif (position.quantity > 0 and fill.side == OrderAction.BUY) or (
            position.quantity < 0 and fill.side == OrderAction.SELL
        ):
            # Adding to position
            total_cost = (
                position.average_cost * abs(position.quantity)
                + fill.price * fill.quantity
            )
            position.average_cost = total_cost / abs(new_quantity)

        position.quantity = new_quantity
        position.realized_pnl += fill.realized_pnl

        # Call position handlers
        self._notify_position_handlers(position)

        # Save position
        self._save_position_to_storage(position)

    def get_order(self, order_id: int) -> Order | None:
        """Get order by ID"""
        return self.orders.get(order_id)

    def get_orders_by_symbol(self, symbol: str) -> list[Order]:
        """Get all orders for a symbol"""
        return [order for order in self.orders.values() if order.symbol == symbol]

    def get_active_orders(self) -> list[Order]:
        """Get all active orders"""
        return [order for order in self.orders.values() if order.is_active]

    def get_filled_orders(self) -> list[Order]:
        """Get all filled orders"""
        return [order for order in self.orders.values() if order.is_filled]

    def get_position(self, symbol: str) -> Position | None:
        """Get position for symbol"""
        return self.positions.get(symbol)

    def get_all_positions(self) -> list[Position]:
        """Get all positions"""
        return list(self.positions.values())

    def get_open_positions(self) -> list[Position]:
        """Get positions with non-zero quantity"""
        return [pos for pos in self.positions.values() if not pos.is_flat]

    def get_fills_for_order(self, order_id: int) -> list[Fill]:
        """Get all fills for an order"""
        return [fill for fill in self.fills.values() if fill.order_id == order_id]

    def add_order_status_handler(self, handler: Callable[[Order], None]):
        """Add callback for order status updates"""
        self.order_status_handlers.append(handler)

    def add_fill_handler(self, handler: Callable[[Fill], None]):
        """Add callback for fill events"""
        self.fill_handlers.append(handler)

    def add_position_handler(self, handler: Callable[[Position], None]):
        """Add callback for position updates"""
        self.position_handlers.append(handler)

    def _notify_order_status_handlers(self, order: Order):
        """Notify order status handlers"""
        for handler in self.order_status_handlers:
            try:
                handler(order)
            except Exception as e:
                self.logger.error(f"Error in order status handler: {e}")

    def _notify_fill_handlers(self, fill: Fill):
        """Notify fill handlers"""
        for handler in self.fill_handlers:
            try:
                handler(fill)
            except Exception as e:
                self.logger.error(f"Error in fill handler: {e}")

    def _notify_position_handlers(self, position: Position):
        """Notify position handlers"""
        for handler in self.position_handlers:
            try:
                handler(position)
            except Exception as e:
                self.logger.error(f"Error in position handler: {e}")

    def _create_contract(self, symbol: str) -> IBContract:
        """Create IB contract for symbol"""
        # Mock contract - real implementation would use IB API
        return {
            "symbol": symbol,
            "secType": "STK",
            "exchange": "SMART",
            "currency": "USD",
        }

    def _create_ib_order(self, order_request: OrderRequest, order_id: int) -> IBOrder:
        """Create IB order object"""
        # Mock order - real implementation would use IB API
        return {
            "orderId": order_id,
            "action": order_request.action.value,
            "totalQuantity": order_request.quantity,
            "orderType": order_request.order_type.value,
            "lmtPrice": order_request.limit_price,
            "auxPrice": order_request.stop_price,
            "tif": order_request.time_in_force.value,
            "transmit": order_request.transmit,
        }

    def _submit_order_to_ib(
        self, connection: IBConnection | None, contract: IBContract, ib_order: IBOrder
    ) -> bool:
        """Submit order to IB API"""
        # Mock implementation
        self.logger.info(f"Mock: Submitting order {ib_order['orderId']} to IB")
        return True

    def _cancel_order_in_ib(
        self, connection: IBConnection | None, order_id: int
    ) -> bool:
        """Cancel order in IB API"""
        # Mock implementation
        self.logger.info(f"Mock: Cancelling order {order_id} in IB")
        return True

    def _modify_order_in_ib(
        self,
        connection: IBConnection | None,
        order_id: int,
        modifications: dict[str, Any],
    ) -> bool:
        """Modify order in IB API"""
        # Mock implementation
        self.logger.info(f"Mock: Modifying order {order_id} in IB")
        return True

    def _save_order_to_storage(self, order: Order):
        """Save order to persistent storage"""
        try:
            # Convert to dictionary for storage
            order_data = {
                "order_id": order.order_id,
                "symbol": order.symbol,
                "action": order.action.value,
                "quantity": order.quantity,
                "order_type": order.order_type.value,
                "limit_price": order.limit_price,
                "stop_price": order.stop_price,
                "status": order.status.value,
                "filled_quantity": order.filled_quantity,
                "avg_fill_price": order.avg_fill_price,
                "commission": order.commission,
                "created_time": order.created_time,
                "updated_time": order.updated_time,
            }

            # In real implementation, save to database or Parquet file
            self.logger.debug(
                "Saved order to storage: %s",
                {k: v for k, v in order_data.items() if k != "commission"},
            )

        except Exception as e:
            self.logger.error(f"Error saving order to storage: {e}")

    def _save_fill_to_storage(self, fill: Fill):
        """Save fill to persistent storage"""
        try:
            # In real implementation, save to database or Parquet file
            self.logger.debug(f"Saved fill {fill.execution_id} to storage")
        except Exception as e:
            self.logger.error(f"Error saving fill to storage: {e}")

    def _save_position_to_storage(self, position: Position):
        """Save position to persistent storage"""
        try:
            # In real implementation, save to database or Parquet file
            self.logger.debug(f"Saved position for {position.symbol} to storage")
        except Exception as e:
            self.logger.error(f"Error saving position to storage: {e}")

    def _update_stats(self):
        """Update order statistics"""
        self.order_stats["active_orders"] = len(self.get_active_orders())

    def get_order_statistics(self) -> dict[str, Any]:
        """Get comprehensive order statistics"""

        stats = self.order_stats.copy()

        # Calculate derived metrics
        if stats["total_orders"] > 0:
            stats["fill_rate"] = (stats["filled_orders"] / stats["total_orders"]) * 100
            stats["cancel_rate"] = (
                stats["cancelled_orders"] / stats["total_orders"]
            ) * 100
            stats["reject_rate"] = (
                stats["rejected_orders"] / stats["total_orders"]
            ) * 100

        # Add position metrics
        open_positions = self.get_open_positions()
        stats["open_positions"] = len(open_positions)
        stats["total_positions"] = len(self.positions)

        return stats

    def get_status_report(self) -> str:
        """Generate human-readable status report"""

        stats = self.get_order_statistics()

        report_lines = [
            "📋 Order Management Service Status",
            "=" * 45,
            f"📊 Total Orders: {stats['total_orders']:,}",
            f"✅ Filled Orders: {stats['filled_orders']:,}",
            f"🚫 Cancelled Orders: {stats['cancelled_orders']:,}",
            f"❌ Rejected Orders: {stats['rejected_orders']:,}",
            f"⏳ Active Orders: {stats['active_orders']:,}",
            f"📈 Total Fills: {stats['total_fills']:,}",
            f"💰 Volume Traded: ${stats['total_volume_traded']:,.2f}",
            f"💸 Total Commission: ${stats['total_commission']:.2f}",
            f"📊 Total PnL: ${stats['total_pnl']:.2f}",
            f"📍 Open Positions: {stats['open_positions']}",
            f"📋 Total Positions: {stats['total_positions']}",
        ]

        if stats["total_orders"] > 0:
            report_lines.extend(
                [
                    "",
                    "📈 Rates:",
                    f"  Fill Rate: {stats.get('fill_rate', 0):.1f}%",
                    f"  Cancel Rate: {stats.get('cancel_rate', 0):.1f}%",
                    f"  Reject Rate: {stats.get('reject_rate', 0):.1f}%",
                ]
            )

        return "\n".join(report_lines)


# Convenient functions for common use cases


def place_market_order(
    symbol: str, action: str, quantity: int, connection: IBConnection | None = None
) -> Order:
    """Place a simple market order"""

    service = OrderManagementService()

    request = OrderRequest(
        symbol=symbol,
        action=OrderAction(action.upper()),
        quantity=quantity,
        order_type=OrderType.MARKET,
    )

    return service.place_order(connection, request)


def place_limit_order(
    symbol: str,
    action: str,
    quantity: int,
    limit_price: float,
    connection: IBConnection | None = None,
) -> Order:
    """Place a limit order"""

    service = OrderManagementService()

    request = OrderRequest(
        symbol=symbol,
        action=OrderAction(action.upper()),
        quantity=quantity,
        order_type=OrderType.LIMIT,
        limit_price=limit_price,
    )

    return service.place_order(connection, request)


def main():
    """Demo the order management service"""

    print("📋 Order Management Service Demo")
    print("=" * 50)

    # Create service
    service = OrderManagementService()

    # Add event handlers
    def order_handler(order: Order):
        print(
            f"🔄 Order {order.order_id}: {order.status.value} - {order.symbol} {order.action.value} {order.quantity}"
        )

    def fill_handler(fill: Fill):
        print(f"✅ Fill: {fill.quantity} {fill.symbol} @ ${fill.price:.2f}")

    def position_handler(position: Position):
        if not position.is_flat:
            print(
                f"📊 Position: {position.symbol} = {position.quantity} @ ${position.average_cost:.2f}"
            )

    service.add_order_status_handler(order_handler)
    service.add_fill_handler(fill_handler)
    service.add_position_handler(position_handler)

    # Place some demo orders
    print("📥 Placing demo orders...")

    # Market order
    market_request = OrderRequest(
        symbol="AAPL", action=OrderAction.BUY, quantity=100, order_type=OrderType.MARKET
    )

    market_order = service.place_order(None, market_request)

    # Limit order
    limit_request = OrderRequest(
        symbol="MSFT",
        action=OrderAction.BUY,
        quantity=50,
        order_type=OrderType.LIMIT,
        limit_price=300.00,
    )

    limit_order = service.place_order(None, limit_request)

    # Simulate some fills
    print("\n📊 Simulating fills...")

    # Fill the market order
    market_fill = {
        "orderId": market_order.order_id,
        "execId": f"exec_{market_order.order_id}_1",
        "symbol": "AAPL",
        "side": "BUY",
        "shares": 100,
        "price": 150.50,
        "exchange": "NASDAQ",
        "commission": 1.00,
    }

    service.process_fill(market_fill)

    # Partial fill for limit order
    limit_fill = {
        "orderId": limit_order.order_id,
        "execId": f"exec_{limit_order.order_id}_1",
        "symbol": "MSFT",
        "side": "BUY",
        "shares": 25,
        "price": 299.95,
        "exchange": "NASDAQ",
        "commission": 0.50,
    }

    service.process_fill(limit_fill)

    # Show current state
    print("\n📊 Current Orders:")
    for order in service.orders.values():
        fill_pct = order.fill_percentage
        print(
            f"  Order {order.order_id}: {order.symbol} {order.status.value} ({fill_pct:.1f}% filled)"
        )

    print("\n📍 Current Positions:")
    for position in service.get_open_positions():
        print(
            f"  {position.symbol}: {position.quantity} @ ${position.average_cost:.2f}"
        )

    # Show statistics
    print(f"\n{service.get_status_report()}")

    print("\n🎉 Order Management Service demo complete!")


if __name__ == "__main__":
    main()
