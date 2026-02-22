"""
Actor — a non-trading component that subscribes to data and events.

Actors are useful for:
  - Recording custom metrics
  - Sending alerts
  - Adjusting risk limits dynamically
  - Aggregating data across strategies

Actors share the same registration interface as Strategy but have no
order-management methods.
"""
from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from nautilus_full.core.identifiers import ActorId, InstrumentId
from nautilus_full.model.data import Bar, BarType, QuoteTick, TradeTick

if TYPE_CHECKING:
    from nautilus_full.core.clock import Clock
    from nautilus_full.core.msgbus import MessageBus
    from nautilus_full.engine.data_engine import DataEngine
    from nautilus_full.state.cache import Cache
    from nautilus_full.state.portfolio import Portfolio


class Actor:
    """
    Non-trading actor component.

    Override on_start(), on_stop(), on_bar(), on_quote_tick(), etc.
    """

    def __init__(self, actor_id: Optional[str] = None) -> None:
        self.id = ActorId(actor_id or type(self).__name__)
        self.clock: Optional[Clock] = None
        self.cache: Optional[Cache] = None
        self.portfolio: Optional[Portfolio] = None
        self.msgbus: Optional[MessageBus] = None
        self._data_engine: Optional[DataEngine] = None

    def register(
        self,
        clock: "Clock",
        cache: "Cache",
        portfolio: "Portfolio",
        msgbus: "MessageBus",
        data_engine: "DataEngine",
    ) -> None:
        self.clock = clock
        self.cache = cache
        self.portfolio = portfolio
        self.msgbus = msgbus
        self._data_engine = data_engine

    # ── Lifecycle ──────────────────────────────────────────────────────────

    def on_start(self) -> None:
        pass

    def on_stop(self) -> None:
        pass

    def on_reset(self) -> None:
        pass

    # ── Data hooks ─────────────────────────────────────────────────────────

    def on_bar(self, bar: Bar) -> None:
        pass

    def on_quote_tick(self, tick: QuoteTick) -> None:
        pass

    def on_trade_tick(self, tick: TradeTick) -> None:
        pass

    def on_data(self, data) -> None:
        pass

    # ── Subscriptions ──────────────────────────────────────────────────────

    def subscribe_bars(self, bar_type: BarType) -> None:
        if self._data_engine:
            self._data_engine.subscribe_bars(bar_type)
        if self.msgbus:
            self.msgbus.subscribe(f"data.bars.{bar_type}", self.on_bar)

    def subscribe_quote_ticks(self, instrument_id: InstrumentId) -> None:
        if self.msgbus:
            self.msgbus.subscribe(f"data.quotes.{instrument_id}", self.on_quote_tick)

    def subscribe_trade_ticks(self, instrument_id: InstrumentId) -> None:
        if self.msgbus:
            self.msgbus.subscribe(f"data.trades.{instrument_id}", self.on_trade_tick)
