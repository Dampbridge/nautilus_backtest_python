"""
All event types used throughout the framework.

Events are immutable data containers (dataclasses with frozen=True).
All events carry:
  ts_event  — nanosecond timestamp of the event occurrence
  ts_init   — nanosecond timestamp when the event object was created
  event_id  — unique UUID string (auto-generated, placed LAST in each subclass)
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional

from nautilus_full.core.enums import (
    AggressorSide,
    ContingencyType,
    LiquiditySide,
    MarketStatus,
    OrderSide,
    OrderStatus,
    OrderType,
    TimeInForce,
)
from nautilus_full.core.identifiers import (
    AccountId,
    ClientOrderId,
    InstrumentId,
    OrderListId,
    PositionId,
    StrategyId,
    TradeId,
    TraderId,
    VenueOrderId,
)
from nautilus_full.core.objects import Currency, Money, Price, Quantity


def _new_id() -> str:
    return str(uuid.uuid4())


# ── Base event ────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Event:
    """
    Base event. Subclasses must put ALL required (non-default) fields first,
    then ts_event, ts_init, and finally event_id (which has a default factory).
    """
    ts_event: int  # nanoseconds
    ts_init: int   # nanoseconds


# ── Order events ──────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class OrderInitialized(Event):
    trader_id: TraderId
    strategy_id: StrategyId
    instrument_id: InstrumentId
    client_order_id: ClientOrderId
    order_side: OrderSide
    order_type: OrderType
    quantity: Quantity
    time_in_force: TimeInForce
    post_only: bool = False
    reduce_only: bool = False
    quote_quantity: bool = False
    price: Optional[Price] = None           # Limit / StopLimit / LIT price
    trigger_price: Optional[Price] = None   # Stop / MIT trigger price
    trigger_type: Optional[str] = None
    limit_offset: Optional[Decimal] = None  # TrailingStopLimit limit offset
    trailing_offset: Optional[Decimal] = None
    trailing_offset_type: Optional[str] = None
    expire_time_ns: Optional[int] = None    # GTD expiry
    display_qty: Optional[Quantity] = None  # Iceberg visible qty
    contingency_type: ContingencyType = ContingencyType.NO_CONTINGENCY
    order_list_id: Optional[OrderListId] = None
    linked_order_ids: Optional[list] = None
    parent_order_id: Optional[ClientOrderId] = None
    tags: Optional[list] = None
    event_id: str = field(default_factory=_new_id)


@dataclass(frozen=True)
class OrderDenied(Event):
    trader_id: TraderId
    strategy_id: StrategyId
    instrument_id: InstrumentId
    client_order_id: ClientOrderId
    reason: str
    event_id: str = field(default_factory=_new_id)


@dataclass(frozen=True)
class OrderSubmitted(Event):
    trader_id: TraderId
    strategy_id: StrategyId
    instrument_id: InstrumentId
    client_order_id: ClientOrderId
    account_id: AccountId
    event_id: str = field(default_factory=_new_id)


@dataclass(frozen=True)
class OrderAccepted(Event):
    trader_id: TraderId
    strategy_id: StrategyId
    instrument_id: InstrumentId
    client_order_id: ClientOrderId
    venue_order_id: VenueOrderId
    account_id: AccountId
    event_id: str = field(default_factory=_new_id)


@dataclass(frozen=True)
class OrderRejected(Event):
    trader_id: TraderId
    strategy_id: StrategyId
    instrument_id: InstrumentId
    client_order_id: ClientOrderId
    account_id: AccountId
    reason: str
    event_id: str = field(default_factory=_new_id)


@dataclass(frozen=True)
class OrderCanceled(Event):
    trader_id: TraderId
    strategy_id: StrategyId
    instrument_id: InstrumentId
    client_order_id: ClientOrderId
    venue_order_id: Optional[VenueOrderId]
    account_id: AccountId
    event_id: str = field(default_factory=_new_id)


@dataclass(frozen=True)
class OrderExpired(Event):
    trader_id: TraderId
    strategy_id: StrategyId
    instrument_id: InstrumentId
    client_order_id: ClientOrderId
    venue_order_id: Optional[VenueOrderId]
    account_id: AccountId
    event_id: str = field(default_factory=_new_id)


@dataclass(frozen=True)
class OrderTriggered(Event):
    """Fired when a stop or MIT order's trigger price is hit."""
    trader_id: TraderId
    strategy_id: StrategyId
    instrument_id: InstrumentId
    client_order_id: ClientOrderId
    venue_order_id: Optional[VenueOrderId]
    account_id: AccountId
    event_id: str = field(default_factory=_new_id)


