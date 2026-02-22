"""
DataCatalog — Parquet-backed persistent market data store.

Usage
-----
>>> catalog = DataCatalog(path="./data")
>>> catalog.write_bars(bars, instrument_id="BTCUSDT.BINANCE")
>>> bars = catalog.read_bars("BTCUSDT.BINANCE", start="2024-01-01", end="2024-12-31")
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import pandas as pd

from nautilus_full.core.enums import BarAggregation
from nautilus_full.core.identifiers import InstrumentId
from nautilus_full.core.objects import Price, Quantity
from nautilus_full.model.data import Bar, BarSpec, BarType, QuoteTick, TradeTick
from nautilus_full.data.wranglers import BarDataWrangler, QuoteTickWrangler, TradeTickWrangler


class DataCatalog:
    """
    Parquet-backed data catalog.

    Directory structure::

        {path}/
          bars/
            {instrument_id}/
              {aggregation}_{step}/
                {year}.parquet
          quotes/
            {instrument_id}.parquet
          trades/
            {instrument_id}.parquet

    Parameters
    ----------
    path : str | Path
        Root directory for the catalog.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.mkdir(parents=True, exist_ok=True)

    # ── Bars ───────────────────────────────────────────────────────────────

    def write_bars(
        self,
        bars: list[Bar],
        compression: str = "snappy",
    ) -> Path:
        """
        Write a list of Bar objects to Parquet.

        File is partitioned by instrument + bar_spec.
        """
        if not bars:
            raise ValueError("Cannot write empty bars list")
        bar_type = bars[0].bar_type
        out_dir = self._bars_dir(bar_type)
        out_dir.mkdir(parents=True, exist_ok=True)
        out_file = out_dir / "data.parquet"

        rows = []
        for bar in bars:
            rows.append({
                "ts_event": bar.ts_event,
                "open": float(bar.open.value),
                "high": float(bar.high.value),
                "low": float(bar.low.value),
                "close": float(bar.close.value),
                "volume": float(bar.volume.value),
            })
        df = pd.DataFrame(rows).set_index("ts_event").sort_index()
        df.to_parquet(out_file, compression=compression)
        return out_file

    def read_bars(
        self,
        bar_type: BarType,
        start: Optional[str | pd.Timestamp] = None,
        end: Optional[str | pd.Timestamp] = None,
        price_precision: int = 2,
        size_precision: int = 0,
    ) -> list[Bar]:
        """Read bars from Parquet for the given bar_type and date range."""
        out_file = self._bars_dir(bar_type) / "data.parquet"
        if not out_file.exists():
            return []

        df = pd.read_parquet(out_file)
        if start is not None:
            start_ns = int(pd.Timestamp(start).value)
            df = df[df.index >= start_ns]
        if end is not None:
            end_ns = int(pd.Timestamp(end).value)
            df = df[df.index <= end_ns]

        df.index = pd.to_datetime(df.index)
        wrangler = BarDataWrangler(bar_type, price_precision, size_precision)
        return wrangler.process(df)

    # ── Quote ticks ────────────────────────────────────────────────────────

    def write_quote_ticks(
        self,
        ticks: list[QuoteTick],
        compression: str = "snappy",
    ) -> Path:
        if not ticks:
            raise ValueError("Cannot write empty ticks list")
        instrument_id = ticks[0].instrument_id
        out_dir = self._quotes_dir(instrument_id)
        out_dir.mkdir(parents=True, exist_ok=True)
        out_file = out_dir / "data.parquet"

        rows = []
        for t in ticks:
            rows.append({
                "ts_event": t.ts_event,
                "bid_price": float(t.bid_price.value),
                "ask_price": float(t.ask_price.value),
                "bid_size": float(t.bid_size.value),
                "ask_size": float(t.ask_size.value),
            })
        df = pd.DataFrame(rows).set_index("ts_event").sort_index()
        df.to_parquet(out_file, compression=compression)
        return out_file

    def read_quote_ticks(
        self,
        instrument_id: InstrumentId,
        start: Optional[str | pd.Timestamp] = None,
        end: Optional[str | pd.Timestamp] = None,
        price_precision: int = 5,
        size_precision: int = 0,
    ) -> list[QuoteTick]:
        out_file = self._quotes_dir(instrument_id) / "data.parquet"
        if not out_file.exists():
            return []
        df = pd.read_parquet(out_file)
        if start:
            df = df[df.index >= int(pd.Timestamp(start).value)]
        if end:
            df = df[df.index <= int(pd.Timestamp(end).value)]
        df.index = pd.to_datetime(df.index)
        return QuoteTickWrangler(instrument_id, price_precision, size_precision).process(df)

    # ── Trade ticks ────────────────────────────────────────────────────────

    def write_trade_ticks(
        self,
        ticks: list[TradeTick],
        compression: str = "snappy",
    ) -> Path:
        if not ticks:
            raise ValueError("Cannot write empty ticks list")
        instrument_id = ticks[0].instrument_id
        out_dir = self._trades_dir(instrument_id)
        out_dir.mkdir(parents=True, exist_ok=True)
        out_file = out_dir / "data.parquet"

        rows = []
        for t in ticks:
            rows.append({
                "ts_event": t.ts_event,
                "price": float(t.price.value),
                "size": float(t.size.value),
                "aggressor_side": t.aggressor_side.name,
                "trade_id": t.trade_id,
            })
        df = pd.DataFrame(rows).set_index("ts_event").sort_index()
        df.to_parquet(out_file, compression=compression)
        return out_file

    def read_trade_ticks(
        self,
        instrument_id: InstrumentId,
        start: Optional[str | pd.Timestamp] = None,
        end: Optional[str | pd.Timestamp] = None,
        price_precision: int = 5,
        size_precision: int = 0,
    ) -> list[TradeTick]:
        out_file = self._trades_dir(instrument_id) / "data.parquet"
        if not out_file.exists():
            return []
        df = pd.read_parquet(out_file)
        if start:
            df = df[df.index >= int(pd.Timestamp(start).value)]
        if end:
            df = df[df.index <= int(pd.Timestamp(end).value)]
        df.index = pd.to_datetime(df.index)
        return TradeTickWrangler(instrument_id, price_precision, size_precision).process(df)

    # ── Listing ────────────────────────────────────────────────────────────

    def list_bar_types(self) -> list[str]:
        bars_root = self.path / "bars"
        if not bars_root.exists():
            return []
        result = []
        for instr_dir in bars_root.iterdir():
            for spec_dir in instr_dir.iterdir():
                result.append(f"{instr_dir.name}/{spec_dir.name}")
        return result

    def list_instruments(self) -> list[str]:
        instruments: set[str] = set()
        for sub in ["bars", "quotes", "trades"]:
            d = self.path / sub
            if d.exists():
                for child in d.iterdir():
                    instruments.add(child.name)
        return sorted(instruments)

    # ── Path helpers ───────────────────────────────────────────────────────

    def _bars_dir(self, bar_type: BarType) -> Path:
        spec = bar_type.bar_spec
        instr_slug = str(bar_type.instrument_id).replace(".", "_")
        spec_slug = f"{spec.step}_{spec.aggregation.name}"
        return self.path / "bars" / instr_slug / spec_slug

    def _quotes_dir(self, instrument_id: InstrumentId) -> Path:
        slug = str(instrument_id).replace(".", "_")
        return self.path / "quotes" / slug

    def _trades_dir(self, instrument_id: InstrumentId) -> Path:
        slug = str(instrument_id).replace(".", "_")
        return self.path / "trades" / slug
