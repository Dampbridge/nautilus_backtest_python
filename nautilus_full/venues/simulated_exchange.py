"""
SimulatedExchange — the core venue simulation for backtesting.

Responsibilities:
  - Maintains one OrderMatchingEngine per instrument
  - Routes incoming orders to the correct matching engine
  - Handles account balance updates after fills
  - Supports bar, quote tick, trade tick, and order book data
  - Provides cancel_order and modify_order
"""
from __future__ import annotations

from decimal import Decimal
from typing import Optional

from nautilus_full.core.enums import AccountType, LiquiditySide, OmsType, OrderSide, OrderType
from nautilus_full.core.events import (
    OrderAccepted,
    OrderCanceled,
    OrderExpired,
    OrderFilled,
    OrderRejected,
    OrderTriggered,
)
from nautilus_full.core.identifiers import AccountId, InstrumentId, Venue, VenueOrderId
from nautilus_full.core.objects import Currency, Money, Price, Quantity
from nautilus_full.engine.matching_engine import OrderMatchingEngine
from nautilus_full.model.data import Bar, OrderBookDelta, OrderBookDeltas, QuoteTick, TradeTick
from nautilus_full.model.instruments.base import Instrument
from nautilus_full.model.orders.base import Order
from nautilus_full.venues.account import CashAccount, MarginAccount
from nautilus_full.venues.models import DefaultFillModel, FeeModel, FillModel, MakerTakerFeeModel


