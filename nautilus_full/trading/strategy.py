"""
Strategy base class.

All user strategies extend this class and override the lifecycle hooks:
  on_start()     — called once when the backtest begins
  on_stop()      — called once when the backtest ends
  on_bar()       — called on each new bar
  on_quote_tick()
  on_trade_tick()
  on_order_*()   — order event callbacks
  on_position_*() — position event callbacks

Order management:
  submit_order()       — submit any Order object
  cancel_order()       — cancel an open order
  modify_order()       — amend quantity/price/trigger
  cancel_all_orders()  — cancel all open orders for an instrument
  close_position()     — close a position with a market order
  close_all_positions()
"""
from __future__ import annotations

from decimal import Decimal
from typing import Optional, TYPE_CHECKING

from nautilus_full.core.enums import OrderSide, TimeInForce, TrailingOffsetType
from nautilus_full.core.events import (
    OrderAccepted,
    OrderCanceled,
    OrderDenied,
    OrderExpired,
    OrderFilled,
    OrderRejected,
    OrderSubmitted,
    OrderTriggered,
    PositionChanged,
    PositionClosed,
    PositionOpened,
)
from nautilus_full.core.identifiers import InstrumentId, StrategyId
from nautilus_full.core.objects import Price, Quantity
from nautilus_full.model.data import Bar, BarType, QuoteTick, TradeTick
from nautilus_full.model.orders.base import Order
from nautilus_full.trading.config import StrategyConfig

if TYPE_CHECKING:
    from nautilus_full.core.clock import Clock
    from nautilus_full.core.msgbus import MessageBus
    from nautilus_full.engine.data_engine import DataEngine
    from nautilus_full.engine.execution_engine import ExecutionEngine
    from nautilus_full.model.orders.factory import OrderFactory
    from nautilus_full.state.cache import Cache
    from nautilus_full.state.portfolio import Portfolio


