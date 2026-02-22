"""
Order base class with full FSM, partial-fill support, and contingency metadata.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Optional

from nautilus_full.core.enums import (
    ContingencyType,
    ORDER_STATUS_TRANSITIONS,
    OrderSide,
    OrderStatus,
    OrderType,
    TimeInForce,
)
from nautilus_full.core.events import (
    OrderAccepted,
    OrderCanceled,
    OrderDenied,
    OrderExpired,
    OrderFilled,
    OrderInitialized,
    OrderPendingCancel,
    OrderPendingUpdate,
    OrderRejected,
    OrderSubmitted,
    OrderTriggered,
    OrderUpdated,
)
from nautilus_full.core.identifiers import (
    ClientOrderId,
    InstrumentId,
    OrderListId,
    PositionId,
    StrategyId,
    TraderId,
    VenueOrderId,
)
from nautilus_full.core.objects import Price, Quantity


_EVENT_TO_STATUS = {
    OrderInitialized:   OrderStatus.INITIALIZED,
    OrderDenied:        OrderStatus.DENIED,
    OrderSubmitted:     OrderStatus.SUBMITTED,
    OrderAccepted:      OrderStatus.ACCEPTED,
    OrderRejected:      OrderStatus.REJECTED,
    OrderCanceled:      OrderStatus.CANCELED,
    OrderExpired:       OrderStatus.EXPIRED,
    OrderTriggered:     OrderStatus.TRIGGERED,
    OrderPendingUpdate: OrderStatus.PENDING_UPDATE,
    OrderPendingCancel: OrderStatus.PENDING_CANCEL,
    # OrderUpdated and OrderFilled are handled specially
}


class Order:
    """
    Abstract order with full FSM and event history.

    Subclasses add order-type-specific price fields and behaviour.
    """

    def __init__(self, init: OrderInitialized) -> None:
        # Identifiers
        self.client_order_id: ClientOrderId = init.client_order_id
        self.instrument_id: InstrumentId = init.instrument_id
        self.trader_id: TraderId = init.trader_id
        self.strategy_id: StrategyId = init.strategy_id
        self.venue_order_id: Optional[VenueOrderId] = None

        # Order spec
        self.side: OrderSide = init.order_side
        self.order_type: OrderType = init.order_type
        self.quantity: Quantity = init.quantity
        self.time_in_force: TimeInForce = init.time_in_force
        self.post_only: bool = init.post_only
        self.reduce_only: bool = init.reduce_only
        self.expire_time_ns: Optional[int] = init.expire_time_ns
        self.display_qty: Optional[Quantity] = init.display_qty  # iceberg
        self.tags: list[str] = list(init.tags or [])

        # Contingency
        self.contingency_type: ContingencyType = init.contingency_type
        self.order_list_id: Optional[OrderListId] = init.order_list_id
        self.linked_order_ids: list[ClientOrderId] = list(init.linked_order_ids or [])
        self.parent_order_id: Optional[ClientOrderId] = init.parent_order_id

        # Fill tracking
        self.status: OrderStatus = OrderStatus.INITIALIZED
        self.filled_qty: Quantity = Quantity.zero(init.quantity.precision)
        self.leaves_qty: Quantity = Quantity(init.quantity.value, init.quantity.precision)
        self.avg_px: Decimal = Decimal("0")
        self.slippage: Decimal = Decimal("0")

        # Position assignment (set by execution engine)
        self.position_id: Optional[PositionId] = None

        # Event history
        self.events: list = [init]
        self.ts_init: int = init.ts_init
        self.ts_last: int = init.ts_event

    # ── State predicates ───────────────────────────────────────────────────

    @property
    def is_open(self) -> bool:
        return self.status in {
            OrderStatus.ACCEPTED,
            OrderStatus.TRIGGERED,
            OrderStatus.PENDING_UPDATE,
            OrderStatus.PENDING_CANCEL,
            OrderStatus.PARTIALLY_FILLED,
        }

    @property
    def is_closed(self) -> bool:
        return self.status in {
            OrderStatus.DENIED,
            OrderStatus.REJECTED,
            OrderStatus.CANCELED,
            OrderStatus.EXPIRED,
            OrderStatus.FILLED,
        }

    @property
    def is_filled(self) -> bool:
        return self.status == OrderStatus.FILLED

    @property
    def is_partially_filled(self) -> bool:
        return self.status == OrderStatus.PARTIALLY_FILLED

    @property
    def is_buy(self) -> bool:
        return self.side == OrderSide.BUY

    @property
    def is_sell(self) -> bool:
        return self.side == OrderSide.SELL

    @property
    def is_passive(self) -> bool:
        """True for limit-type orders that rest in the book."""
        return self.order_type in {OrderType.LIMIT, OrderType.STOP_LIMIT}

    # ── Event application (FSM) ────────────────────────────────────────────

    def apply(self, event) -> None:
        """
        Apply an order event, updating the FSM state.

        Raises RuntimeError on illegal state transitions.
        """
        if isinstance(event, OrderFilled):
            self._apply_filled(event)
        elif isinstance(event, OrderUpdated):
            self._apply_updated(event)
        else:
            new_status = _EVENT_TO_STATUS.get(type(event))
            if new_status is None:
                raise ValueError(f"Unknown order event type: {type(event).__name__}")
            self._transition(new_status)

            # Side effects on specific events
            if isinstance(event, OrderAccepted) and event.venue_order_id:
                self.venue_order_id = event.venue_order_id
            elif isinstance(event, OrderTriggered) and event.venue_order_id:
                self.venue_order_id = event.venue_order_id

        self.events.append(event)
        self.ts_last = event.ts_event

    def _apply_filled(self, event: OrderFilled) -> None:
        fill_qty = event.last_qty.value
        fill_px = event.last_px.value
        prev_filled = self.filled_qty.value
        new_filled = prev_filled + fill_qty

        # Weighted average fill price
        if new_filled > 0:
            self.avg_px = (
                self.avg_px * prev_filled + fill_px * fill_qty
            ) / new_filled

        self.filled_qty = Quantity(new_filled, self.quantity.precision)
        self.leaves_qty = Quantity(
            max(Decimal("0"), self.quantity.value - new_filled),
            self.quantity.precision,
        )

        if event.venue_order_id:
            self.venue_order_id = event.venue_order_id
        if event.position_id:
            self.position_id = event.position_id

        new_status = (
            OrderStatus.FILLED if self.leaves_qty.is_zero()
            else OrderStatus.PARTIALLY_FILLED
        )
        self._transition(new_status)

    def _apply_updated(self, event: OrderUpdated) -> None:
        if event.quantity is not None:
            self.quantity = event.quantity
            self.leaves_qty = Quantity(
                max(Decimal("0"), event.quantity.value - self.filled_qty.value),
                event.quantity.precision,
            )
        # Subclasses may override to update price / trigger_price
        self._transition(OrderStatus.ACCEPTED)

    def _transition(self, new_status: OrderStatus) -> None:
        valid = ORDER_STATUS_TRANSITIONS.get(self.status, set())
        if new_status not in valid:
            raise RuntimeError(
                f"Invalid order state transition: "
                f"{self.status.name} -> {new_status.name} "
                f"for order {self.client_order_id}"
            )
        self.status = new_status

    # ── Representation ─────────────────────────────────────────────────────

    def __repr__(self) -> str:
        return (
            f"{type(self).__name__}("
            f"id={self.client_order_id}, "
            f"{self.side.name} {self.quantity} {self.instrument_id}, "
            f"tif={self.time_in_force.name}, "
            f"status={self.status.name})"
        )
