"""
Cache — centralized read-through state repository.

The Cache is the single source of truth for:
  - Instruments
  - Orders (all states)
  - Positions
  - Accounts
  - Market data (last quote/trade/bar per instrument)
"""
from __future__ import annotations

from collections import defaultdict
from typing import Optional

from nautilus_full.core.identifiers import (
    AccountId,
    ClientOrderId,
    InstrumentId,
    PositionId,
    StrategyId,
    Venue,
)
from nautilus_full.core.objects import Price
from nautilus_full.model.data import Bar, BarType, QuoteTick, TradeTick
from nautilus_full.model.instruments.base import Instrument
from nautilus_full.model.orders.base import Order
from nautilus_full.model.position import Position


class Cache:
    """
    In-memory state cache.

    All lookups are O(1) via dict.
    """

    def __init__(self) -> None:
        # Instruments
        self._instruments: dict[InstrumentId, Instrument] = {}

        # Orders — keyed by client_order_id
        self._orders: dict[ClientOrderId, Order] = {}
        # Secondary indexes
        self._orders_by_instrument: dict[InstrumentId, set[ClientOrderId]] = defaultdict(set)
        self._orders_by_strategy: dict[StrategyId, set[ClientOrderId]] = defaultdict(set)

        # Positions — keyed by position_id
        self._positions: dict[PositionId, Position] = {}
        self._positions_by_instrument: dict[InstrumentId, set[PositionId]] = defaultdict(set)
        self._positions_by_strategy: dict[StrategyId, set[PositionId]] = defaultdict(set)

        # Accounts
        self._accounts: dict[AccountId, object] = {}

        # Market data — last known per instrument
        self._last_quote: dict[InstrumentId, QuoteTick] = {}
        self._last_trade: dict[InstrumentId, TradeTick] = {}
        self._last_bar: dict[BarType, Bar] = {}
        self._bars: dict[BarType, list[Bar]] = defaultdict(list)  # rolling history

    # ── Instruments ────────────────────────────────────────────────────────

    def add_instrument(self, instrument: Instrument) -> None:
        self._instruments[instrument.id] = instrument

    def instrument(self, instrument_id: InstrumentId) -> Optional[Instrument]:
        return self._instruments.get(instrument_id)

    def instruments(self, venue: Optional[Venue] = None) -> list[Instrument]:
        if venue is None:
            return list(self._instruments.values())
        return [i for i in self._instruments.values() if i.venue == venue]

    # ── Orders ─────────────────────────────────────────────────────────────

    def add_order(self, order: Order) -> None:
        self._orders[order.client_order_id] = order
        self._orders_by_instrument[order.instrument_id].add(order.client_order_id)
        self._orders_by_strategy[order.strategy_id].add(order.client_order_id)

    def order(self, client_order_id: ClientOrderId) -> Optional[Order]:
        return self._orders.get(client_order_id)

    def orders(
        self,
        instrument_id: Optional[InstrumentId] = None,
        strategy_id: Optional[StrategyId] = None,
    ) -> list[Order]:
        if instrument_id is not None:
            ids = self._orders_by_instrument.get(instrument_id, set())
        elif strategy_id is not None:
            ids = self._orders_by_strategy.get(strategy_id, set())
        else:
            return list(self._orders.values())
        return [self._orders[i] for i in ids if i in self._orders]

    def orders_open(
        self,
        instrument_id: Optional[InstrumentId] = None,
        strategy_id: Optional[StrategyId] = None,
    ) -> list[Order]:
        return [o for o in self.orders(instrument_id, strategy_id) if o.is_open]

    def orders_closed(
        self,
        instrument_id: Optional[InstrumentId] = None,
        strategy_id: Optional[StrategyId] = None,
    ) -> list[Order]:
        return [o for o in self.orders(instrument_id, strategy_id) if o.is_closed]

    def orders_filled(
        self,
        instrument_id: Optional[InstrumentId] = None,
        strategy_id: Optional[StrategyId] = None,
    ) -> list[Order]:
        return [o for o in self.orders(instrument_id, strategy_id) if o.is_filled]

    # ── Positions ──────────────────────────────────────────────────────────

    def add_position(self, position: Position) -> None:
        self._positions[position.id] = position
        self._positions_by_instrument[position.instrument_id].add(position.id)
        self._positions_by_strategy[position.strategy_id].add(position.id)

    def position(self, position_id: PositionId) -> Optional[Position]:
        return self._positions.get(position_id)

    def positions(
        self,
        instrument_id: Optional[InstrumentId] = None,
        strategy_id: Optional[StrategyId] = None,
    ) -> list[Position]:
        if instrument_id is not None:
            ids = self._positions_by_instrument.get(instrument_id, set())
        elif strategy_id is not None:
            ids = self._positions_by_strategy.get(strategy_id, set())
        else:
            return list(self._positions.values())
        return [self._positions[i] for i in ids if i in self._positions]

    def positions_open(
        self,
        instrument_id: Optional[InstrumentId] = None,
        strategy_id: Optional[StrategyId] = None,
    ) -> list[Position]:
        return [p for p in self.positions(instrument_id, strategy_id) if p.is_open]

    def positions_closed(
        self,
        instrument_id: Optional[InstrumentId] = None,
        strategy_id: Optional[StrategyId] = None,
    ) -> list[Position]:
        return [p for p in self.positions(instrument_id, strategy_id) if p.is_closed]

    # ── Accounts ───────────────────────────────────────────────────────────

    def add_account(self, account) -> None:
        self._accounts[account.id] = account

    def account(self, account_id: AccountId) -> Optional[object]:
        return self._accounts.get(account_id)

    def accounts(self) -> list:
        return list(self._accounts.values())

    # ── Market data ────────────────────────────────────────────────────────

    def update_quote_tick(self, tick: QuoteTick) -> None:
        self._last_quote[tick.instrument_id] = tick

    def update_trade_tick(self, tick: TradeTick) -> None:
        self._last_trade[tick.instrument_id] = tick

    def update_bar(self, bar: Bar) -> None:
        self._last_bar[bar.bar_type] = bar
        self._bars[bar.bar_type].append(bar)

    def quote_tick(self, instrument_id: InstrumentId) -> Optional[QuoteTick]:
        return self._last_quote.get(instrument_id)

    def trade_tick(self, instrument_id: InstrumentId) -> Optional[TradeTick]:
        return self._last_trade.get(instrument_id)

    def bar(self, bar_type: BarType) -> Optional[Bar]:
        return self._last_bar.get(bar_type)

    def bars(self, bar_type: BarType, count: Optional[int] = None) -> list[Bar]:
        history = self._bars.get(bar_type, [])
        if count is not None:
            return history[-count:]
        return list(history)

    def price(self, instrument_id: InstrumentId) -> Optional[Price]:
        """Best available price for an instrument (quote > trade > bar)."""
        qt = self._last_quote.get(instrument_id)
        if qt:
            from decimal import Decimal
            mid = (qt.bid_price.value + qt.ask_price.value) / 2
            return Price(mid, qt.bid_price.precision)
        tt = self._last_trade.get(instrument_id)
        if tt:
            return tt.price
        # Fall back to last bar close
        for bt, bar in self._last_bar.items():
            if bt.instrument_id == instrument_id:
                return bar.close
        return None

    # ── Reset ──────────────────────────────────────────────────────────────

    def reset(self) -> None:
        self._orders.clear()
        self._orders_by_instrument.clear()
        self._orders_by_strategy.clear()
        self._positions.clear()
        self._positions_by_instrument.clear()
        self._positions_by_strategy.clear()
        self._last_quote.clear()
        self._last_trade.clear()
        self._last_bar.clear()
        self._bars.clear()
