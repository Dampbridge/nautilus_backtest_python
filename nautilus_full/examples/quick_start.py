"""
Quick Start Example
===================
A minimal end-to-end backtest using nautilus_full.

Strategy: Buy-and-hold with trailing stop for drawdown protection.
Data:      Synthetic OHLCV bars (random walk).
"""
from __future__ import annotations

from decimal import Decimal

from nautilus_full.backtest.engine import BacktestEngine
from nautilus_full.core.enums import (
    AccountType,
    BarAggregation,
    OmsType,
    OrderSide,
    TimeInForce,
    TrailingOffsetType,
)
from nautilus_full.core.identifiers import InstrumentId, Venue
from nautilus_full.core.objects import Money, Price, Quantity, USD
from nautilus_full.data.wranglers import generate_bars
from nautilus_full.model.data import Bar, BarSpec, BarType
from nautilus_full.model.instruments.equity import Equity
from nautilus_full.trading.strategy import Strategy


class TrailingStopStrategy(Strategy):
    """
    Enter long on the first bar; protect with a 5% trailing stop.
    """

    def __init__(self, instrument_id: InstrumentId, qty: int = 100) -> None:
        super().__init__()
        self.instrument_id = instrument_id
        self.qty = qty
        self._in_position = False
        self._trailing_order = None

    def on_start(self) -> None:
        bar_type = BarType(
            instrument_id=self.instrument_id,
            bar_spec=BarSpec(1, BarAggregation.DAY),
        )
        self.subscribe_bars(bar_type)

    def on_bar(self, bar: Bar) -> None:
        ts = bar.ts_event
        if not self._in_position:
            # Buy on first bar
            order = self.order_factory.market(
                instrument_id=self.instrument_id,
                order_side=OrderSide.BUY,
                quantity=Quantity(self.qty, 0),
                ts_init=ts,
            )
            self.submit_order(order)
            self._in_position = True

            # Place a 5% trailing stop
            trailing_order = self.order_factory.trailing_stop_market(
                instrument_id=self.instrument_id,
                order_side=OrderSide.SELL,
                quantity=Quantity(self.qty, 0),
                trailing_offset=Decimal("0.05"),
                trailing_offset_type=TrailingOffsetType.BASIS_POINTS,
                reduce_only=True,
                ts_init=ts,
            )
            # Override: use 5% of price
            trailing_order.trailing_offset = Decimal("0.05") * bar.close.value
            trailing_order.trailing_offset_type = TrailingOffsetType.PRICE
            self.submit_order(trailing_order)
            self._trailing_order = trailing_order


def main():
    # 1. Generate synthetic daily bars
    instrument_id = InstrumentId.from_str("AAPL.NASDAQ")
    bars = generate_bars(
        instrument_id=instrument_id,
        n=252,
        start_price=150.0,
        volatility=0.015,
        seed=42,
    )

    # 2. Define instrument
    venue = Venue("NASDAQ")
    instr_id = InstrumentId(instrument_id.symbol, venue)
    instrument = Equity(
        instrument_id=instr_id,
        raw_symbol="AAPL",
        currency=USD,
        price_precision=2,
        price_increment=Price("0.01", 2),
        lot_size=Quantity("1", 0),
        taker_fee=Decimal("0.001"),
        maker_fee=Decimal("0.0005"),
    )

    # Fix bar instrument_id to match the venue
    bar_spec = BarSpec(1, BarAggregation.DAY)
    bar_type = BarType(instrument_id=instr_id, bar_spec=bar_spec)
    bars = [
        Bar(bar_type, b.open, b.high, b.low, b.close, b.volume, b.ts_event, b.ts_init)
        for b in bars
    ]

    # 3. Build engine
    engine = BacktestEngine()
    engine.add_venue(
        venue_name="NASDAQ",
        oms_type=OmsType.NETTING,
        account_type=AccountType.CASH,
        base_currency=USD,
        starting_balances=[Money(Decimal("100000"), USD)],
    )
    engine.add_instrument(instrument)
    engine.add_data(bars)

    # 4. Add strategy
    strategy = TrailingStopStrategy(instrument_id=instr_id, qty=100)
    engine.add_strategy(strategy)

    # 5. Run
    engine.run()

    # 6. Results
    result = engine.get_result()
    print(result)
    print("\nSummary:")
    print(result.summary().to_string())


if __name__ == "__main__":
    main()
