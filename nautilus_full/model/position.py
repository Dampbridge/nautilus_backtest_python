"""
Position tracking.

A Position aggregates all fills for a single instrument (per strategy in
HEDGING mode, or a single shared position in NETTING mode).
"""
from __future__ import annotations

from decimal import Decimal
from typing import Optional

from nautilus_full.core.enums import OrderSide, PositionSide
from nautilus_full.core.events import OrderFilled
from nautilus_full.core.identifiers import (
    AccountId,
    ClientOrderId,
    InstrumentId,
    PositionId,
    StrategyId,
    TraderId,
)
from nautilus_full.core.objects import Currency, Price, Quantity


class Position:
    """
    Tracks an open or closed position built up from OrderFilled events.

    Attributes
    ----------
    quantity : Quantity
        Net absolute quantity currently held.
    side : PositionSide
        LONG, SHORT, or FLAT.
    avg_px_open : Decimal
        Volume-weighted average open price.
    realized_pnl : Decimal
        PnL from closed portions of the position.
    unrealized_pnl : Decimal
        Estimated PnL on the remaining open quantity (mark-to-market).
    """

    def __init__(
        self,
        instrument_id: InstrumentId,
        position_id: PositionId,
        account_id: AccountId,
        trader_id: TraderId,
        strategy_id: StrategyId,
        opening_event: OrderFilled,
        currency: Currency,
        multiplier: Decimal = Decimal("1"),
    ) -> None:
        self.instrument_id = instrument_id
        self.id = position_id
        self.account_id = account_id
        self.trader_id = trader_id
        self.strategy_id = strategy_id
        self.currency = currency
        self.multiplier = multiplier

        # Signed net quantity: positive = long, negative = short
        self._signed_qty: Decimal = Decimal("0")

        # Running totals for avg price calculation
        self._buy_qty: Decimal = Decimal("0")
        self._sell_qty: Decimal = Decimal("0")
        self._buy_cost: Decimal = Decimal("0")   # sum of buy_qty * price
        self._sell_cost: Decimal = Decimal("0")

        # PnL
        self.realized_pnl: Decimal = Decimal("0")
        self.unrealized_pnl: Decimal = Decimal("0")
        self.commissions: Decimal = Decimal("0")

        # History
        self.events: list[OrderFilled] = []
        self.trade_ids: list[str] = []
        self.opening_order_id: ClientOrderId = opening_event.client_order_id
        self.closing_order_id: Optional[ClientOrderId] = None
        self.ts_opened: int = opening_event.ts_event
        self.ts_closed: Optional[int] = None
        self.ts_last: int = opening_event.ts_event

        # Apply the opening fill
        self._apply_fill(opening_event)

    # ── State ──────────────────────────────────────────────────────────────

    @property
    def side(self) -> PositionSide:
        if self._signed_qty > 0:
            return PositionSide.LONG
        elif self._signed_qty < 0:
            return PositionSide.SHORT
        return PositionSide.FLAT

    @property
    def quantity(self) -> Quantity:
        prec = max(self.events[0].last_qty.precision if self.events else 0, 0)
        return Quantity(abs(self._signed_qty), prec)

    @property
    def signed_qty(self) -> Decimal:
        return self._signed_qty

    @property
    def is_open(self) -> bool:
        return self._signed_qty != 0

    @property
    def is_closed(self) -> bool:
        return self._signed_qty == 0 and bool(self.events)

    @property
    def is_long(self) -> bool:
        return self._signed_qty > 0

    @property
    def is_short(self) -> bool:
        return self._signed_qty < 0

    @property
    def avg_px_open(self) -> Decimal:
        """Volume-weighted average open price for the current open leg."""
        if self._signed_qty > 0:
            return self._buy_cost / self._buy_qty if self._buy_qty else Decimal("0")
        elif self._signed_qty < 0:
            return self._sell_cost / self._sell_qty if self._sell_qty else Decimal("0")
        return Decimal("0")

    @property
    def net_qty(self) -> Decimal:
        return abs(self._signed_qty)

    # ── Fill application ───────────────────────────────────────────────────

    def apply(self, event: OrderFilled) -> None:
        self._apply_fill(event)
        self.events.append(event)
        self.ts_last = event.ts_event

    def _apply_fill(self, event: OrderFilled) -> None:
        qty = event.last_qty.value
        px = event.last_px.value
        commission = event.commission.amount

        self.commissions += commission
        self.trade_ids.append(str(event.trade_id))

        if event.order_side == OrderSide.BUY:
            if self._signed_qty < 0:
                # Closing / reducing a short
                close_qty = min(qty, abs(self._signed_qty))
                realized = close_qty * (self.avg_px_open - px) * self.multiplier
                self.realized_pnl += realized - commission
            self._signed_qty += qty
            self._buy_qty += qty
            self._buy_cost += qty * px

        else:  # SELL
            if self._signed_qty > 0:
                # Closing / reducing a long
                close_qty = min(qty, self._signed_qty)
                realized = close_qty * (px - self.avg_px_open) * self.multiplier
                self.realized_pnl += realized - commission
            self._signed_qty -= qty
            self._sell_qty += qty
            self._sell_cost += qty * px

        # Detect close
        if self._signed_qty == 0 and not self.is_closed:
            self.ts_closed = event.ts_event
            self.closing_order_id = event.client_order_id

    def update_unrealized_pnl(self, mark_price: Price) -> None:
        """Recompute unrealized PnL using a new mark price."""
        mp = mark_price.value
        open_qty = abs(self._signed_qty)
        if open_qty == 0:
            self.unrealized_pnl = Decimal("0")
            return
        if self._signed_qty > 0:
            self.unrealized_pnl = open_qty * (mp - self.avg_px_open) * self.multiplier
        else:
            self.unrealized_pnl = open_qty * (self.avg_px_open - mp) * self.multiplier

    @property
    def total_pnl(self) -> Decimal:
        return self.realized_pnl + self.unrealized_pnl

    def __repr__(self) -> str:
        return (
            f"Position({self.id} {self.instrument_id} "
            f"qty={self._signed_qty} "
            f"avg_px={self.avg_px_open:.4f} "
            f"rpnl={self.realized_pnl:.2f})"
        )