@dataclass(frozen=True)
class OrderPendingUpdate(Event):
    trader_id: TraderId
    strategy_id: StrategyId
    instrument_id: InstrumentId
    client_order_id: ClientOrderId
    venue_order_id: Optional[VenueOrderId]
    account_id: AccountId
    event_id: str = field(default_factory=_new_id)


@dataclass(frozen=True)
class OrderPendingCancel(Event):
    trader_id: TraderId
    strategy_id: StrategyId
    instrument_id: InstrumentId
    client_order_id: ClientOrderId
    venue_order_id: Optional[VenueOrderId]
    account_id: AccountId
    event_id: str = field(default_factory=_new_id)


@dataclass(frozen=True)
class OrderUpdated(Event):
    trader_id: TraderId
    strategy_id: StrategyId
    instrument_id: InstrumentId
    client_order_id: ClientOrderId
    venue_order_id: Optional[VenueOrderId]
    account_id: AccountId
    quantity: Optional[Quantity] = None
    price: Optional[Price] = None
    trigger_price: Optional[Price] = None
    event_id: str = field(default_factory=_new_id)


@dataclass(frozen=True)
class OrderFilled(Event):
    trader_id: TraderId
    strategy_id: StrategyId
    instrument_id: InstrumentId
    client_order_id: ClientOrderId
    venue_order_id: VenueOrderId
    account_id: AccountId
    trade_id: TradeId
    order_side: OrderSide
    order_type: OrderType
    last_qty: Quantity
    last_px: Price
    currency: Currency
    commission: Money
    liquidity_side: LiquiditySide
    position_id: Optional[PositionId] = None
    event_id: str = field(default_factory=_new_id)


# ── Position events ───────────────────────────────────────────────────────────

@dataclass(frozen=True)
class PositionOpened(Event):
    trader_id: TraderId
    strategy_id: StrategyId
    instrument_id: InstrumentId
    position_id: PositionId
    account_id: AccountId
    opening_order_id: ClientOrderId
    entry_side: OrderSide
    entry_price: Price
    quantity: Quantity
    currency: Currency
    event_id: str = field(default_factory=_new_id)


@dataclass(frozen=True)
class PositionChanged(Event):
    trader_id: TraderId
    strategy_id: StrategyId
    instrument_id: InstrumentId
    position_id: PositionId
    account_id: AccountId
    quantity: Quantity
    realized_pnl: Decimal
    unrealized_pnl: Decimal
    event_id: str = field(default_factory=_new_id)


@dataclass(frozen=True)
class PositionClosed(Event):
    trader_id: TraderId
    strategy_id: StrategyId
    instrument_id: InstrumentId
    position_id: PositionId
    account_id: AccountId
    closing_order_id: ClientOrderId
    realized_pnl: Decimal
    currency: Currency
    event_id: str = field(default_factory=_new_id)


# ── Account events ────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class AccountState(Event):
    account_id: AccountId
    account_type: str
    base_currency: Optional[Currency]
    balances: list  # list of AccountBalance objects
    margins: list   # list of MarginBalance objects
    is_reported: bool
    info: dict = field(default_factory=dict)
    event_id: str = field(default_factory=_new_id)


# ── Market data events ────────────────────────────────────────────────────────

@dataclass(frozen=True)
class InstrumentStatusUpdate(Event):
    instrument_id: InstrumentId
    status: MarketStatus
    event_id: str = field(default_factory=_new_id)


# ── System events ─────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class ComponentStateChanged(Event):
    component_id: str
    state: str
    config: dict = field(default_factory=dict)
    event_id: str = field(default_factory=_new_id)
