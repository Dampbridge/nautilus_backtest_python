"""
OrderMatchingEngine — full L2 order book matching per instrument.

Responsibilities:
  - Maintain an L2 order book (from real deltas, quotes, or bars)
  - Match incoming market/limit/stop orders against the book
  - Track resting limit orders and trigger them when price crosses
  - Handle trailing stops (update trigger dynamically)
  - Enforce IOC (fill-or-cancel) and FOK (fill-or-kill) semantics
  - Manage OCO contingencies (cancel sibling on fill)
  - Handle partial fills
  - Fire fill events through callbacks
"""
from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Callable, Optional

from nautilus_full.core.enums import (
    ContingencyType,
    LiquiditySide,
    OrderSide,
    OrderStatus,
    OrderType,
    TimeInForce,
)
from nautilus_full.core.events import (
    OrderCanceled,
    OrderExpired,
    OrderFilled,
    OrderTriggered,
)
from nautilus_full.core.identifiers import (
    AccountId,
    ClientOrderId,
    TradeId,
    VenueOrderId,
)
from nautilus_full.core.objects import Money, Price, Quantity
from nautilus_full.model.data import Bar, OrderBookDelta, OrderBookDeltas, QuoteTick, TradeTick
from nautilus_full.model.instruments.base import Instrument
from nautilus_full.model.orders.base import Order
from nautilus_full.model.orders.limit import LimitOrder
from nautilus_full.model.orders.limit_if_touched import LimitIfTouchedOrder
from nautilus_full.model.orders.market_if_touched import MarketIfTouchedOrder
from nautilus_full.model.orders.stop_limit import StopLimitOrder
from nautilus_full.model.orders.stop_market import StopMarketOrder
from nautilus_full.model.orders.trailing_stop import TrailingStopLimitOrder, TrailingStopMarketOrder
from nautilus_full.venues.models import FeeModel, FillModel


