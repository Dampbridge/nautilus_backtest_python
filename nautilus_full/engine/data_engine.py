"""
DataEngine — routes market data from the event loop to subscribed handlers.

Strategies subscribe to instruments/bar types and the engine dispatches
data updates via the MessageBus.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from nautilus_full.core.identifiers import InstrumentId
from nautilus_full.model.data import Bar, BarType, OrderBookDelta, OrderBookDeltas, QuoteTick, TradeTick

if TYPE_CHECKING:
    from nautilus_full.core.msgbus import MessageBus
    from nautilus_full.state.cache import Cache


class DataEngine:
    """
    Receives data from the backtest event loop and:
    1. Updates the Cache with the latest data.
    2. Publishes to MessageBus topics for strategy subscriptions.
    """

    def __init__(self, cache: "Cache", msgbus: "MessageBus") -> None:
        self._cache = cache
        self._msgbus = msgbus
        self._bar_subscriptions: set[BarType] = set()
        self._quote_subscriptions: set[InstrumentId] = set()
        self._trade_subscriptions: set[InstrumentId] = set()

    # ── Subscriptions ──────────────────────────────────────────────────────

    def subscribe_bars(self, bar_type: BarType) -> None:
        self._bar_subscriptions.add(bar_type)

    def subscribe_quote_ticks(self, instrument_id: InstrumentId) -> None:
        self._quote_subscriptions.add(instrument_id)

    def subscribe_trade_ticks(self, instrument_id: InstrumentId) -> None:
        self._trade_subscriptions.add(instrument_id)

    def unsubscribe_bars(self, bar_type: BarType) -> None:
        self._bar_subscriptions.discard(bar_type)

    def unsubscribe_quote_ticks(self, instrument_id: InstrumentId) -> None:
        self._quote_subscriptions.discard(instrument_id)

    # ── Data processing ────────────────────────────────────────────────────

    def process_bar(self, bar: Bar) -> None:
        self._cache.update_bar(bar)
        topic = f"data.bars.{bar.bar_type}"
        self._msgbus.publish(topic, bar)

    def process_quote_tick(self, tick: QuoteTick) -> None:
        self._cache.update_quote_tick(tick)
        topic = f"data.quotes.{tick.instrument_id}"
        self._msgbus.publish(topic, tick)

    def process_trade_tick(self, tick: TradeTick) -> None:
        self._cache.update_trade_tick(tick)
        topic = f"data.trades.{tick.instrument_id}"
        self._msgbus.publish(topic, tick)

    def process_book_delta(self, delta: OrderBookDelta) -> None:
        topic = f"data.book.{delta.instrument_id}"
        self._msgbus.publish(topic, delta)

    def process_book_deltas(self, deltas: OrderBookDeltas) -> None:
        for delta in deltas.deltas:
            self.process_book_delta(delta)

    # ── Stats ──────────────────────────────────────────────────────────────

    @property
    def bar_subscription_count(self) -> int:
        return len(self._bar_subscriptions)

    @property
    def quote_subscription_count(self) -> int:
        return len(self._quote_subscriptions)