class SimulatedExchange:
    """
    Simulated exchange for backtesting.

    Parameters
    ----------
    venue : Venue
        Exchange identifier.
    oms_type : OmsType
        NETTING (single position) or HEDGING (multiple positions).
    account_type : AccountType
        CASH or MARGIN.
    base_currency : Currency
        Settlement currency for the account.
    starting_balances : list[Money]
        Initial account balances.
    fill_model : FillModel, optional
        Custom fill model; defaults to DefaultFillModel.
    fee_model : FeeModel, optional
        Custom fee model; defaults to MakerTakerFeeModel.
    default_leverage : Decimal
        Default leverage for margin accounts.
    book_spread_pct : Decimal
        Synthetic spread when constructing L2 from bars.
    """

    def __init__(
        self,
        venue: Venue,
        oms_type: OmsType,
        account_type: AccountType,
        base_currency: Currency,
        starting_balances: list[Money],
        fill_model: Optional[FillModel] = None,
        fee_model: Optional[FeeModel] = None,
        default_leverage: Decimal = Decimal("1"),
        book_spread_pct: Decimal = Decimal("0.0001"),
        exec_engine=None,  # injected by BacktestEngine
    ) -> None:
        self.venue = venue
        self.oms_type = oms_type
        self.account_type = account_type
        self.base_currency = base_currency
        self.fill_model = fill_model or DefaultFillModel()
        self.fee_model = fee_model or MakerTakerFeeModel()
        self.book_spread_pct = book_spread_pct
        self._exec_engine = exec_engine

        # Account
        account_id = AccountId(f"{venue}-001")
        if account_type == AccountType.MARGIN:
            self.account = MarginAccount(account_id, base_currency, default_leverage)
        else:
            self.account = CashAccount(account_id, base_currency)

        for money in starting_balances:
            self.account.update_balance(money.currency, money.amount, Decimal("0"))

        # Per-instrument matching engines
        self._instruments: dict[InstrumentId, Instrument] = {}
        self._matching_engines: dict[InstrumentId, OrderMatchingEngine] = {}
        self._venue_order_counter = 0

    def set_exec_engine(self, exec_engine) -> None:
        self._exec_engine = exec_engine

    # ── Instrument management ──────────────────────────────────────────────

    def add_instrument(self, instrument: Instrument) -> None:
        self._instruments[instrument.id] = instrument
        self._matching_engines[instrument.id] = OrderMatchingEngine(
            instrument=instrument,
            fill_model=self.fill_model,
            fee_model=self.fee_model,
            account_id=self.account.id,
            on_fill=self._on_fill,
            on_cancel=self._on_cancel,
            on_expire=self._on_expire,
            on_trigger=self._on_trigger,
            book_spread_pct=self.book_spread_pct,
        )

    # ── Order routing ──────────────────────────────────────────────────────

    def process_order(self, order: Order) -> None:
        """Accept an incoming order and route it to the matching engine."""
        self._venue_order_counter += 1
        venue_order_id = VenueOrderId(
            f"V-{self.venue}-{self._venue_order_counter}"
        )

        # Pre-trade check: balance
        ok, reason = self._check_balance(order)
        if not ok:
            event = OrderRejected(
                trader_id=order.trader_id,
                strategy_id=order.strategy_id,
                instrument_id=order.instrument_id,
                client_order_id=order.client_order_id,
                account_id=self.account.id,
                reason=reason,
                ts_event=order.ts_init,
                ts_init=order.ts_init,
            )
            if self._exec_engine:
                self._exec_engine.process_event(event)
            return

        # Accept
        accepted = OrderAccepted(
            trader_id=order.trader_id,
            strategy_id=order.strategy_id,
            instrument_id=order.instrument_id,
            client_order_id=order.client_order_id,
            venue_order_id=venue_order_id,
            account_id=self.account.id,
            ts_event=order.ts_init,
            ts_init=order.ts_init,
        )
        if self._exec_engine:
            self._exec_engine.process_event(accepted)

        # Route to matching engine
        engine = self._matching_engines.get(order.instrument_id)
        if engine:
            engine.process_order(order, order.ts_init)

    def cancel_order(self, order: Order, ts: int = 0) -> None:
        engine = self._matching_engines.get(order.instrument_id)
        if engine:
            engine.cancel_order(order, ts)

    def modify_order(
        self,
        order: Order,
        quantity=None,
        price=None,
        trigger_price=None,
        ts: int = 0,
    ) -> None:
        engine = self._matching_engines.get(order.instrument_id)
        if engine:
            engine.modify_order(order, quantity, price, trigger_price, ts)

    # ── Data routing ───────────────────────────────────────────────────────

    def process_bar(self, bar: Bar) -> None:
        engine = self._matching_engines.get(bar.bar_type.instrument_id)
        if engine:
            engine.process_bar(bar)

    def process_quote_tick(self, tick: QuoteTick) -> None:
        engine = self._matching_engines.get(tick.instrument_id)
        if engine:
            engine.process_quote_tick(tick)

    def process_trade_tick(self, tick: TradeTick) -> None:
        engine = self._matching_engines.get(tick.instrument_id)
        if engine:
            engine.process_trade_tick(tick)

    def process_order_book_delta(self, delta: OrderBookDelta) -> None:
        engine = self._matching_engines.get(delta.instrument_id)
        if engine:
            engine.process_book_delta(delta)

    def process_order_book_deltas(self, deltas: OrderBookDeltas) -> None:
        engine = self._matching_engines.get(deltas.instrument_id)
        if engine:
            engine.process_book_deltas(deltas)

    # ── Event callbacks from matching engines ──────────────────────────────

    def _on_fill(self, event: OrderFilled) -> None:
        """Update account balance and forward to execution engine."""
        self._update_account_on_fill(event)
        if self._exec_engine:
            self._exec_engine.process_event(event)

    def _on_cancel(self, event: OrderCanceled) -> None:
        if self._exec_engine:
            self._exec_engine.process_event(event)

    def _on_expire(self, event: OrderExpired) -> None:
        if self._exec_engine:
            self._exec_engine.process_event(event)

    def _on_trigger(self, event: OrderTriggered) -> None:
        if self._exec_engine:
            self._exec_engine.process_event(event)

    # ── Account updates ────────────────────────────────────────────────────

    def _update_account_on_fill(self, event: OrderFilled) -> None:
        instrument = self._instruments.get(event.instrument_id)
        if instrument is None:
            return

        qty = event.last_qty.value
        px = event.last_px.value
        commission = event.commission.amount
        currency = self.base_currency

        if event.order_side == OrderSide.BUY:
            cost = qty * px + commission
            bal = self.account.balance_free(currency)
            if bal:
                new_total = bal.amount - cost
                cur_bal = self.account._balances.get(currency)
                locked = cur_bal.locked.amount if cur_bal else Decimal("0")
                self.account.update_balance(currency, max(new_total, Decimal("0")), locked)
        else:
            revenue = qty * px - commission
            bal = self.account.balance_free(currency)
            if bal:
                new_total = bal.amount + revenue
                cur_bal = self.account._balances.get(currency)
                locked = cur_bal.locked.amount if cur_bal else Decimal("0")
                self.account.update_balance(currency, new_total, locked)

        self.account.update_commissions(currency, commission)

    def _check_balance(self, order: Order) -> tuple[bool, str]:
        instrument = self._instruments.get(order.instrument_id)
        if instrument is None:
            return True, ""  # No instrument info, let it through

        # Determine approximate cost
        price_to_use: Optional[Price] = None
        if hasattr(order, "price") and order.price:
            price_to_use = order.price
        elif hasattr(order, "trigger_price") and order.trigger_price:
            price_to_use = order.trigger_price
        else:
            # Use best ask/bid from book if available
            engine = self._matching_engines.get(order.instrument_id)
            if engine:
                if order.side == OrderSide.BUY:
                    bp = engine.book.best_ask_price
                    price_to_use = Price(bp, instrument.price_precision) if bp else None
                else:
                    bp = engine.book.best_bid_price
                    price_to_use = Price(bp, instrument.price_precision) if bp else None

        if price_to_use is None:
            return True, ""  # Can't check without price; allow

        return self.account.can_submit_order(
            quantity=order.quantity.value,
            price=price_to_use.value,
            currency=self.base_currency,
        )

    # ── Properties ─────────────────────────────────────────────────────────

    @property
    def open_order_count(self) -> int:
        return sum(e.open_order_count for e in self._matching_engines.values())

    def best_bid_price(self, instrument_id: InstrumentId) -> Optional[Decimal]:
        engine = self._matching_engines.get(instrument_id)
        return engine.book.best_bid_price if engine else None

    def best_ask_price(self, instrument_id: InstrumentId) -> Optional[Decimal]:
        engine = self._matching_engines.get(instrument_id)
        return engine.book.best_ask_price if engine else None