class OrderMatchingEngine:
    """
    Per-instrument matching engine.

    Parameters
    ----------
    instrument : Instrument
        The instrument being traded.
    fill_model : FillModel
        Controls fill probability and slippage in simulation.
    fee_model : FeeModel
        Computes commissions per fill.
    account_id : AccountId
        The venue account.
    on_fill : Callable
        Callback fired with each OrderFilled event.
    on_cancel : Callable
        Callback fired with each OrderCanceled event.
    on_expire : Callable
        Callback fired with each OrderExpired event.
    on_trigger : Callable
        Callback fired when a stop/MIT order is triggered.
    book_spread_pct : Decimal
        Used when synthesizing an L2 book from bar/quote data.
    """

    def __init__(
        self,
        instrument: Instrument,
        fill_model: FillModel,
        fee_model: FeeModel,
        account_id: AccountId,
        on_fill: Callable[[OrderFilled], None],
        on_cancel: Callable[[OrderCanceled], None],
        on_expire: Callable[[OrderExpired], None],
        on_trigger: Optional[Callable[[OrderTriggered], None]] = None,
        book_spread_pct: Decimal = Decimal("0.0001"),
    ) -> None:
        self.instrument = instrument
        self.fill_model = fill_model
        self.fee_model = fee_model
        self.account_id = account_id
        self._on_fill = on_fill
        self._on_cancel = on_cancel
        self._on_expire = on_expire
        self._on_trigger = on_trigger or (lambda e: None)
        self.book_spread_pct = book_spread_pct

        # L2 order book
        from nautilus_full.model.data import OrderBook
        from nautilus_full.core.enums import BookType
        self.book = OrderBook(instrument.id, BookType.L2_MBP)

        # Resting orders: client_order_id -> Order
        self._resting: dict[ClientOrderId, Order] = {}

        # Trailing stop orders: separately tracked
        self._trailing_stops: dict[ClientOrderId, Order] = {}

        # Stop/MIT orders waiting for trigger
        self._stops: dict[ClientOrderId, Order] = {}

        # Trade counter
        self._trade_count = 0
        self._venue_order_count = 0

        # Last known prices
        self._last_price: Optional[Price] = None
        self._last_bid: Optional[Price] = None
        self._last_ask: Optional[Price] = None

        # Contingency groups: order_list_id -> list of client_order_ids
        self._contingency_groups: dict[str, list[ClientOrderId]] = {}

    # ── Book updates ───────────────────────────────────────────────────────

    def process_book_delta(self, delta: OrderBookDelta) -> None:
        self.book.apply_delta(delta)
        self._check_resting_orders()

    def process_book_deltas(self, deltas: OrderBookDeltas) -> None:
        self.book.apply_deltas(deltas)
        self._check_resting_orders()

    def process_quote_tick(self, tick: QuoteTick) -> None:
        self._last_bid = tick.bid_price
        self._last_ask = tick.ask_price
        mid = Price(
            (tick.bid_price.value + tick.ask_price.value) / 2,
            tick.bid_price.precision,
        )
        self._last_price = mid
        self.book.update_from_quote(tick)
        self._update_trailing_stops(mid, tick.ts_event)
        self._check_resting_orders()

    def process_trade_tick(self, tick: TradeTick) -> None:
        self._last_price = tick.price
        self._update_trailing_stops(tick.price, tick.ts_event)
        self._check_resting_orders()

    def process_bar(self, bar: Bar) -> None:
        """
        Process an OHLCV bar through the matching engine.

        Bar traversal order (NautilusTrader convention):
          1. Open  → fill market orders, check stop/MIT triggers
          2. High  → check sell limit / buy stop triggers
          3. Low   → check buy limit / sell stop triggers
          4. Close → update trailing stops, expire DAY orders
        """
        ts = bar.ts_event
        self.book.update_from_bar(bar, self.book_spread_pct)

        # Step 1: open price — fill any queued market orders
        self._last_price = bar.open
        self._process_at_price(bar.open, ts, is_open=True)

        # Step 2: high — sell limit fills / buy stop & MIT triggers
        self._last_price = bar.high
        self._process_at_price(bar.high, ts, is_high=True)

        # Step 3: low — buy limit fills / sell stop & MIT triggers
        self._last_price = bar.low
        self._process_at_price(bar.low, ts, is_low=True)

        # Step 4: close — update trailing stops, expire DAY orders
        self._last_price = bar.close
        self._update_trailing_stops(bar.close, ts)
        self._expire_day_orders(ts)

    # ── Order lifecycle ────────────────────────────────────────────────────

    def process_order(self, order: Order, ts: int) -> None:
        """
        Process an incoming order (just accepted by the venue).

        Routes to the appropriate matching logic based on order type.
        """
        self._register_contingency(order)

        if order.order_type == OrderType.MARKET:
            self._match_market(order, ts)

        elif order.order_type == OrderType.LIMIT:
            self._match_limit_or_rest(order, ts)

        elif order.order_type == OrderType.STOP_MARKET:
            if self._is_stop_triggered(order, self._last_price):
                self._match_market(order, ts)
            else:
                self._stops[order.client_order_id] = order

        elif order.order_type == OrderType.STOP_LIMIT:
            if self._is_stop_triggered(order, self._last_price):
                self._convert_stop_limit(order, ts)
            else:
                self._stops[order.client_order_id] = order

        elif order.order_type in (OrderType.TRAILING_STOP_MARKET, OrderType.TRAILING_STOP_LIMIT):
            self._trailing_stops[order.client_order_id] = order

        elif order.order_type == OrderType.MARKET_IF_TOUCHED:
            if self._is_mit_triggered(order, self._last_price):
                self._match_market(order, ts)
            else:
                self._stops[order.client_order_id] = order

        elif order.order_type == OrderType.LIMIT_IF_TOUCHED:
            if self._is_mit_triggered(order, self._last_price):
                self._resting[order.client_order_id] = order
            else:
                self._stops[order.client_order_id] = order

    def cancel_order(self, order: Order, ts: int) -> None:
        self._remove_resting(order.client_order_id)
        self._stops.pop(order.client_order_id, None)
        self._trailing_stops.pop(order.client_order_id, None)
        self._fire_cancel(order, ts)

    def modify_order(
        self,
        order: Order,
        quantity: Optional[Quantity] = None,
        price: Optional[Price] = None,
        trigger_price: Optional[Price] = None,
        ts: int = 0,
    ) -> None:
        from nautilus_full.core.events import OrderUpdated
        event = OrderUpdated(
            trader_id=order.trader_id,
            strategy_id=order.strategy_id,
            instrument_id=order.instrument_id,
            client_order_id=order.client_order_id,
            venue_order_id=order.venue_order_id,
            account_id=self.account_id,
            quantity=quantity,
            price=price,
            trigger_price=trigger_price,
            ts_event=ts,
            ts_init=ts,
        )
        order.apply(event)
        # Re-check if the modification causes an immediate fill
        if order.client_order_id in self._resting:
            self._check_single_order(order, self._last_price, ts)

    # ── Internal matching logic ────────────────────────────────────────────

    def _match_market(self, order: Order, ts: int) -> None:
        """Sweep the book for a market order with IOC/FOK handling."""
        fills = self.book.simulate_market_fill(order.side, order.leaves_qty.value)

        if order.time_in_force == TimeInForce.FOK:
            total_avail = sum(qty for _, qty in fills)
            if total_avail < order.leaves_qty.value:
                self._fire_cancel(order, ts)
                return

        for px_d, qty_d in fills:
            if order.leaves_qty.is_zero():
                break
            fill_qty = min(qty_d, order.leaves_qty.value)
            px = Price(px_d, self.instrument.price_precision)

            # Apply fill model slippage
            px = self.fill_model.apply_slippage(px, order.side, self.instrument)

            self._fire_fill(order, Price(px_d, self.instrument.price_precision), fill_qty, LiquiditySide.TAKER, ts)

        # IOC: cancel remainder
        if order.time_in_force == TimeInForce.IOC and not order.leaves_qty.is_zero():
            self._fire_cancel(order, ts)

    def _match_limit_or_rest(self, order: LimitOrder, ts: int) -> None:
        """Fill limit order if it crosses the spread, otherwise rest it."""
        # post_only: reject if it would fill immediately
        if order.post_only:
            if self._would_fill_immediately(order):
                from nautilus_full.core.events import OrderRejected
                self._on_cancel(OrderCanceled(
                    trader_id=order.trader_id,
                    strategy_id=order.strategy_id,
                    instrument_id=order.instrument_id,
                    client_order_id=order.client_order_id,
                    venue_order_id=order.venue_order_id,
                    account_id=self.account_id,
                    ts_event=ts,
                    ts_init=ts,
                ))
                return

        # Try immediate fill
        filled = self._fill_limit(order, ts, liquidity_side=LiquiditySide.TAKER)

        if not order.leaves_qty.is_zero() and not order.is_closed:
            if order.time_in_force == TimeInForce.IOC:
                self._fire_cancel(order, ts)
            elif order.time_in_force == TimeInForce.FOK:
                self._fire_cancel(order, ts)
            else:
                # Rest in book
                self._resting[order.client_order_id] = order

    def _fill_limit(self, order: LimitOrder, ts: int, liquidity_side: LiquiditySide) -> bool:
        """Attempt to fill a limit order. Returns True if any fill occurred."""
        if not hasattr(order, "price"):
            return False
        if self._last_price is None and self.book.best_bid_price is None:
            return False

        any_fill = False
        if order.side == OrderSide.BUY:
            # Fill against asks below or at the limit
            for px_d, avail in self.book.asks():
                if Decimal(str(px_d)) > order.price.value:
                    break
                if order.leaves_qty.is_zero():
                    break
                fill_qty = min(avail, order.leaves_qty.value)
                fill_px = min(Decimal(str(px_d)), order.price.value)
                self._fire_fill(order, Price(fill_px, self.instrument.price_precision), fill_qty, liquidity_side, ts)
                any_fill = True
        else:
            # Fill against bids at or above the limit
            for px_d, avail in self.book.bids():
                if Decimal(str(px_d)) < order.price.value:
                    break
                if order.leaves_qty.is_zero():
                    break
                fill_qty = min(avail, order.leaves_qty.value)
                fill_px = max(Decimal(str(px_d)), order.price.value)
                self._fire_fill(order, Price(fill_px, self.instrument.price_precision), fill_qty, liquidity_side, ts)
                any_fill = True

        return any_fill

    def _convert_stop_limit(self, order: StopLimitOrder, ts: int) -> None:
        """Stop-limit triggered: fire OrderTriggered then rest as limit."""
        order.is_triggered = True
        self._fire_triggered(order, ts)
        self._resting[order.client_order_id] = order

    def _check_resting_orders(self) -> None:
        """Check if any resting limit orders should now fill."""
        if not self._resting:
            return
        ts = self._get_ts()
        for oid in list(self._resting):
            order = self._resting.get(oid)
            if order is None or not order.is_open:
                self._resting.pop(oid, None)
                continue
            self._check_single_order(order, self._last_price, ts)

    def _check_single_order(self, order: Order, market_price: Optional[Price], ts: int) -> None:
        if not hasattr(order, "price") or market_price is None:
            return
        if order.leaves_qty.is_zero() or order.is_closed:
            self._remove_resting(order.client_order_id)
            return
        self._fill_limit(order, ts, LiquiditySide.MAKER)  # type: ignore
        if order.is_filled or order.is_closed:
            self._remove_resting(order.client_order_id)

    def _process_at_price(
        self,
        price: Price,
        ts: int,
        is_open: bool = False,
        is_high: bool = False,
        is_low: bool = False,
    ) -> None:
        """Process triggers and fills at a given bar price level."""
        self._last_price = price

        # 1. Fill resting market orders (only at bar open)
        if is_open:
            mkt_orders = [o for o in list(self._resting.values())
                          if o.order_type == OrderType.MARKET and o.is_open]
            for order in mkt_orders:
                self._fire_fill(order, price, order.leaves_qty.value, LiquiditySide.TAKER, ts)
                self._remove_resting(order.client_order_id)

        # 2. Check stop/MIT triggers
        triggered = []
        for oid, order in list(self._stops.items()):
            if not order.is_open:
                self._stops.pop(oid)
                continue
            if self._is_stop_triggered(order, price) or self._is_mit_triggered(order, price):
                triggered.append(order)
                self._stops.pop(oid)

        for order in triggered:
            if order.order_type in (OrderType.STOP_MARKET, OrderType.MARKET_IF_TOUCHED):
                self._fire_triggered(order, ts)
                # Fill at trigger price (or bar open, whichever is worse for the trader)
                fill_px = Price(
                    max(order.trigger_price.value, price.value) if order.side == OrderSide.BUY
                    else min(order.trigger_price.value, price.value),
                    self.instrument.price_precision,
                )
                self._fire_fill(order, fill_px, order.leaves_qty.value, LiquiditySide.TAKER, ts)
            elif order.order_type in (OrderType.STOP_LIMIT, OrderType.LIMIT_IF_TOUCHED):
                self._convert_stop_limit(order, ts)  # type: ignore

        # 3. Check resting limit orders
        for oid in list(self._resting):
            order = self._resting.get(oid)
            if order is None or not order.is_open:
                self._remove_resting(oid)
                continue
            if not hasattr(order, "price"):
                continue
            should_fill = (
                (is_high and order.side == OrderSide.SELL and price >= order.price) or  # type: ignore
                (is_low and order.side == OrderSide.BUY and price <= order.price) or  # type: ignore
                (is_open and (
                    (order.side == OrderSide.BUY and price <= order.price) or  # type: ignore
                    (order.side == OrderSide.SELL and price >= order.price)    # type: ignore
                ))
            )
            if should_fill:
                # Fill at the better of limit price and bar price
                if order.side == OrderSide.BUY:
                    fill_px_d = min(order.price.value, price.value)
                else:
                    fill_px_d = max(order.price.value, price.value)
                fill_px = Price(fill_px_d, self.instrument.price_precision)
                self._fire_fill(order, fill_px, order.leaves_qty.value, LiquiditySide.MAKER, ts)
                if order.is_filled or order.is_closed:
                    self._remove_resting(oid)

    def _update_trailing_stops(self, market_price: Price, ts: int) -> None:
        for oid in list(self._trailing_stops):
            order = self._trailing_stops.get(oid)
            if order is None or not order.is_open:
                self._trailing_stops.pop(oid, None)
                continue
            if isinstance(order, (TrailingStopMarketOrder, TrailingStopLimitOrder)):
                triggered = order.update_trigger(market_price)
                if triggered:
                    self._trailing_stops.pop(oid)
                    self._fire_triggered(order, ts)
                    if isinstance(order, TrailingStopLimitOrder):
                        # Become a resting limit order
                        order.price = order.get_limit_price()
                        self._resting[order.client_order_id] = order
                    else:
                        # Fill as market at trigger price
                        fill_px = order.trigger_price or market_price
                        self._fire_fill(order, fill_px, order.leaves_qty.value, LiquiditySide.TAKER, ts)

    def _expire_day_orders(self, ts: int) -> None:
        for oid in list(self._resting):
            order = self._resting[oid]
            if order.time_in_force == TimeInForce.DAY:
                self._resting.pop(oid)
                event = OrderExpired(
                    trader_id=order.trader_id,
                    strategy_id=order.strategy_id,
                    instrument_id=order.instrument_id,
                    client_order_id=order.client_order_id,
                    venue_order_id=order.venue_order_id,
                    account_id=self.account_id,
                    ts_event=ts,
                    ts_init=ts,
                )
                order.apply(event)
                self._on_expire(event)

    # ── Contingency management ─────────────────────────────────────────────

    def _register_contingency(self, order: Order) -> None:
        if order.contingency_type == ContingencyType.NO_CONTINGENCY:
            return
        if order.order_list_id:
            gid = str(order.order_list_id)
            group = self._contingency_groups.setdefault(gid, [])
            if order.client_order_id not in group:
                group.append(order.client_order_id)

    def _handle_contingency_fill(self, order: Order, ts: int) -> None:
        if order.contingency_type == ContingencyType.OCO and order.order_list_id:
            gid = str(order.order_list_id)
            siblings = self._contingency_groups.get(gid, [])
            for sid in siblings:
                if sid == order.client_order_id:
                    continue
                sibling = self._resting.pop(sid, None) or self._stops.pop(sid, None) or self._trailing_stops.pop(sid, None)
                if sibling and sibling.is_open:
                    self._fire_cancel(sibling, ts)

    # ── Event firing ───────────────────────────────────────────────────────

    def _fire_fill(
        self,
        order: Order,
        fill_px: Price,
        fill_qty_d: Decimal,
        liquidity_side: LiquiditySide,
        ts: int,
    ) -> None:
        if order.is_closed or not order.is_open:
            return
        self._trade_count += 1
        fill_qty = Quantity(
            min(fill_qty_d, order.leaves_qty.value),
            order.quantity.precision,
        )
        if fill_qty.is_zero():
            return

        self._venue_order_count += 1
        venue_order_id = order.venue_order_id or VenueOrderId(
            f"V-{self.instrument.venue}-{self._venue_order_count}"
        )
        trade_id = TradeId(f"T-{self.instrument.venue}-{self._trade_count}")

        commission = self.fee_model.calculate(
            order=order,
            fill_qty=fill_qty,
            fill_px=fill_px,
            instrument=self.instrument,
            liquidity_side=liquidity_side,
        )

        event = OrderFilled(
            trader_id=order.trader_id,
            strategy_id=order.strategy_id,
            instrument_id=order.instrument_id,
            client_order_id=order.client_order_id,
            venue_order_id=venue_order_id,
            account_id=self.account_id,
            trade_id=trade_id,
            order_side=order.side,
            order_type=order.order_type,
            last_qty=fill_qty,
            last_px=fill_px,
            currency=self.instrument.quote_currency,
            commission=commission,
            liquidity_side=liquidity_side,
            ts_event=ts,
            ts_init=ts,
        )
        order.apply(event)
        self._on_fill(event)

        # Handle contingency
        if order.is_filled:
            self._handle_contingency_fill(order, ts)

    def _fire_cancel(self, order: Order, ts: int) -> None:
        event = OrderCanceled(
            trader_id=order.trader_id,
            strategy_id=order.strategy_id,
            instrument_id=order.instrument_id,
            client_order_id=order.client_order_id,
            venue_order_id=order.venue_order_id,
            account_id=self.account_id,
            ts_event=ts,
            ts_init=ts,
        )
        order.apply(event)
        self._on_cancel(event)

    def _fire_triggered(self, order: Order, ts: int) -> None:
        event = OrderTriggered(
            trader_id=order.trader_id,
            strategy_id=order.strategy_id,
            instrument_id=order.instrument_id,
            client_order_id=order.client_order_id,
            venue_order_id=order.venue_order_id,
            account_id=self.account_id,
            ts_event=ts,
            ts_init=ts,
        )
        order.apply(event)
        self._on_trigger(event)

    # ── Trigger predicates ─────────────────────────────────────────────────

    def _is_stop_triggered(self, order: Order, price: Optional[Price]) -> bool:
        if price is None or not hasattr(order, "trigger_price"):
            return False
        tp = order.trigger_price
        if tp is None:
            return False
        if order.side == OrderSide.BUY:
            return price >= tp
        return price <= tp

    def _is_mit_triggered(self, order: Order, price: Optional[Price]) -> bool:
        if price is None or not hasattr(order, "trigger_price"):
            return False
        tp = order.trigger_price
        if tp is None:
            return False
        # MIT triggers on touch (opposite direction from stop)
        if order.side == OrderSide.BUY:
            return price <= tp   # buy the dip
        return price >= tp       # sell the rally

    def _would_fill_immediately(self, order: LimitOrder) -> bool:
        if order.side == OrderSide.BUY:
            ask = self.book.best_ask_price
            return ask is not None and order.price.value >= ask
        else:
            bid = self.book.best_bid_price
            return bid is not None and order.price.value <= bid

    # ── Utilities ──────────────────────────────────────────────────────────

    def _remove_resting(self, order_id: ClientOrderId) -> None:
        self._resting.pop(order_id, None)

    def _get_ts(self) -> int:
        return 0  # caller supplies ts in process_ methods

    @property
    def open_order_count(self) -> int:
        return (
            len(self._resting) +
            len(self._stops) +
            len(self._trailing_stops)
        )

    def reset(self) -> None:
        self._resting.clear()
        self._stops.clear()
        self._trailing_stops.clear()
        self._contingency_groups.clear()
        self.book.clear()
        self._last_price = None
        self._last_bid = None
        self._last_ask = None
