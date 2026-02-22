"""
ExecutionEngine — routes order commands to venues and position events to strategies.

Responsibilities:
  - Submit, cancel, modify orders via registered venues
  - Apply all order/position events to the Cache
  - Manage position lifecycle (open, change, close) in NETTING and HEDGING OMS
  - Publish events to the MessageBus for strategy notification
  - Run orders through the RiskEngine before submission
"""
from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Optional, TYPE_CHECKING

from nautilus_full.core.enums import OmsType, OrderSide, PositionSide
from nautilus_full.core.events import (
    OrderAccepted,
    OrderCanceled,
    OrderDenied,
    OrderExpired,
    OrderFilled,
    OrderInitialized,
    OrderRejected,
    OrderSubmitted,
    OrderTriggered,
    OrderUpdated,
    PositionChanged,
    PositionClosed,
    PositionOpened,
)
from nautilus_full.core.identifiers import PositionId, Venue
from nautilus_full.model.orders.base import Order
from nautilus_full.model.position import Position

if TYPE_CHECKING:
    from nautilus_full.core.identifiers import InstrumentId
    from nautilus_full.core.msgbus import MessageBus
    from nautilus_full.engine.risk_engine import RiskEngine
    from nautilus_full.state.cache import Cache
    from nautilus_full.venues.simulated_exchange import SimulatedExchange


