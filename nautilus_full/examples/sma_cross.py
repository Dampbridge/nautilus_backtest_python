"""
SMA Crossover Strategy Example
================================
Classic dual SMA crossover with:
  - Market entry on golden cross / death cross
  - OCO exit: take-profit limit + stop-loss stop market
  - Comprehensive result reporting
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from nautilus_full.backtest.engine import BacktestEngine
from nautilus_full.core.enums import (
    AccountType,
    BarAggregation,
    ContingencyType,
    OmsType,
    OrderSide,
    TimeInForce,
)
from nautilus_full.core.identifiers import InstrumentId, OrderListId, Venue
from nautilus_full.core.objects import Money, Price, Quantity, USD
from nautilus_full.data.wranglers import generate_bars
from nautilus_full.indicators.sma import SimpleMovingAverage
from nautilus_full.model.data import Bar, BarSpec, BarType
from nautilus_full.model.instruments.equity import Equity
from nautilus_full.model.orders.base import Order
from nautilus_full.trading.config import StrategyConfig
from nautilus_full.trading.strategy import Strategy


@dataclass
class SMACrossConfig(StrategyConfig):
    fast_period: int = 10
    slow_period: int = 30
    take_profit_pct: float = 0.05     # 5% above entry
    stop_loss_pct: float = 0.02       # 2% below entry
    position_size: int = 100


class SMACrossStrategy(Strategy):
    """
    Simple SMA crossover strategy:
      - BUY when fast SMA crosses above slow SMA
      - SELL when fast SMA crosses below slow SMA
      - Each entry is protected by an OCO TP/SL pair
    """

    def __init__(
        self,
        instrument_id: InstrumentId,
        config: Optional[SMACrossConfig] = None,
    ) -> None:
        cfg = config or SMACrossConfig()
        super().__init__(config=cfg)
        self.instrument_id = instrument_id
        self.cfg = cfg

        self.fast_sma = SimpleMovingAverage(cfg.fast_period)
        self.slow_sma = SimpleMovingAverage(cfg.slow_period)

        self._prev_fast: Optional[Decimal] = None
        self._prev_slow: Optional[Decimal] = None
        self._entry_price: Optional[Price] = None

    def on_start(self) -> None:
        bar_type = BarType(
            instrument_id=self.instrument_id,
            bar_spec=BarSpec(1, BarAggregation.DAY),
        )
        self.register_indicator_for_bars(bar_type, self.fast_sma)
        self.register_indicator_for_bars(bar_type, self.slow_sma)
        self.subscribe_bars(bar_type)

    def on_bar(self, bar: Bar) -> None:
        if not self.fast_sma.initialized or not self.slow_sma.initialized:
            self._prev_fast = self.fast_sma.value
            self._prev_slow = self.slow_sma.value
            return

        fast = self.fast_sma.value
        slow = self.slow_sma.value
        ts = bar.ts_event

        # Crossover detection
        golden_cross = (
            self._prev_fast is not None
            and self._prev_slow is not None
            and self._prev_fast <= self._prev_slow
            and fast > slow
        )
        death_cross = (
            self._prev_fast is not None
            and self._prev_slow is not None
            and self._prev_fast >= self._prev_slow
            and fast < slow
        )

        # Check if we have an open position
        open_positions = self.cache.positions_open(
            instrument_id=self.instrument_id, strategy_id=self.id
        )
        has_long = any(p.is_long for p in open_positions)
        has_short = any(p.is_short for p in open_positions)

        # Golden cross: go long
        if golden_cross and not has_long:
            # Close any short first
            if has_short:
                self.close_all_positions(self.instrument_id, ts_init=ts)
                self.cancel_all_orders(self.instrument_id)

            # Enter long
            entry = self.order_factory.market(
                instrument_id=self.instrument_id,
                order_side=OrderSide.BUY,
                quantity=Quantity(self.cfg.position_size, 0),
                ts_init=ts,
            )
            self.submit_order(entry)
            self._entry_price = bar.close

        # Death cross: go short (or just exit long)
        elif death_cross and not has_short:
            if has_long:
                self.close_all_positions(self.instrument_id, ts_init=ts)
                self.cancel_all_orders(self.instrument_id)

        self._prev_fast = fast
        self._prev_slow = slow

    def on_position_opened(self, event) -> None:
        """Place OCO take-profit and stop-loss when position opens."""
        if self._entry_price is None:
            return

        ep = self._entry_price.value
        pos_side = event.entry_side
        qty = Quantity(self.cfg.position_size, 0)
        ts = event.ts_event

        if pos_side == OrderSide.BUY:
            tp_price = Price(ep * Decimal(str(1 + self.cfg.take_profit_pct)), 2)
            sl_price = Price(ep * Decimal(str(1 - self.cfg.stop_loss_pct)), 2)

            # Take-profit: sell limit
            tp = self.order_factory.limit(
                instrument_id=self.instrument_id,
                order_side=OrderSide.SELL,
                quantity=qty,
                price=tp_price,
                time_in_force=TimeInForce.GTC,
                reduce_only=True,
                ts_init=ts,
            )
            # Stop-loss: sell stop market
            sl = self.order_factory.stop_market(
                instrument_id=self.instrument_id,
                order_side=OrderSide.SELL,
                quantity=qty,
                trigger_price=sl_price,
                time_in_force=TimeInForce.GTC,
                reduce_only=True,
                ts_init=ts,
            )
            # Link as OCO
            self.order_factory.oco(tp, sl)

            self.submit_order(tp)
            self.submit_order(sl)

    def on_stop(self) -> None:
        """Close any remaining positions at end of backtest."""
        self.close_all_positions(self.instrument_id)


def run_sma_cross(
    fast: int = 10,
    slow: int = 30,
    n_bars: int = 500,
    cash: float = 100_000.0,
) -> None:
    """Run the SMA crossover backtest and print results."""
    # Generate synthetic data
    raw_id = InstrumentId.from_str("SPY.NASDAQ")
    bars = generate_bars(raw_id, n=n_bars, start_price=400.0, volatility=0.012, seed=99)

    venue = Venue("NASDAQ")
    instr_id = InstrumentId("SPY", venue)
    instrument = Equity(
        instrument_id=instr_id,
        raw_symbol="SPY",
        currency=USD,
        price_precision=2,
        price_increment=Price("0.01", 2),
        lot_size=Quantity("1", 0),
        taker_fee=Decimal("0.0005"),
        maker_fee=Decimal("0.0002"),
    )
    bar_spec = BarSpec(1, BarAggregation.DAY)
    bar_type = BarType(instrument_id=instr_id, bar_spec=bar_spec)
    bars = [
        Bar(bar_type, b.open, b.high, b.low, b.close, b.volume, b.ts_event, b.ts_init)
        for b in bars
    ]

    engine = BacktestEngine()
    engine.add_venue(
        venue_name="NASDAQ",
        oms_type=OmsType.NETTING,
        account_type=AccountType.CASH,
        base_currency=USD,
        starting_balances=[Money(Decimal(str(cash)), USD)],
    )
    engine.add_instrument(instrument)
    engine.add_data(bars)

    config = SMACrossConfig(
        strategy_id="SMA-Cross-001",
        fast_period=fast,
        slow_period=slow,
    )
    strategy = SMACrossStrategy(instrument_id=instr_id, config=config)
    engine.add_strategy(strategy)

    print(f"Running SMA({fast},{slow}) crossover on {n_bars} bars...")
    engine.run()

    result = engine.get_result()
    print(result)

    # HTML report
    from nautilus_full.visualization.report import generate_html_report
    generate_html_report(result, output_path="sma_cross_report.html")


if __name__ == "__main__":
    run_sma_cross(fast=10, slow=30, n_bars=500)
