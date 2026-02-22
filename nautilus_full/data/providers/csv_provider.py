"""CSV data provider — loads OHLCV bars directly from CSV files."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import pandas as pd

from nautilus_full.core.enums import BarAggregation
from nautilus_full.core.identifiers import InstrumentId
from nautilus_full.model.data import Bar, BarSpec, BarType
from nautilus_full.data.wranglers import BarDataWrangler


class CSVBarProvider:
    """
    Load OHLCV bar data from CSV files.

    Supported formats:
      - Standard: datetime_col, open, high, low, close, volume
      - Yahoo Finance format (auto-detected)
      - Generic format with custom column mapping

    Parameters
    ----------
    instrument_id : InstrumentId
        Target instrument.
    aggregation : BarAggregation
        Bar aggregation (default: DAY).
    step : int
        Bar step (default: 1).
    price_precision : int
        Decimal places for prices.
    size_precision : int
        Decimal places for volume.
    """

    def __init__(
        self,
        instrument_id: InstrumentId,
        aggregation: BarAggregation = BarAggregation.DAY,
        step: int = 1,
        price_precision: int = 2,
        size_precision: int = 0,
    ) -> None:
        self.instrument_id = instrument_id
        self.bar_spec = BarSpec(step=step, aggregation=aggregation)
        self.bar_type = BarType(instrument_id=instrument_id, bar_spec=self.bar_spec)
        self.price_precision = price_precision
        self.size_precision = size_precision

    def load(
        self,
        path: str | Path,
        date_col: Optional[str] = None,
        column_map: Optional[dict[str, str]] = None,
        start: Optional[str] = None,
        end: Optional[str] = None,
    ) -> list[Bar]:
        """
        Load bars from a CSV file.

        Parameters
        ----------
        path : str | Path
            Path to the CSV file.
        date_col : str, optional
            Name of the date/timestamp column. If None, the first column is used.
        column_map : dict, optional
            Rename columns: {source_name: standard_name}.
            Standard names: open, high, low, close, volume.
        start : str, optional
            ISO date string to filter data from.
        end : str, optional
            ISO date string to filter data to.
        """
        df = pd.read_csv(path)
        df.columns = [c.strip() for c in df.columns]

        # Apply column mapping
        if column_map:
            df = df.rename(columns=column_map)

        # Set datetime index
        if date_col:
            df[date_col] = pd.to_datetime(df[date_col])
            df = df.set_index(date_col)
        else:
            # Try to parse the first column as dates
            first_col = df.columns[0]
            try:
                df[first_col] = pd.to_datetime(df[first_col])
                df = df.set_index(first_col)
            except Exception:
                df.index = pd.to_datetime(df.index)

        df.columns = [c.lower() for c in df.columns]

        # Handle Yahoo Finance column names
        if "adj close" in df.columns and "close" not in df.columns:
            df = df.rename(columns={"adj close": "close"})
        if "vol" in df.columns and "volume" not in df.columns:
            df = df.rename(columns={"vol": "volume"})

        # Date range filter
        if start:
            df = df[df.index >= pd.Timestamp(start)]
        if end:
            df = df[df.index <= pd.Timestamp(end)]

        df = df.sort_index()
        wrangler = BarDataWrangler(self.bar_type, self.price_precision, self.size_precision)
        return wrangler.process(df)

    def load_directory(
        self, directory: str | Path, pattern: str = "*.csv"
    ) -> list[Bar]:
        """Load and merge all CSV files in a directory."""
        directory = Path(directory)
        all_bars: list[Bar] = []
        for csv_file in sorted(directory.glob(pattern)):
            bars = self.load(csv_file)
            all_bars.extend(bars)
        return sorted(all_bars, key=lambda b: b.ts_event)
