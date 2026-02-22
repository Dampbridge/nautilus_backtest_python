"""Market order."""
from __future__ import annotations

from nautilus_full.core.enums import OrderType
from nautilus_full.core.events import OrderInitialized
from nautilus_full.model.orders.base import Order


class MarketOrder(Order):
    """
    Market order — fills immediately at best available price.
    Supports IOC (fill what's available, cancel rest) and FOK (all or nothing).
    """

    def __init__(self, init: OrderInitialized) -> None:
        if init.order_type != OrderType.MARKET:
            raise ValueError(f"Expected MARKET order, got {init.order_type}")
        super().__init__(init)
