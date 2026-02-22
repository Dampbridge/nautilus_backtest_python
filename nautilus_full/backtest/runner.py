"""
BacktestRunner — simplified high-level entry point.

Provides a ``Backtest`` class similar to the backtesting.py API for quick,
low-boilerplate backtests.

Usage
-----
>>> bt = Backtest(data=bars, strategy=MyStrategy, cash=100_000, commission=0.001)
>>> result = bt.run()
>>> bt.plot()
"""
from __future__ import annotations

from decimal import Decimal
from typing import Optional, Type

from nautilus_full.backtest.engine import BacktestEngine
from nautilus_full.backtest.results import BacktestResult
from nautilus_full.core.enums import AccountType, BarAggregation, OmsType
from nautilus_full.core.identifiers import InstrumentId, Venue
from nautilus_full.core.objects import Currency, Money
from nautilus_full.core.objects import USD
from nautilus_full.model.data import Bar, BarSpec, BarType
from nautilus_full.model.instruments.equity import Equity
from nautilus_full.model.instruments.base import Instrument
from nautilus_full.model.orders.factory import OrderFactory
from nautilus_full.trading.strategy import Strategy
from nautilus_full.venues.models import MakerTakerFeeModel, ZeroFeeModel


class Backtest:
    """
    Simplified backtest runner.

    Parameters
    ----------
    data : list[Bar]
        Historical price data.
    strategy : type[Strategy]
        Strategy class (will be instantiated with strategy_kwargs).
    cash : float
        Starting capital.
    commission : float
        Per-trade commission rate (e.g. 0.001 = 0.1%).
    margin : float
        Margin fraction (1.0 = no leverage).
    exclusive_orders : bool
        If True, cancel existing orders before placing new ones.
    strategy_kwargs : dict
        Keyword arguments forwarded to the strategy constructor.
    """

    def __init__(
        self,
        data: list[Bar],
        strategy: Type[Strategy],
        cash: float = 100_000.0,
        commission: float = 0.0,
        margin: float = 1.0,
        exclusive_orders: bool = False,
        strategy_kwargs: Optional[dict] = None,
        venue_name: str = "SIM",
        currency: Currency = USD,
    ) -> None:
        self._data = data
        self._strategy_cls = strategy
        self._cash = cash
        self._commission = commission
        self._margin = margin
        self._exclusive_orders = exclusive_orders
        self._strategy_kwargs = strategy_kwargs or {}
        self._venue_name = venue_name
        self._currency = currency

        self._result: Optional[BacktestResult] = None
        self._engine: Optional[BacktestEngine] = None

    def run(self, start=None, end=None) -> BacktestResult:
        """Run the backtest and return the result."""
        if not self._data:
            raise ValueError("No data provided")

        # Derive instrument from bar data
        bar_type = self._data[0].bar_type
        instrument_id = bar_type.instrument_id
        venue = Venue(self._venue_name)
        # Use a simple equity instrument if the venue matches
        instr_id = InstrumentId(instrument_id.symbol, venue)

        from nautilus_full.core.objects import Price, Quantity
        instrument = Equity(
            instrument_id=instr_id,
            raw_symbol=instr_id.symbol,
            currency=self._currency,
            price_precision=self._data[0].open.precision,
            price_increment=Price("0.01", 2),
            lot_size=Quantity("1", 0),
            taker_fee=Decimal(str(self._commission)),
            maker_fee=Decimal(str(self._commission)),
        )

        # Re-wrap bars to the correct instrument_id
        bar_spec = bar_type.bar_spec
        new_bar_type = BarType(instrument_id=instr_id, bar_spec=bar_spec)
        bars = [
            Bar(
                bar_type=new_bar_type,
                open=b.open, high=b.high, low=b.low, close=b.close,
                volume=b.volume, ts_event=b.ts_event, ts_init=b.ts_init,
            )
            for b in self._data
        ]

        # Build engine
        engine = BacktestEngine()
        engine.add_venue(
            venue_name=self._venue_name,
            oms_type=OmsType.NETTING,
            account_type=AccountType.MARGIN if self._margin < 1.0 else AccountType.CASH,
            base_currency=self._currency,
            starting_balances=[Money(Decimal(str(self._cash)), self._currency)],
            default_leverage=Decimal(str(1 / self._margin if self._margin > 0 else 1)),
            fee_model=MakerTakerFeeModel() if self._commission > 0 else ZeroFeeModel(),
        )
        engine.add_instrument(instrument)
        engine.add_data(bars)

        # Instantiate strategy
        strategy = self._strategy_cls(**self._strategy_kwargs)
        engine.add_strategy(strategy)

        engine.run(start=start, end=end)
        self._result = engine.get_result()
        self._engine = engine
        return self._result

    def plot(self, filename: Optional[str] = None) -> None:
        """Plot the equity curve and trade signals using Bokeh."""
        if self._result is None:
            raise RuntimeError("Run the backtest first")
        from nautilus_full.visualization.bokeh_plot import plot_backtest
        plot_backtest(self._result, filename=filename)

    def get_result(self) -> BacktestResult:
        if self._result is None:
            raise RuntimeError("Run the backtest first")
        return self._result
