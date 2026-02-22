"""Stop limit order."""
from __future__ import annotations

from nautilus_full.core.enums import OrderType
from nautilus_full.core.events import OrderInitialized, OrderUpdated
from nautilus_full.core.objects import Price
from nautilus_full.model.orders.base import Order


class StopLimitOrder(Order):
    """
    Stop limit order — when ``trigger_price`` is hit, rests a limit order at ``price``.

    Two-phase execution:
    1. Trigger phase: monitors market price against trigger_price.
    2. After trigger fires, becomes a resting limit order at price.
    """

    def __init__(self, init: OrderInitialized) -> None:
        if init.order_type != OrderType.STOP_LIMIT:
            raise ValueError(f"Expected STOP_LIMIT order, got {init.order_type}")
        if init.trigger_price is None:
            raise ValueError("StopLimitOrder requires a trigger_price")
        if init.price is None:
            raise ValueError("StopLimitOrder requires a price (limit price)")
        super().__init__(init)
        self.trigger_price: Price = init.trigger_price
        self.price: Price = init.price
        self.is_triggered: bool = False

    def _apply_updated(self, event: OrderUpdated) -> None:
        super()._apply_updated(event)
        if event.price is not None:
            self.price = event.price
        if event.trigger_price is not None:
            self.trigger_price = event.trigger_price
