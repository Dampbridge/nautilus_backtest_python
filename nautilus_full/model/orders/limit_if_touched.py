"""Limit-if-touched (LIT) order."""
from __future__ import annotations

from nautilus_full.core.enums import OrderType
from nautilus_full.core.events import OrderInitialized, OrderUpdated
from nautilus_full.core.objects import Price
from nautilus_full.model.orders.base import Order


class LimitIfTouchedOrder(Order):
    """
    Limit-if-touched order — triggers as a limit order when price touches
    the trigger level.

    BUY LIT: triggers when market <= trigger_price, then rests a limit at price
    SELL LIT: triggers when market >= trigger_price, then rests a limit at price
    """

    def __init__(self, init: OrderInitialized) -> None:
        if init.order_type != OrderType.LIMIT_IF_TOUCHED:
            raise ValueError(f"Expected LIMIT_IF_TOUCHED order, got {init.order_type}")
        if init.trigger_price is None:
            raise ValueError("LimitIfTouchedOrder requires a trigger_price")
        if init.price is None:
            raise ValueError("LimitIfTouchedOrder requires a limit price")
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
