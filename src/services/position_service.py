"""Position Service (thin wrapper)

Provides a dedicated façade over OrderManagementService's position
tracking to improve separation of concerns and allow a gradual
extraction of position state in the future.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.services.order_management_service import (
    Fill,
    OrderAction,
    OrderManagementService,
    Position,
)


@dataclass
class PositionService:
    """Dedicated service for positions.

    Initially delegates to OrderManagementService; later we can migrate
    storage/state here without changing callers.
    """

    _oms: OrderManagementService | None = None

    @property
    def _svc(self) -> OrderManagementService:
        if self._oms is None:
            self._oms = OrderManagementService()
        return self._oms

    # Query APIs -----------------------------------------------------------
    def get_position(self, symbol: str) -> Position | None:
        return self._svc.get_position(symbol)

    def get_all_positions(self) -> list[Position]:
        return self._svc.get_all_positions()

    def get_open_positions(self) -> list[Position]:
        return self._svc.get_open_positions()

    # Mutation APIs --------------------------------------------------------
    def update_on_fill(
        self,
        *,
        order_id: int,
        execution_id: str,
        symbol: str,
        side: OrderAction,
        quantity: int,
        price: float,
        time: Any | None = None,
        exchange: str = "SMART",
        commission: float = 0.0,
        realized_pnl: float = 0.0,
    ) -> None:
        """Apply a fill to positions by delegating to OMS.

        Constructs a Fill and routes it through OMS so order/position
        bookkeeping stays consistent.
        """
        from datetime import datetime

        fill = Fill(
            order_id=order_id,
            execution_id=execution_id,
            symbol=symbol,
            side=side,
            quantity=quantity,
            price=price,
            time=time or datetime.now(),
            exchange=exchange,
            commission=commission,
            realized_pnl=realized_pnl,
        )

        # Reuse the OMS public API for fills if exposed; else, call its
        # internal processing method to avoid duplicating logic.
        try:
            process_fill = getattr(self._svc, "process_fill", None)
            if callable(process_fill):  # type: ignore[call-arg]
                process_fill(fill)  # pragma: no cover - rare path
            else:
                # Fallback to private method used internally
                self._svc._update_position(fill)  # type: ignore[attr-defined]
        except Exception:
            # As a safe fallback, at least update via private path; we already tried.
            self._svc._update_position(fill)  # type: ignore[attr-defined]
