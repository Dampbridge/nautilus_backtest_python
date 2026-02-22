"""Stop market order."""
from __future__ import annotations

from nautilus_full.core.enums import OrderType
from nautilus_full.core.events import OrderInitialized, OrderUpdated
from nautilus_full.core.objects import Price
from nautilus_full.model.orders.base import Order


class StopMarketOrder(Order):
    """
    Stop market order — triggers as a market order when ``trigger_price`` is hit.

    BUY stop: triggers when market >= trigger_price (used to enter long on breakout,
               or cover a short position).
    SELL stop: triggers when market <= trigger_price (used to cut losses on a long,
               or enter short on breakdown).
    """

    def __init__(self, init: OrderInitialized) -> None:
        if init.order_type != OrderType.STOP_MARKET:
            raise ValueError(f"Expected STOP_MARKET order, got {init.order_type}")
        if init.trigger_price is None:
            raise ValueError("StopMarketOrder requires a trigger_price")
        super().__init__(init)
        self.trigger_price: Price = init.trigger_price
        self.is_triggered: bool = False

    def _apply_updated(self, event: OrderUpdated) -> None:
        super()._apply_updated(event)
        if event.trigger_price is not None:
            self.trigger_price = event.trigger_price
