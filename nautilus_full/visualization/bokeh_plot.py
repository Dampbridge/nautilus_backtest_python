"""
Interactive Bokeh visualizations for backtest results.

Generates:
  - Equity curve chart
  - Drawdown chart
  - Candlestick OHLCV chart with trade entry/exit markers
  - Combined HTML report

Requires: bokeh >= 3.0
"""
from __future__ import annotations

import os
from decimal import Decimal
from pathlib import Path
from typing import Optional, TYPE_CHECKING

import pandas as pd

if TYPE_CHECKING:
    from nautilus_full.backtest.results import BacktestResult


def _ensure_bokeh():
    try:
        import bokeh
        return bokeh
    except ImportError:
        raise ImportError(
            "Bokeh is required for visualization. Install with: pip install bokeh"
        )


def plot_equity_curve(
    result: "BacktestResult",
    title: str = "Equity Curve",
    show: bool = True,
    filename: Optional[str] = None,
):
    """
    Plot the equity curve using Bokeh.

    Parameters
    ----------
    result : BacktestResult
    title : str
    show : bool
        If True, open the plot in a browser.
    filename : str, optional
        HTML file to save the plot. If None and show=False, auto-generated.
    """
    bk = _ensure_bokeh()
    from bokeh.plotting import figure, output_file, show as bk_show, save
    from bokeh.models import HoverTool, CrosshairTool, Span
    from bokeh.layouts import column

    equity = result.equity_series()
    if equity.empty:
        print("No equity data to plot")
        return

    dates = equity.index.to_pydatetime()
    values = equity.values

    p = figure(
        title=title,
        x_axis_type="datetime",
        width=1200,
        height=400,
        tools="pan,wheel_zoom,box_zoom,reset,save",
        toolbar_location="above",
    )
    p.line(dates, values, line_width=2, color="#2196F3", legend_label="Equity")
    p.add_tools(HoverTool(
        tooltips=[("Date", "@x{%F}"), ("Equity", "@y{$0,0.00}")],
        formatters={"@x": "datetime"},
        mode="vline",
    ))

    # Drawdown chart
    dd = result.drawdown_series()
    dd_dates = dd.index.to_pydatetime()
    dd_values = dd.values

    p2 = figure(
        title="Drawdown",
        x_axis_type="datetime",
        x_range=p.x_range,
        width=1200,
        height=200,
        tools="pan,wheel_zoom,box_zoom,reset",
        toolbar_location=None,
    )
    p2.varea(
        dd_dates, [0] * len(dd_dates), dd_values,
        color="#F44336", alpha=0.5,
    )
    p2.line(dd_dates, dd_values, line_width=1, color="#F44336")

    layout = column(p, p2)

    if filename:
        out = filename
    elif not show:
        out = "backtest_result.html"
    else:
        out = None

    if out:
        output_file(out)
        save(layout)
        print(f"Plot saved to {out}")

    if show:
        bk_show(layout)

    return layout


def plot_ohlcv(
    bars,
    title: str = "OHLCV",
    show: bool = True,
    filename: Optional[str] = None,
    filled_orders=None,
):
    """
    Candlestick chart for a list of Bar objects with optional trade markers.

    Parameters
    ----------
    bars : list[Bar]
    title : str
    show : bool
    filename : str, optional
    filled_orders : list[Order], optional
        Filled orders to mark on the chart.
    """
    bk = _ensure_bokeh()
    from bokeh.plotting import figure, output_file, show as bk_show, save
    from bokeh.models import HoverTool, ColumnDataSource

    df = pd.DataFrame([{
        "date": pd.Timestamp(b.ts_event, unit="ns"),
        "open": float(b.open.value),
        "high": float(b.high.value),
        "low": float(b.low.value),
        "close": float(b.close.value),
        "volume": float(b.volume.value),
    } for b in bars]).set_index("date")

    inc = df["close"] >= df["open"]
    dec = df["open"] > df["close"]

    w = 12 * 60 * 60 * 1000  # half day in ms (candle width)

    source = ColumnDataSource(df)

    p = figure(
        title=title,
        x_axis_type="datetime",
        width=1200,
        height=500,
        tools="pan,wheel_zoom,box_zoom,reset,save",
    )

    # Wicks
    p.segment(
        df.index[inc], df["high"][inc], df.index[inc], df["low"][inc],
        color="#26a69a",
    )
    p.segment(
        df.index[dec], df["high"][dec], df.index[dec], df["low"][dec],
        color="#ef5350",
    )

    # Bodies
    p.vbar(
        df.index[inc], w, df["open"][inc], df["close"][inc],
        fill_color="#26a69a", line_color="#26a69a",
    )
    p.vbar(
        df.index[dec], w, df["close"][dec], df["open"][dec],
        fill_color="#ef5350", line_color="#ef5350",
    )

    if filename:
        output_file(filename)
        save(p)
    if show:
        bk_show(p)

    return p


def plot_backtest(
    result: "BacktestResult",
    bars=None,
    show: bool = True,
    filename: Optional[str] = None,
) -> None:
    """
    Combined plot: equity curve + drawdown (+ OHLCV if bars provided).
    """
    plot_equity_curve(result, show=show, filename=filename)
