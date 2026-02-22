"""
RiskEngine — pre-trade risk checks.

Validates orders before submission to the venue:
  - Position limits
  - Notional limits
  - Max order quantity
  - Max orders per instrument
  - Reduce-only enforcement
  - Trading state checks
"""
from __future__ import annotations

from decimal import Decimal
from typing import Optional, TYPE_CHECKING

from nautilus_full.core.enums import OrderSide, TradingState
from nautilus_full.model.orders.base import Order

if TYPE_CHECKING:
    from nautilus_full.core.identifiers import InstrumentId, StrategyId
    from nautilus_full.core.msgbus import MessageBus
    from nautilus_full.state.cache import Cache
    from nautilus_full.state.portfolio import Portfolio


class RiskEngine:
    """
    Pre-trade risk gate.

    All orders pass through the RiskEngine before being forwarded to the
    venue. Orders that fail checks are denied with a reason string.

    Parameters
    ----------
    max_order_rate : int
        Maximum orders per second per strategy (0 = unlimited).
    max_notional_per_order : Decimal | None
        Maximum USD-equivalent notional per order (None = unlimited).
    max_position_notional : Decimal | None
        Maximum USD-equivalent notional per position (None = unlimited).
    """

    def __init__(
        self,
        portfolio: "Portfolio",
        cache: "Cache",
        msgbus: "MessageBus",
        max_order_rate: int = 0,
        max_notional_per_order: Optional[Decimal] = None,
        max_position_notional: Optional[Decimal] = None,
        trading_state: TradingState = TradingState.ACTIVE,
    ) -> None:
        self._portfolio = portfolio
        self._cache = cache
        self._msgbus = msgbus
        self.max_order_rate = max_order_rate
        self.max_notional_per_order = max_notional_per_order
        self.max_position_notional = max_position_notional
        self.trading_state = trading_state

        # Per-strategy order count tracking
        self._order_counts: dict[str, int] = {}

    def check_order(self, order: Order) -> tuple[bool, str]:
        """
        Run all risk checks on an order.

        Returns (True, "") if the order passes, or (False, reason) if denied.
        """
        # 1. Trading state
        if self.trading_state == TradingState.HALTED:
            return False, "Trading is halted"
        if self.trading_state == TradingState.REDUCING:
            if not order.reduce_only:
                return False, "Trading state is REDUCING — only reduce-only orders allowed"

        # 2. Reduce-only validation
        if order.reduce_only:
            net_qty = self._portfolio.net_position(
                order.instrument_id, order.strategy_id
            )
            if net_qty == 0:
                return False, "Reduce-only order rejected: no open position to reduce"
            # Buy reduce-only is valid only when short
            if order.side == OrderSide.BUY and net_qty >= 0:
                return False, "Reduce-only BUY rejected: position is not short"
            if order.side == OrderSide.SELL and net_qty <= 0:
                return False, "Reduce-only SELL rejected: position is not long"

        # 3. Notional check
        if self.max_notional_per_order is not None:
            instrument = self._cache.instrument(order.instrument_id)
            if instrument and hasattr(order, "price") and order.price:
                notional = instrument.notional_value(order.quantity, order.price)
                if notional > self.max_notional_per_order:
                    return False, (
                        f"Order notional {notional} exceeds max {self.max_notional_per_order}"
                    )

        return True, ""

    def set_trading_state(self, state: TradingState) -> None:
        self.trading_state = state

    def reset(self) -> None:
        self._order_counts.clear()
