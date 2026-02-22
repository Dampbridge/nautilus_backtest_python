"""
DataWranglers — convert raw data (CSV, DataFrames) to framework objects.

Each wrangler targets a specific data type:
  BarDataWrangler        — OHLCV bars from a pandas DataFrame or CSV
  QuoteTickWrangler      — Bid/Ask quote ticks
  TradeTickWrangler      — Individual trades
  OrderBookDeltaWrangler — L2 order book updates
"""
from __future__ import annotations

from decimal import Decimal
from typing import Optional, TYPE_CHECKING

import pandas as pd

from nautilus_full.core.enums import AggressorSide, BarAggregation, BookAction, BookType, OrderSide, PriceType
from nautilus_full.core.identifiers import InstrumentId
from nautilus_full.core.objects import Price, Quantity
from nautilus_full.model.data import (
    Bar,
    BarSpec,
    BarType,
    BookOrder,
    OrderBookDelta,
    QuoteTick,
    TradeTick,
)
from nautilus_full.model.instruments.base import Instrument


def _to_ns(ts) -> int:
    """Convert a pandas Timestamp or integer to nanoseconds."""
    if isinstance(ts, int):
        return ts
    if hasattr(ts, "value"):
        return int(ts.value)
    try:
        return int(pd.Timestamp(ts).value)
    except Exception:
        return 0


# ── Bar wrangler ──────────────────────────────────────────────────────────────

class BarDataWrangler:
    """
    Convert a pandas DataFrame to a list of Bar objects.

    Expected DataFrame columns (case-insensitive):
      open, high, low, close, volume
      index: datetime (timezone-aware or naive)

    Parameters
    ----------
    bar_type : BarType
        The target bar type (instrument + spec).
    price_precision : int
        Decimal precision for prices.
    size_precision : int
        Decimal precision for volume.
    """

    def __init__(
        self,
        bar_type: BarType,
        price_precision: int = 2,
        size_precision: int = 0,
    ) -> None:
        self.bar_type = bar_type
        self.price_precision = price_precision
        self.size_precision = size_precision

    def process(self, df: pd.DataFrame) -> list[Bar]:
        """Process a DataFrame and return sorted list of Bar objects."""
        df = df.copy()
        df.columns = [c.lower() for c in df.columns]
        bars = []
        for ts, row in df.iterrows():
            ts_ns = _to_ns(ts)
            bars.append(Bar(
                bar_type=self.bar_type,
                open=Price(row["open"], self.price_precision),
                high=Price(row["high"], self.price_precision),
                low=Price(row["low"], self.price_precision),
                close=Price(row["close"], self.price_precision),
                volume=Quantity(row.get("volume", 0), self.size_precision),
                ts_event=ts_ns,
                ts_init=ts_ns,
            ))
        return sorted(bars, key=lambda b: b.ts_event)

    @classmethod
    def from_csv(
        cls,
        path: str,
        bar_type: BarType,
        price_precision: int = 2,
        size_precision: int = 0,
        date_column: Optional[str] = None,
        **read_csv_kwargs,
    ) -> list[Bar]:
        """Convenience: load a CSV file directly into bars."""
        df = pd.read_csv(path, **read_csv_kwargs)
        if date_column:
            df[date_column] = pd.to_datetime(df[date_column])
            df = df.set_index(date_column)
        else:
            # Try to parse index
            try:
                df.index = pd.to_datetime(df.index)
            except Exception:
                pass
        wrangler = cls(bar_type, price_precision, size_precision)
        return wrangler.process(df)


# ── Quote tick wrangler ───────────────────────────────────────────────────────

class QuoteTickWrangler:
    """
    Convert a DataFrame of bid/ask quotes to QuoteTick objects.

    Expected columns: bid_price, ask_price, bid_size, ask_size
    Index: datetime
    """

    def __init__(
        self,
        instrument_id: InstrumentId,
        price_precision: int = 5,
        size_precision: int = 0,
    ) -> None:
        self.instrument_id = instrument_id
        self.price_precision = price_precision
        self.size_precision = size_precision

    def process(self, df: pd.DataFrame) -> list[QuoteTick]:
        df = df.copy()
        df.columns = [c.lower() for c in df.columns]
        ticks = []
        for ts, row in df.iterrows():
            ts_ns = _to_ns(ts)
            ticks.append(QuoteTick(
                instrument_id=self.instrument_id,
                bid_price=Price(row.get("bid_price", row.get("bid", 0)), self.price_precision),
                ask_price=Price(row.get("ask_price", row.get("ask", 0)), self.price_precision),
                bid_size=Quantity(row.get("bid_size", row.get("bid_qty", 0)), self.size_precision),
                ask_size=Quantity(row.get("ask_size", row.get("ask_qty", 0)), self.size_precision),
                ts_event=ts_ns,
                ts_init=ts_ns,
            ))
        return sorted(ticks, key=lambda t: t.ts_event)


