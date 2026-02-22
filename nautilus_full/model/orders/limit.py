"""Limit order."""
from __future__ import annotations

from nautilus_full.core.enums import OrderType
from nautilus_full.core.events import OrderInitialized, OrderUpdated
from nautilus_full.core.objects import Price
from nautilus_full.model.orders.base import Order


class LimitOrder(Order):
    """
    Limit order — rests at the specified price or fills if the market crosses it.

    With ``post_only=True``, the order is rejected if it would fill immediately
    (maker-only constraint).

    With ``display_qty`` set, becomes an iceberg order — only ``display_qty``
    is visible in the book; the rest is hidden.
    """

    def __init__(self, init: OrderInitialized) -> None:
        if init.order_type != OrderType.LIMIT:
            raise ValueError(f"Expected LIMIT order, got {init.order_type}")
        if init.price is None:
            raise ValueError("LimitOrder requires a price")
        super().__init__(init)
        self.price: Price = init.price

    def _apply_updated(self, event: OrderUpdated) -> None:
        super()._apply_updated(event)
        if event.price is not None:
            self.price = event.price
