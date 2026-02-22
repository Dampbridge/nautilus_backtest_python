"""
OrderFactory — creates orders and manages client order IDs.

Each strategy gets its own factory seeded with its trader_id / strategy_id.
"""
from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Optional

from nautilus_full.core.enums import (
    ContingencyType,
    OrderSide,
    OrderType,
    TimeInForce,
    TrailingOffsetType,
)
from nautilus_full.core.events import OrderInitialized
from nautilus_full.core.identifiers import (
    ClientOrderId,
    InstrumentId,
    OrderListId,
    StrategyId,
    TraderId,
)
from nautilus_full.core.objects import Price, Quantity
from nautilus_full.model.orders.limit import LimitOrder
from nautilus_full.model.orders.limit_if_touched import LimitIfTouchedOrder
from nautilus_full.model.orders.market import MarketOrder
from nautilus_full.model.orders.market_if_touched import MarketIfTouchedOrder
from nautilus_full.model.orders.stop_limit import StopLimitOrder
from nautilus_full.model.orders.stop_market import StopMarketOrder
from nautilus_full.model.orders.trailing_stop import TrailingStopLimitOrder, TrailingStopMarketOrder


class OrderFactory:
    """
    Constructs typed order objects and assigns sequential client order IDs.

    Usage
    -----
    >>> factory = OrderFactory(trader_id=TraderId("TRADER-001"),
    ...                        strategy_id=StrategyId("MyStrat-001"))
    >>> order = factory.market(instrument_id, OrderSide.BUY, Quantity("1", 0))
    """

    def __init__(
        self,
        trader_id: TraderId,
        strategy_id: StrategyId,
        initial_count: int = 0,
    ) -> None:
        self._trader_id = trader_id
        self._strategy_id = strategy_id
        self._count = initial_count

    def _next_id(self) -> ClientOrderId:
        self._count += 1
        return ClientOrderId(f"O-{self._trader_id}-{self._strategy_id}-{self._count}")

    def _base_init(
        self,
        instrument_id: InstrumentId,
        order_side: OrderSide,
        order_type: OrderType,
        quantity: Quantity,
        time_in_force: TimeInForce,
        ts_init: int,
        price: Optional[Price] = None,
        trigger_price: Optional[Price] = None,
        trigger_type: Optional[str] = None,
        trailing_offset: Optional[Decimal] = None,
        trailing_offset_type: Optional[TrailingOffsetType] = None,
        limit_offset: Optional[Decimal] = None,
        expire_time_ns: Optional[int] = None,
        post_only: bool = False,
        reduce_only: bool = False,
        display_qty: Optional[Quantity] = None,
        contingency_type: ContingencyType = ContingencyType.NO_CONTINGENCY,
        order_list_id: Optional[OrderListId] = None,
        linked_order_ids: Optional[list[ClientOrderId]] = None,
        parent_order_id: Optional[ClientOrderId] = None,
        tags: Optional[list[str]] = None,
        client_order_id: Optional[ClientOrderId] = None,
    ) -> OrderInitialized:
        cid = client_order_id or self._next_id()
        return OrderInitialized(
            trader_id=self._trader_id,
            strategy_id=self._strategy_id,
            instrument_id=instrument_id,
            client_order_id=cid,
            order_side=order_side,
            order_type=order_type,
            quantity=quantity,
            time_in_force=time_in_force,
            post_only=post_only,
            reduce_only=reduce_only,
            price=price,
            trigger_price=trigger_price,
            trigger_type=trigger_type,
            trailing_offset=trailing_offset,
            trailing_offset_type=(
                trailing_offset_type.name if trailing_offset_type else None
            ),
            limit_offset=limit_offset,
            expire_time_ns=expire_time_ns,
            display_qty=display_qty,
            contingency_type=contingency_type,
            order_list_id=order_list_id,
            linked_order_ids=linked_order_ids,
            parent_order_id=parent_order_id,
            tags=tags,
            ts_event=ts_init,
            ts_init=ts_init,
        )

    # ── Market order ───────────────────────────────────────────────────────

    def market(
        self,
        instrument_id: InstrumentId,
        order_side: OrderSide,
        quantity: Quantity,
        time_in_force: TimeInForce = TimeInForce.GTC,
        reduce_only: bool = False,
        tags: Optional[list[str]] = None,
        ts_init: int = 0,
        client_order_id: Optional[ClientOrderId] = None,
    ) -> MarketOrder:
        init = self._base_init(
            instrument_id=instrument_id,
            order_side=order_side,
            order_type=OrderType.MARKET,
            quantity=quantity,
            time_in_force=time_in_force,
            ts_init=ts_init,
            reduce_only=reduce_only,
            tags=tags,
            client_order_id=client_order_id,
        )
        return MarketOrder(init)

    # ── Limit order ────────────────────────────────────────────────────────

    def limit(
        self,
        instrument_id: InstrumentId,
        order_side: OrderSide,
        quantity: Quantity,
        price: Price,
        time_in_force: TimeInForce = TimeInForce.GTC,
        post_only: bool = False,
        reduce_only: bool = False,
        display_qty: Optional[Quantity] = None,
        expire_time_ns: Optional[int] = None,
        tags: Optional[list[str]] = None,
        ts_init: int = 0,
        client_order_id: Optional[ClientOrderId] = None,
    ) -> LimitOrder:
        init = self._base_init(
            instrument_id=instrument_id,
            order_side=order_side,
            order_type=OrderType.LIMIT,
            quantity=quantity,
            time_in_force=time_in_force,
            ts_init=ts_init,
            price=price,
            post_only=post_only,
            reduce_only=reduce_only,
            display_qty=display_qty,
            expire_time_ns=expire_time_ns,
            tags=tags,
            client_order_id=client_order_id,
        )
        return LimitOrder(init)

    # ── Stop market order ──────────────────────────────────────────────────

    def stop_market(
        self,
        instrument_id: InstrumentId,
        order_side: OrderSide,
        quantity: Quantity,
        trigger_price: Price,
        time_in_force: TimeInForce = TimeInForce.GTC,
        reduce_only: bool = False,
        tags: Optional[list[str]] = None,
        ts_init: int = 0,
        client_order_id: Optional[ClientOrderId] = None,
    ) -> StopMarketOrder:
        init = self._base_init(
            instrument_id=instrument_id,
            order_side=order_side,
            order_type=OrderType.STOP_MARKET,
            quantity=quantity,
            time_in_force=time_in_force,
            ts_init=ts_init,
            trigger_price=trigger_price,
            reduce_only=reduce_only,
            tags=tags,
            client_order_id=client_order_id,
        )
        return StopMarketOrder(init)

    # ── Stop limit order ───────────────────────────────────────────────────

    def stop_limit(
        self,
        instrument_id: InstrumentId,
        order_side: OrderSide,
        quantity: Quantity,
        price: Price,
        trigger_price: Price,
        time_in_force: TimeInForce = TimeInForce.GTC,
        post_only: bool = False,
        reduce_only: bool = False,
        tags: Optional[list[str]] = None,
        ts_init: int = 0,
        client_order_id: Optional[ClientOrderId] = None,
    ) -> StopLimitOrder:
        init = self._base_init(
            instrument_id=instrument_id,
            order_side=order_side,
            order_type=OrderType.STOP_LIMIT,
            quantity=quantity,
            time_in_force=time_in_force,
            ts_init=ts_init,
            price=price,
            trigger_price=trigger_price,
            post_only=post_only,
            reduce_only=reduce_only,
            tags=tags,
            client_order_id=client_order_id,
        )
        return StopLimitOrder(init)

    # ── Trailing stop market order ─────────────────────────────────────────

    def trailing_stop_market(
        self,
        instrument_id: InstrumentId,
        order_side: OrderSide,
        quantity: Quantity,
        trailing_offset: Decimal,
        trailing_offset_type: TrailingOffsetType = TrailingOffsetType.PRICE,
        trigger_price: Optional[Price] = None,
        time_in_force: TimeInForce = TimeInForce.GTC,
        reduce_only: bool = False,
        tags: Optional[list[str]] = None,
        ts_init: int = 0,
    ) -> TrailingStopMarketOrder:
        init = self._base_init(
            instrument_id=instrument_id,
            order_side=order_side,
            order_type=OrderType.TRAILING_STOP_MARKET,
            quantity=quantity,
            time_in_force=time_in_force,
            ts_init=ts_init,
            trigger_price=trigger_price,
            trailing_offset=trailing_offset,
            trailing_offset_type=trailing_offset_type,
            reduce_only=reduce_only,
            tags=tags,
        )
        return TrailingStopMarketOrder(init)

    # ── Trailing stop limit order ──────────────────────────────────────────

    def trailing_stop_limit(
        self,
        instrument_id: InstrumentId,
        order_side: OrderSide,
        quantity: Quantity,
        trailing_offset: Decimal,
        limit_offset: Decimal,
        trailing_offset_type: TrailingOffsetType = TrailingOffsetType.PRICE,
        trigger_price: Optional[Price] = None,
        price: Optional[Price] = None,
        time_in_force: TimeInForce = TimeInForce.GTC,
        reduce_only: bool = False,
        tags: Optional[list[str]] = None,
        ts_init: int = 0,
    ) -> TrailingStopLimitOrder:
        init = self._base_init(
            instrument_id=instrument_id,
            order_side=order_side,
            order_type=OrderType.TRAILING_STOP_LIMIT,
            quantity=quantity,
            time_in_force=time_in_force,
            ts_init=ts_init,
            price=price,
            trigger_price=trigger_price,
            trailing_offset=trailing_offset,
            trailing_offset_type=trailing_offset_type,
            limit_offset=limit_offset,
            reduce_only=reduce_only,
            tags=tags,
        )
        return TrailingStopLimitOrder(init)

    # ── Market-if-touched order ────────────────────────────────────────────

    def market_if_touched(
        self,
        instrument_id: InstrumentId,
        order_side: OrderSide,
        quantity: Quantity,
        trigger_price: Price,
        time_in_force: TimeInForce = TimeInForce.GTC,
        tags: Optional[list[str]] = None,
        ts_init: int = 0,
    ) -> MarketIfTouchedOrder:
        init = self._base_init(
            instrument_id=instrument_id,
            order_side=order_side,
            order_type=OrderType.MARKET_IF_TOUCHED,
            quantity=quantity,
            time_in_force=time_in_force,
            ts_init=ts_init,
            trigger_price=trigger_price,
            tags=tags,
        )
        return MarketIfTouchedOrder(init)

    # ── Limit-if-touched order ─────────────────────────────────────────────

    def limit_if_touched(
        self,
        instrument_id: InstrumentId,
        order_side: OrderSide,
        quantity: Quantity,
        price: Price,
        trigger_price: Price,
        time_in_force: TimeInForce = TimeInForce.GTC,
        tags: Optional[list[str]] = None,
        ts_init: int = 0,
    ) -> LimitIfTouchedOrder:
        init = self._base_init(
            instrument_id=instrument_id,
            order_side=order_side,
            order_type=OrderType.LIMIT_IF_TOUCHED,
            quantity=quantity,
            time_in_force=time_in_force,
            ts_init=ts_init,
            price=price,
            trigger_price=trigger_price,
            tags=tags,
        )
        return LimitIfTouchedOrder(init)

    # ── OCO order list ─────────────────────────────────────────────────────

    def oco(
        self,
        first: "Order",
        second: "Order",
    ) -> tuple["Order", "Order"]:
        """
        Link two orders as OCO (One Cancels Other).
        Mutates both orders' contingency metadata in place.
        Returns the linked pair.
        """
        list_id = OrderListId(f"OL-{uuid.uuid4().hex[:8]}")
        # Patch contingency info (we update the init event too for record)
        first.contingency_type = ContingencyType.OCO
        first.order_list_id = list_id
        first.linked_order_ids = [second.client_order_id]

        second.contingency_type = ContingencyType.OCO
        second.order_list_id = list_id
        second.linked_order_ids = [first.client_order_id]

        return first, second

    def reset(self) -> None:
        self._count = 0