class ExecutionEngine:
    """
    Central execution engine that mediates between strategies, risk, venues,
    and the state cache.
    """

    def __init__(
        self,
        cache: "Cache",
        msgbus: "MessageBus",
        risk_engine: "RiskEngine",
    ) -> None:
        self._cache = cache
        self._msgbus = msgbus
        self._risk = risk_engine

        # venue -> (exchange, OmsType)
        self._venues: dict[Venue, tuple["SimulatedExchange", OmsType]] = {}

        # Position ID counter
        self._pos_count = 0

    # ── Venue registration ─────────────────────────────────────────────────

    def register_venue(
        self,
        venue: Venue,
        exchange: "SimulatedExchange",
        oms_type: OmsType,
    ) -> None:
        self._venues[venue] = (exchange, oms_type)

    # ── Order commands ─────────────────────────────────────────────────────

    def submit_order(self, order: Order) -> None:
        # Risk check
        ok, reason = self._risk.check_order(order)
        if not ok:
            denied = OrderDenied(
                trader_id=order.trader_id,
                strategy_id=order.strategy_id,
                instrument_id=order.instrument_id,
                client_order_id=order.client_order_id,
                reason=reason,
                ts_event=order.ts_init,
                ts_init=order.ts_init,
            )
            self.process_event(denied)
            return

        # Add to cache
        self._cache.add_order(order)

        # Fire OrderSubmitted
        submitted = OrderSubmitted(
            trader_id=order.trader_id,
            strategy_id=order.strategy_id,
            instrument_id=order.instrument_id,
            client_order_id=order.client_order_id,
            account_id=self._get_account_id(order.instrument_id.venue),
            ts_event=order.ts_init,
            ts_init=order.ts_init,
        )
        self.process_event(submitted)

        # Route to venue
        venue = order.instrument_id.venue
        venue_tuple = self._venues.get(venue)
        if venue_tuple:
            exchange, _ = venue_tuple
            exchange.process_order(order)

    def cancel_order(self, order: Order, ts: int = 0) -> None:
        venue = order.instrument_id.venue
        venue_tuple = self._venues.get(venue)
        if venue_tuple:
            exchange, _ = venue_tuple
            exchange.cancel_order(order, ts)

    def modify_order(
        self,
        order: Order,
        quantity=None,
        price=None,
        trigger_price=None,
        ts: int = 0,
    ) -> None:
        venue = order.instrument_id.venue
        venue_tuple = self._venues.get(venue)
        if venue_tuple:
            exchange, _ = venue_tuple
            exchange.modify_order(order, quantity, price, trigger_price, ts)

    # ── Event processing ───────────────────────────────────────────────────

    def process_event(self, event) -> None:
        """
        Process any order/position event:
        1. Apply to the Order FSM in the cache.
        2. Handle position lifecycle for OrderFilled events.
        3. Publish to MessageBus for strategy notification.
        """
        if isinstance(event, (OrderInitialized,)):
            return  # handled at submission time

        # Apply to order FSM
        order = None
        if hasattr(event, "client_order_id"):
            order = self._cache.order(event.client_order_id)
            if order and not isinstance(event, (OrderFilled,)):
                try:
                    order.apply(event)
                except RuntimeError:
                    pass  # Log and continue; don't crash backtest

        # Position lifecycle on fill
        if isinstance(event, OrderFilled) and order is not None:
            try:
                order.apply(event)
            except RuntimeError:
                pass
            self._handle_fill(order, event)

        # Publish to MessageBus
        self._publish_event(event)

    def _handle_fill(self, order: Order, event: OrderFilled) -> None:
        """Update or create positions based on a fill."""
        venue = order.instrument_id.venue
        venue_tuple = self._venues.get(venue)
        oms_type = venue_tuple[1] if venue_tuple else OmsType.NETTING

        instrument = self._cache.instrument(order.instrument_id)
        if instrument is None:
            return

        currency = instrument.quote_currency
        multiplier = instrument.multiplier.value

        if oms_type == OmsType.NETTING:
            self._handle_fill_netting(order, event, currency, multiplier)
        else:
            self._handle_fill_hedging(order, event, currency, multiplier)

    def _handle_fill_netting(self, order, event, currency, multiplier) -> None:
        """NETTING: single position per instrument per strategy."""
        open_positions = self._cache.positions_open(
            instrument_id=order.instrument_id,
            strategy_id=order.strategy_id,
        )

        if not open_positions:
            # Open new position
            pos = self._open_position(order, event, currency, multiplier)
        else:
            pos = open_positions[0]
            pos.apply(event)
            if pos.is_closed:
                self._publish_position_closed(pos, order, event)
            else:
                self._publish_position_changed(pos, event)

    def _handle_fill_hedging(self, order, event, currency, multiplier) -> None:
        """HEDGING: multiple positions per instrument; find the right one."""
        # Find the position this order belongs to (by position_id if set)
        if order.position_id:
            pos = self._cache.position(order.position_id)
            if pos:
                pos.apply(event)
                if pos.is_closed:
                    self._publish_position_closed(pos, order, event)
                else:
                    self._publish_position_changed(pos, event)
                return

        # No existing position — open a new one
        self._open_position(order, event, currency, multiplier)

    def _open_position(self, order, event, currency, multiplier) -> Position:
        self._pos_count += 1
        pos_id = PositionId(
            f"P-{order.strategy_id}-{order.instrument_id.symbol}-{self._pos_count}"
        )
        pos = Position(
            instrument_id=order.instrument_id,
            position_id=pos_id,
            account_id=event.account_id,
            trader_id=order.trader_id,
            strategy_id=order.strategy_id,
            opening_event=event,
            currency=currency,
            multiplier=multiplier,
        )
        self._cache.add_position(pos)
        order.position_id = pos_id

        # Publish PositionOpened
        pos_event = PositionOpened(
            trader_id=order.trader_id,
            strategy_id=order.strategy_id,
            instrument_id=order.instrument_id,
            position_id=pos_id,
            account_id=event.account_id,
            opening_order_id=order.client_order_id,
            entry_side=order.side,
            entry_price=event.last_px,
            quantity=event.last_qty,
            currency=currency,
            ts_event=event.ts_event,
            ts_init=event.ts_init,
        )
        self._msgbus.publish(f"events.position.{order.strategy_id}", pos_event)
        return pos

    def _publish_position_changed(self, pos, event) -> None:
        pos_event = PositionChanged(
            trader_id=pos.trader_id,
            strategy_id=pos.strategy_id,
            instrument_id=pos.instrument_id,
            position_id=pos.id,
            account_id=pos.account_id,
            quantity=pos.quantity,
            realized_pnl=pos.realized_pnl,
            unrealized_pnl=pos.unrealized_pnl,
            ts_event=event.ts_event,
            ts_init=event.ts_init,
        )
        self._msgbus.publish(f"events.position.{pos.strategy_id}", pos_event)

    def _publish_position_closed(self, pos, order, event) -> None:
        pos_event = PositionClosed(
            trader_id=pos.trader_id,
            strategy_id=pos.strategy_id,
            instrument_id=pos.instrument_id,
            position_id=pos.id,
            account_id=pos.account_id,
            closing_order_id=order.client_order_id,
            realized_pnl=pos.realized_pnl,
            currency=pos.currency,
            ts_event=event.ts_event,
            ts_init=event.ts_init,
        )
        self._msgbus.publish(f"events.position.{pos.strategy_id}", pos_event)

    def _publish_event(self, event) -> None:
        """Publish order event to the strategy's subscription topic."""
        if hasattr(event, "strategy_id"):
            self._msgbus.publish(f"events.order.{event.strategy_id}", event)

    def _get_account_id(self, venue: Venue):
        from nautilus_full.core.identifiers import AccountId
        venue_tuple = self._venues.get(venue)
        if venue_tuple:
            return venue_tuple[0].account.id
        return AccountId(f"{venue}-001")