# ── Trade tick wrangler ───────────────────────────────────────────────────────

class TradeTickWrangler:
    """
    Convert a DataFrame of trades to TradeTick objects.

    Expected columns: price, size/qty, [side/aggressor_side]
    Index: datetime
    """

    def __init__(
        self,
        instrument_id: InstrumentId,
        price_precision: int = 5,
        size_precision: int = 0,
    ) -> None:
        self.instrument_id = instrument_id
        self.price_precision = price_precision
        self.size_precision = size_precision
        self._count = 0

    def process(self, df: pd.DataFrame) -> list[TradeTick]:
        df = df.copy()
        df.columns = [c.lower() for c in df.columns]
        ticks = []
        for ts, row in df.iterrows():
            self._count += 1
            ts_ns = _to_ns(ts)

            # Determine aggressor side
            side_raw = row.get("side", row.get("aggressor_side", ""))
            if str(side_raw).upper() in ("BUY", "BUYER", "B"):
                agg_side = AggressorSide.BUYER
            elif str(side_raw).upper() in ("SELL", "SELLER", "S"):
                agg_side = AggressorSide.SELLER
            else:
                agg_side = AggressorSide.NO_AGGRESSOR

            ticks.append(TradeTick(
                instrument_id=self.instrument_id,
                price=Price(row["price"], self.price_precision),
                size=Quantity(row.get("size", row.get("qty", row.get("quantity", 0))), self.size_precision),
                aggressor_side=agg_side,
                trade_id=str(row.get("trade_id", row.get("id", self._count))),
                ts_event=ts_ns,
                ts_init=ts_ns,
            ))
        return sorted(ticks, key=lambda t: t.ts_event)


# ── Bars from instrument ───────────────────────────────────────────────────────

def bars_from_instrument(
    instrument: Instrument,
    df: pd.DataFrame,
    aggregation: BarAggregation = BarAggregation.DAY,
    step: int = 1,
) -> list[Bar]:
    """
    Convenience wrapper: create bars using instrument's precision settings.
    """
    bar_spec = BarSpec(step=step, aggregation=aggregation)
    bar_type = BarType(instrument_id=instrument.id, bar_spec=bar_spec)
    wrangler = BarDataWrangler(
        bar_type=bar_type,
        price_precision=instrument.price_precision,
        size_precision=instrument.size_precision,
    )
    return wrangler.process(df)


# ── Synthetic data generators ─────────────────────────────────────────────────

def generate_bars(
    instrument_id: InstrumentId,
    n: int = 252,
    start_price: float = 100.0,
    volatility: float = 0.01,
    seed: int = 42,
    price_precision: int = 2,
    start_ts_ns: int = 0,
    bar_interval_ns: int = 86_400_000_000_000,  # 1 day
) -> list[Bar]:
    """
    Generate synthetic OHLCV bars using a random walk.

    Useful for testing and examples.
    """
    import random
    rng = random.Random(seed)

    bar_spec = BarSpec(step=1, aggregation=BarAggregation.DAY)
    bar_type = BarType(instrument_id=instrument_id, bar_spec=bar_spec)
    bars = []
    price = Decimal(str(start_price))

    for i in range(n):
        change_pct = Decimal(str(rng.gauss(0, volatility)))
        open_px = price
        close_px = price * (1 + change_pct)
        high_px = max(open_px, close_px) * Decimal(str(1 + abs(float(change_pct)) / 2))
        low_px = min(open_px, close_px) * Decimal(str(1 - abs(float(change_pct)) / 2))
        volume = Decimal(str(int(rng.uniform(1000, 10000))))

        ts_ns = start_ts_ns + i * bar_interval_ns
        bars.append(Bar(
            bar_type=bar_type,
            open=Price(open_px, price_precision),
            high=Price(high_px, price_precision),
            low=Price(low_px, price_precision),
            close=Price(close_px, price_precision),
            volume=Quantity(volume, 0),
            ts_event=ts_ns,
            ts_init=ts_ns,
        ))
        price = close_px

    return bars
