"""
BacktestEngine — the main orchestration class.

Connects all subsystems and runs the event loop:
  Clock → Data → Exchange (matching) → ExecutionEngine → Strategies

Usage
-----
>>> engine = BacktestEngine()
>>> engine.add_venue("SIM", starting_balances=[Money("100000", USD)])
>>> engine.add_instrument(equity)
>>> engine.add_data(bars)
>>> engine.add_strategy(my_strategy)
>>> engine.run()
>>> result = engine.get_result()
>>> print(result)
"""
from __future__ import annotations

import time
from decimal import Decimal
from typing import Any, Optional

from nautilus_full.analysis.stats import compute_all_stats
from nautilus_full.backtest.config import BacktestConfig, VenueConfig
from nautilus_full.backtest.results import BacktestResult
from nautilus_full.core.clock import TestClock
from nautilus_full.core.enums import AccountType, OmsType, OrderStatus
from nautilus_full.core.identifiers import TraderId, Venue
from nautilus_full.core.msgbus import MessageBus
from nautilus_full.core.objects import Currency, Money
from nautilus_full.engine.data_engine import DataEngine
from nautilus_full.engine.execution_engine import ExecutionEngine
from nautilus_full.engine.risk_engine import RiskEngine
from nautilus_full.model.data import Bar, OrderBookDelta, OrderBookDeltas, QuoteTick, TradeTick
from nautilus_full.model.instruments.base import Instrument
from nautilus_full.model.orders.factory import OrderFactory
from nautilus_full.state.cache import Cache
from nautilus_full.state.portfolio import Portfolio
from nautilus_full.trading.actor import Actor
from nautilus_full.trading.strategy import Strategy
from nautilus_full.venues.simulated_exchange import SimulatedExchange
from nautilus_full.venues.models import (
    DefaultFillModel,
    FeeModel,
    FillModel,
    MakerTakerFeeModel,
    ZeroFeeModel,
)


