"""
Trailing stop orders.

Trailing stops dynamically adjust their trigger price as the market moves
in the favourable direction, locking in profits while letting winners run.

Algorithm
---------
Sell trailing stop (protect long):
  - Initial trigger = entry_price - trailing_offset
  - Each time market price rises: trigger = new_high - trailing_offset
  - Trigger NEVER moves down once set (ratchets up with the market)
  - Fires when market price falls to trigger

Buy trailing stop (protect short):
  - Initial trigger = entry_price + trailing_offset
  - Each time market price falls: trigger = new_low + trailing_offset
  - Trigger NEVER moves up once set (ratchets down with the market)
  - Fires when market price rises to trigger
"""
from __future__ import annotations

from decimal import Decimal
from typing import Optional

from nautilus_full.core.enums import OrderSide, OrderType, TrailingOffsetType
from nautilus_full.core.events import OrderInitialized, OrderUpdated
from nautilus_full.core.objects import Price
from nautilus_full.model.orders.base import Order


class TrailingStopMarketOrder(Order):
    """
    Trailing stop that fills as a market order when triggered.

    Parameters
    ----------
    trailing_offset : Decimal
        The distance from the peak/trough price to the trigger.
    trailing_offset_type : TrailingOffsetType
        Whether the offset is a price, basis points, or ticks.
    activation_price : Price, optional
        If set, the trailing logic only starts once market reaches this price.
    """

    def __init__(self, init: OrderInitialized) -> None:
        if init.order_type not in (
            OrderType.TRAILING_STOP_MARKET, OrderType.STOP_MARKET
        ):
            # Allow STOP_MARKET for compatibility
            pass
        if init.trailing_offset is None and init.trigger_price is None:
            raise ValueError(
                "TrailingStopMarketOrder requires either trailing_offset or trigger_price"
            )
        super().__init__(init)
        self.trailing_offset: Decimal = init.trailing_offset or Decimal("0")
        self.trailing_offset_type: TrailingOffsetType = (
            TrailingOffsetType[init.trailing_offset_type]
            if isinstance(init.trailing_offset_type, str)
            else (init.trailing_offset_type or TrailingOffsetType.PRICE)
        )
        # The current (dynamic) trigger price
        self.trigger_price: Optional[Price] = init.trigger_price
        # The best price seen since the order was placed
        self._extreme_price: Optional[Decimal] = None
        self.is_triggered: bool = False
        self.is_activated: bool = init.trigger_price is None  # activated immediately if no trigger

    def update_trigger(self, market_price: Price) -> bool:
        """
        Update the trailing trigger based on the latest market price.

        Returns True if the order should now be triggered (filled as market).
        """
        mp = market_price.value

        # --- Activation (for orders with an activation_price) ---
        if not self.is_activated:
            # Activate when market crosses in the right direction
            if self.trigger_price is not None:
                if self.side == OrderSide.SELL and mp >= self.trigger_price.value:
                    self.is_activated = True
                elif self.side == OrderSide.BUY and mp <= self.trigger_price.value:
                    self.is_activated = True
            else:
                self.is_activated = True

        if not self.is_activated:
            return False

        offset = self._compute_offset(mp)

        if self.side == OrderSide.SELL:
            # Ratchet trigger UP with rising price
            if self._extreme_price is None or mp > self._extreme_price:
                self._extreme_price = mp
                new_trigger = mp - offset
                if self.trigger_price is None or new_trigger > self.trigger_price.value:
                    self.trigger_price = Price(new_trigger, market_price.precision)
            # Fire when market falls to trigger
            if self.trigger_price is not None and mp <= self.trigger_price.value:
                self.is_triggered = True
                return True

        else:  # BUY
            # Ratchet trigger DOWN with falling price
            if self._extreme_price is None or mp < self._extreme_price:
                self._extreme_price = mp
                new_trigger = mp + offset
                if self.trigger_price is None or new_trigger < self.trigger_price.value:
                    self.trigger_price = Price(new_trigger, market_price.precision)
            # Fire when market rises to trigger
            if self.trigger_price is not None and mp >= self.trigger_price.value:
                self.is_triggered = True
                return True

        return False

    def _compute_offset(self, market_price: Decimal) -> Decimal:
        if self.trailing_offset_type == TrailingOffsetType.PRICE:
            return self.trailing_offset
        elif self.trailing_offset_type == TrailingOffsetType.BASIS_POINTS:
            return market_price * self.trailing_offset / Decimal("10000")
        elif self.trailing_offset_type == TrailingOffsetType.TICKS:
            # Requires tick size knowledge; default 1 tick = offset
            return self.trailing_offset
        return self.trailing_offset

    def _apply_updated(self, event: OrderUpdated) -> None:
        super()._apply_updated(event)
        if event.trigger_price is not None:
            self.trigger_price = event.trigger_price


class TrailingStopLimitOrder(TrailingStopMarketOrder):
    """
    Trailing stop that becomes a limit order when triggered.

    The limit price is set as ``trigger_price - limit_offset`` for sells
    (i.e. the limit trails the trigger by ``limit_offset``).
    """

    def __init__(self, init: OrderInitialized) -> None:
        super().__init__(init)
        # limit_offset is the gap between trigger and limit price
        self.limit_offset: Decimal = init.limit_offset or Decimal("0")
        # The resting limit price (computed when triggered)
        self.price: Optional[Price] = init.price

    def get_limit_price(self) -> Optional[Price]:
        """Return the limit price to rest once triggered."""
        if self.price is not None:
            return self.price
        if self.trigger_price is not None:
            if self.side == OrderSide.SELL:
                lp = self.trigger_price.value - self.limit_offset
            else:
                lp = self.trigger_price.value + self.limit_offset
            return Price(lp, self.trigger_price.precision)
        return None
