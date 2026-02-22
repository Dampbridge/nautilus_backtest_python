"""Market-if-touched (MIT) order."""
from __future__ import annotations

from nautilus_full.core.enums import OrderType
from nautilus_full.core.events import OrderInitialized, OrderUpdated
from nautilus_full.core.objects import Price
from nautilus_full.model.orders.base import Order


class MarketIfTouchedOrder(Order):
    """
    Market-if-touched order — triggers as a market order when price TOUCHES
    the trigger level (unlike a stop, which requires the price to go THROUGH it).

    Used for reversal / mean-reversion entries.
    BUY MIT: triggers when market <= trigger_price (buy the dip)
    SELL MIT: triggers when market >= trigger_price (sell the rally)
    """

    def __init__(self, init: OrderInitialized) -> None:
        if init.order_type != OrderType.MARKET_IF_TOUCHED:
            raise ValueError(f"Expected MARKET_IF_TOUCHED order, got {init.order_type}")
        if init.trigger_price is None:
            raise ValueError("MarketIfTouchedOrder requires a trigger_price")
        super().__init__(init)
        self.trigger_price: Price = init.trigger_price
        self.is_triggered: bool = False

    def _apply_updated(self, event: OrderUpdated) -> None:
        super()._apply_updated(event)
        if event.trigger_price is not None:
            self.trigger_price = event.trigger_price