class BacktestEngine:
    """
    Full backtesting engine.

    Wires together:
      - TestClock
      - MessageBus
      - Cache
      - Portfolio
      - RiskEngine
      - ExecutionEngine
      - DataEngine
      - SimulatedExchange (one per venue)
      - Strategy instances
      - Actor instances
    """

    def __init__(self, config: Optional[BacktestConfig] = None) -> None:
        cfg = config or BacktestConfig()
        self.trader_id = TraderId(cfg.trader_id)

        # Core infrastructure
        self.clock = TestClock()
        self.msgbus = MessageBus(trader_id=cfg.trader_id)
        self.cache = Cache()
        self.portfolio = Portfolio(self.cache)
        self.risk_engine = RiskEngine(self.portfolio, self.cache, self.msgbus)
        self.exec_engine = ExecutionEngine(self.cache, self.msgbus, self.risk_engine)
        self.data_engine = DataEngine(self.cache, self.msgbus)

        # Registries
        self._exchanges: dict[Venue, SimulatedExchange] = {}
        self._strategies: list[Strategy] = []
        self._actors: list[Actor] = []
        self._data: list[Any] = []
        self._instruments: dict = {}

        self._result: Optional[BacktestResult] = None
        self._run_time: float = 0.0

    # ── Configuration ──────────────────────────────────────────────────────

    def add_venue(
        self,
        venue_name: str,
        oms_type: OmsType = OmsType.HEDGING,
        account_type: AccountType = AccountType.CASH,
        base_currency: Optional[Currency] = None,
        starting_balances: Optional[list[Money]] = None,
        default_leverage: Decimal = Decimal("1"),
        book_spread_pct: Decimal = Decimal("0.0001"),
        fill_model: Optional[FillModel] = None,
        fee_model: Optional[FeeModel] = None,
    ) -> None:
        """Register a simulated venue."""
        venue = Venue(venue_name)
        balances = starting_balances or []

        if base_currency is None and balances:
            base_currency = balances[0].currency

        exchange = SimulatedExchange(
            venue=venue,
            oms_type=oms_type,
            account_type=account_type,
            base_currency=base_currency,
            starting_balances=balances,
            fill_model=fill_model,
            fee_model=fee_model,
            default_leverage=default_leverage,
            book_spread_pct=book_spread_pct,
            exec_engine=self.exec_engine,
        )
        self._exchanges[venue] = exchange
        self.exec_engine.register_venue(venue, exchange, oms_type)
        self.cache.add_account(exchange.account)

    def add_instrument(self, instrument: Instrument) -> None:
        """Register an instrument with the engine and all matching venues."""
        self.cache.add_instrument(instrument)
        self._instruments[instrument.id] = instrument
        exchange = self._exchanges.get(instrument.venue)
        if exchange:
            exchange.add_instrument(instrument)

    def add_data(
        self,
        data: list[Bar | QuoteTick | TradeTick | OrderBookDelta | OrderBookDeltas],
    ) -> None:
        """Add market data to the event queue."""
        self._data.extend(data)

    def add_strategy(self, strategy: Strategy) -> None:
        """Register a strategy and inject all dependencies."""
        order_factory = OrderFactory(self.trader_id, strategy.id)
        strategy.register(
            clock=self.clock,
            cache=self.cache,
            portfolio=self.portfolio,
            msgbus=self.msgbus,
            order_factory=order_factory,
            exec_engine=self.exec_engine,
            data_engine=self.data_engine,
        )
        self._strategies.append(strategy)

    def add_actor(self, actor: Actor) -> None:
        """Register a non-trading actor."""
        actor.register(
            clock=self.clock,
            cache=self.cache,
            portfolio=self.portfolio,
            msgbus=self.msgbus,
            data_engine=self.data_engine,
        )
        self._actors.append(actor)

    # ── Run ────────────────────────────────────────────────────────────────

    def run(
        self,
        start: Optional[int] = None,
        end: Optional[int] = None,
    ) -> None:
        """
        Run the backtest.

        Parameters
        ----------
        start : int, optional
            Start timestamp in nanoseconds (inclusive).
        end : int, optional
            End timestamp in nanoseconds (inclusive).
        """
        wall_start = time.perf_counter()

        # Sort data chronologically
        self._data.sort(key=lambda d: d.ts_event)

        # Apply time range filter
        data = self._data
        if start is not None:
            data = [d for d in data if d.ts_event >= start]
        if end is not None:
            data = [d for d in data if d.ts_event <= end]

        # Start strategies and actors
        for actor in self._actors:
            actor.on_start()
        for strategy in self._strategies:
            strategy.on_start()

        # Equity curve recording
        balance_curve: list[tuple[int, Decimal]] = []
        starting_balance = self._get_total_balance()
        if data:
            balance_curve.append((data[0].ts_event, starting_balance))

        # ── Main event loop ────────────────────────────────────────────────
        for datum in data:
            ts = datum.ts_event

            # Advance clock and fire timers
            time_events = self.clock.advance_time(ts)
            for te in time_events:
                if te.callback:
                    te.callback(te)

            # Route to exchange matching engines (fills) first,
            # then to data engine (strategy callbacks)
            if isinstance(datum, Bar):
                venue = datum.bar_type.instrument_id.venue
                exchange = self._exchanges.get(venue)
                if exchange:
                    exchange.process_bar(datum)
                self.data_engine.process_bar(datum)
                balance_curve.append((ts, self._get_total_balance()))

            elif isinstance(datum, QuoteTick):
                venue = datum.instrument_id.venue
                exchange = self._exchanges.get(venue)
                if exchange:
                    exchange.process_quote_tick(datum)
                self.data_engine.process_quote_tick(datum)

            elif isinstance(datum, TradeTick):
                venue = datum.instrument_id.venue
                exchange = self._exchanges.get(venue)
                if exchange:
                    exchange.process_trade_tick(datum)
                self.data_engine.process_trade_tick(datum)

            elif isinstance(datum, OrderBookDelta):
                venue = datum.instrument_id.venue
                exchange = self._exchanges.get(venue)
                if exchange:
                    exchange.process_order_book_delta(datum)
                self.data_engine.process_book_delta(datum)

            elif isinstance(datum, OrderBookDeltas):
                venue = datum.instrument_id.venue
                exchange = self._exchanges.get(venue)
                if exchange:
                    exchange.process_order_book_deltas(datum)
                self.data_engine.process_book_deltas(datum)

        # Record final balance
        final_balance = self._get_total_balance()
        if balance_curve:
            balance_curve.append((balance_curve[-1][0], final_balance))

        # Stop strategies and actors
        for strategy in self._strategies:
            strategy.on_stop()
        for actor in self._actors:
            actor.on_stop()

        self._run_time = time.perf_counter() - wall_start
        self._result = self._build_result(starting_balance, final_balance, balance_curve)

    # ── Result ─────────────────────────────────────────────────────────────

    def get_result(self) -> BacktestResult:
        if self._result is None:
            raise RuntimeError("No result available. Run the backtest first.")
        return self._result

    def reset(self) -> None:
        """Reset for a fresh run (keeps instruments and venue config)."""
        self._data.clear()
        self._result = None
        self.cache.reset()
        self.msgbus.reset()
        for strategy in self._strategies:
            strategy.on_reset()
        for actor in self._actors:
            actor.on_reset()
        # Reset exchanges
        for exchange in self._exchanges.values():
            for engine in exchange._matching_engines.values():
                engine.reset()

    def dispose(self) -> None:
        """Full teardown."""
        self._data.clear()
        self._strategies.clear()
        self._actors.clear()
        self._exchanges.clear()
        self._result = None

    # ── Internal helpers ───────────────────────────────────────────────────

    def _get_total_balance(self) -> Decimal:
        total = Decimal("0")
        for exchange in self._exchanges.values():
            if exchange.base_currency:
                bal = exchange.account.balance_total(exchange.base_currency)
                if bal:
                    total += bal.amount
        return total

    def _build_result(
        self,
        starting_balance: Decimal,
        ending_balance: Decimal,
        balance_curve: list[tuple[int, Decimal]],
    ) -> BacktestResult:
        from nautilus_full.analysis.stats import compute_all_stats

        all_orders = self.cache.orders()
        all_positions = self.cache.positions()
        total_fills = sum(1 for o in all_orders if o.is_filled)
        total_commissions = sum(
            sum(a for a in exchange.account.commissions.values())
            for exchange in self._exchanges.values()
        )

        stats = compute_all_stats(
            equity_curve=balance_curve,
            positions=all_positions,
            starting_balance=starting_balance,
            ending_balance=ending_balance,
        )

        start_ns = balance_curve[0][0] if balance_curve else 0
        end_ns = balance_curve[-1][0] if balance_curve else 0

        return BacktestResult(
            trader_id=str(self.trader_id),
            start_time_ns=start_ns,
            end_time_ns=end_ns,
            run_time_seconds=self._run_time,
            starting_balance=starting_balance,
            ending_balance=ending_balance,
            total_return=ending_balance - starting_balance,
            total_orders=len(all_orders),
            total_positions=len(all_positions),
            total_fills=total_fills,
            total_commissions=Decimal(str(total_commissions)),
            total_return_pct=stats["total_return_pct"],
            annualized_return_pct=stats["annualized_return_pct"],
            annualized_volatility_pct=stats["annualized_volatility_pct"],
            sharpe_ratio=stats["sharpe_ratio"],
            sortino_ratio=stats["sortino_ratio"],
            calmar_ratio=stats["calmar_ratio"],
            max_drawdown_pct=stats["max_drawdown_pct"],
            max_drawdown_abs=stats["max_drawdown_abs"],
            win_rate=stats["win_rate_pct"] / 100,
            profit_factor=stats["profit_factor"],
            expectancy=stats["expectancy"],
            avg_win=stats["avg_win"],
            avg_loss=stats["avg_loss"],
            balance_curve=balance_curve,
        )