class Strategy:
    """
    Abstract base class for all trading strategies.

    The backtest engine calls ``register()`` to inject dependencies, then
    calls the lifecycle methods in order.
    """

    def __init__(self, config: Optional[StrategyConfig] = None) -> None:
        self.config = config or StrategyConfig()
        self.id = StrategyId(self.config.strategy_id or type(self).__name__)

        # Injected by the engine at registration time
        self.clock: Optional[Clock] = None
        self.cache: Optional[Cache] = None
        self.portfolio: Optional[Portfolio] = None
        self.msgbus: Optional[MessageBus] = None
        self.order_factory: Optional[OrderFactory] = None
        self._exec_engine: Optional[ExecutionEngine] = None
        self._data_engine: Optional[DataEngine] = None

        # Indicator registry: BarType -> list of indicators
        self._indicators: dict[BarType, list] = {}
        self._registered = False

    # ── Registration ───────────────────────────────────────────────────────

    def register(
        self,
        clock: "Clock",
        cache: "Cache",
        portfolio: "Portfolio",
        msgbus: "MessageBus",
        order_factory: "OrderFactory",
        exec_engine: "ExecutionEngine",
        data_engine: "DataEngine",
    ) -> None:
        self.clock = clock
        self.cache = cache
        self.portfolio = portfolio
        self.msgbus = msgbus
        self.order_factory = order_factory
        self._exec_engine = exec_engine
        self._data_engine = data_engine

        # Subscribe to order and position events for this strategy
        msgbus.subscribe(f"events.order.{self.id}", self._handle_order_event)
        msgbus.subscribe(f"events.position.{self.id}", self._handle_position_event)

        self._registered = True

    # ── Lifecycle hooks ────────────────────────────────────────────────────

    def on_start(self) -> None:
        """Called once when the engine starts. Set up subscriptions here."""

    def on_stop(self) -> None:
        """Called once when the engine stops (end of backtest)."""

    def on_reset(self) -> None:
        """Called when the engine is reset for a new run."""

    def on_dispose(self) -> None:
        """Called when the strategy is being disposed."""

    # ── Market data hooks ──────────────────────────────────────────────────

    def on_bar(self, bar: Bar) -> None:
        """Called on each new bar for subscribed bar types."""

    def on_quote_tick(self, tick: QuoteTick) -> None:
        """Called on each new quote tick."""

    def on_trade_tick(self, tick: TradeTick) -> None:
        """Called on each new trade tick."""

    def on_data(self, data) -> None:
        """Called with custom data objects."""

    # ── Order event hooks ──────────────────────────────────────────────────

    def on_order_initialized(self, event: "OrderInitialized") -> None:
        pass

    def on_order_submitted(self, event: OrderSubmitted) -> None:
        pass

    def on_order_accepted(self, event: OrderAccepted) -> None:
        pass

    def on_order_rejected(self, event: OrderRejected) -> None:
        pass

    def on_order_denied(self, event: OrderDenied) -> None:
        pass

    def on_order_canceled(self, event: OrderCanceled) -> None:
        pass

    def on_order_expired(self, event: OrderExpired) -> None:
        pass

    def on_order_filled(self, event: OrderFilled) -> None:
        pass

    def on_order_triggered(self, event: OrderTriggered) -> None:
        pass

    # ── Position event hooks ───────────────────────────────────────────────

    def on_position_opened(self, event: PositionOpened) -> None:
        pass

    def on_position_changed(self, event: PositionChanged) -> None:
        pass

    def on_position_closed(self, event: PositionClosed) -> None:
        pass

    # ── Order management ───────────────────────────────────────────────────

    def submit_order(self, order: Order) -> None:
        """Submit an order to the execution engine."""
        if self._exec_engine:
            self._exec_engine.submit_order(order)

    def cancel_order(self, order: Order) -> None:
        """Cancel an open order."""
        if self._exec_engine and self.clock:
            self._exec_engine.cancel_order(order, ts=self.clock.timestamp_ns())

    def modify_order(
        self,
        order: Order,
        quantity: Optional[Quantity] = None,
        price: Optional[Price] = None,
        trigger_price: Optional[Price] = None,
    ) -> None:
        """Amend an open order's quantity, price, or trigger price."""
        if self._exec_engine and self.clock:
            self._exec_engine.modify_order(
                order,
                quantity=quantity,
                price=price,
                trigger_price=trigger_price,
                ts=self.clock.timestamp_ns(),
            )

    def cancel_all_orders(self, instrument_id: InstrumentId) -> None:
        """Cancel all open orders for the given instrument."""
        if self.cache:
            for order in self.cache.orders_open(
                instrument_id=instrument_id, strategy_id=self.id
            ):
                self.cancel_order(order)

    def close_position(self, position, ts_init: int = 0) -> None:
        """Close a position with a market order."""
        if not position.is_open or self.order_factory is None:
            return
        side = OrderSide.SELL if position.is_long else OrderSide.BUY
        ts = ts_init or (self.clock.timestamp_ns() if self.clock else 0)
        order = self.order_factory.market(
            instrument_id=position.instrument_id,
            order_side=side,
            quantity=position.quantity,
            reduce_only=True,
            ts_init=ts,
        )
        self.submit_order(order)

    def close_all_positions(self, instrument_id: InstrumentId, ts_init: int = 0) -> None:
        """Close all open positions for the given instrument."""
        if self.cache:
            for pos in self.cache.positions_open(
                instrument_id=instrument_id, strategy_id=self.id
            ):
                self.close_position(pos, ts_init=ts_init)

    # ── Data subscriptions ─────────────────────────────────────────────────

    def subscribe_bars(self, bar_type: BarType) -> None:
        if self._data_engine:
            self._data_engine.subscribe_bars(bar_type)
        if self.msgbus:
            self.msgbus.subscribe(f"data.bars.{bar_type}", self._handle_bar)

    def subscribe_quote_ticks(self, instrument_id: InstrumentId) -> None:
        if self._data_engine:
            self._data_engine.subscribe_quote_ticks(instrument_id)
        if self.msgbus:
            self.msgbus.subscribe(f"data.quotes.{instrument_id}", self._handle_quote_tick)

    def subscribe_trade_ticks(self, instrument_id: InstrumentId) -> None:
        if self._data_engine:
            self._data_engine.subscribe_trade_ticks(instrument_id)
        if self.msgbus:
            self.msgbus.subscribe(f"data.trades.{instrument_id}", self._handle_trade_tick)

    # ── Indicator helpers ──────────────────────────────────────────────────

    def register_indicator_for_bars(self, bar_type: BarType, indicator) -> None:
        """Register an indicator to be auto-updated on each bar."""
        self._indicators.setdefault(bar_type, []).append(indicator)

    def indicators_initialized(self, bar_type: BarType) -> bool:
        """True if all indicators for ``bar_type`` have warmed up."""
        return all(
            ind.initialized for ind in self._indicators.get(bar_type, [])
        )

    # ── Convenience order constructors ─────────────────────────────────────

    def buy(
        self,
        instrument_id: InstrumentId,
        quantity: Quantity,
        ts_init: int = 0,
    ) -> None:
        """Shorthand: submit a market buy."""
        order = self.order_factory.market(instrument_id, OrderSide.BUY, quantity, ts_init=ts_init)
        self.submit_order(order)

    def sell(
        self,
        instrument_id: InstrumentId,
        quantity: Quantity,
        ts_init: int = 0,
    ) -> None:
        """Shorthand: submit a market sell."""
        order = self.order_factory.market(instrument_id, OrderSide.SELL, quantity, ts_init=ts_init)
        self.submit_order(order)

    def buy_limit(
        self,
        instrument_id: InstrumentId,
        quantity: Quantity,
        price: Price,
        ts_init: int = 0,
    ) -> None:
        order = self.order_factory.limit(instrument_id, OrderSide.BUY, quantity, price, ts_init=ts_init)
        self.submit_order(order)

    def sell_limit(
        self,
        instrument_id: InstrumentId,
        quantity: Quantity,
        price: Price,
        ts_init: int = 0,
    ) -> None:
        order = self.order_factory.limit(instrument_id, OrderSide.SELL, quantity, price, ts_init=ts_init)
        self.submit_order(order)

    # ── Internal handlers ──────────────────────────────────────────────────

    def _handle_bar(self, bar: Bar) -> None:
        # Update registered indicators
        for indicator in self._indicators.get(bar.bar_type, []):
            indicator.handle_bar(bar)
        self.on_bar(bar)

    def _handle_quote_tick(self, tick: QuoteTick) -> None:
        self.on_quote_tick(tick)

    def _handle_trade_tick(self, tick: TradeTick) -> None:
        self.on_trade_tick(tick)

    def _handle_order_event(self, event) -> None:
        if isinstance(event, OrderSubmitted):
            self.on_order_submitted(event)
        elif isinstance(event, OrderAccepted):
            self.on_order_accepted(event)
        elif isinstance(event, OrderRejected):
            self.on_order_rejected(event)
        elif isinstance(event, OrderDenied):
            self.on_order_denied(event)
        elif isinstance(event, OrderCanceled):
            self.on_order_canceled(event)
        elif isinstance(event, OrderExpired):
            self.on_order_expired(event)
        elif isinstance(event, OrderFilled):
            self.on_order_filled(event)
        elif isinstance(event, OrderTriggered):
            self.on_order_triggered(event)

    def _handle_position_event(self, event) -> None:
        if isinstance(event, PositionOpened):
            self.on_position_opened(event)
        elif isinstance(event, PositionChanged):
            self.on_position_changed(event)
        elif isinstance(event, PositionClosed):
            self.on_position_closed(event)

    def __repr__(self) -> str:
        return f"Strategy(id={self.id})"
