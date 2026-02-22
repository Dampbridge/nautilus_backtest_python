"""HTML report generator for backtest results."""
from __future__ import annotations

from pathlib import Path
from typing import Optional, TYPE_CHECKING

import pandas as pd

if TYPE_CHECKING:
    from nautilus_full.backtest.results import BacktestResult


_HTML_TEMPLATE = """<!DOCTYPE html>
<html>
<head>
<title>Backtest Report — {trader_id}</title>
<style>
  body {{ font-family: 'Segoe UI', sans-serif; max-width: 1100px; margin: 40px auto; color: #333; }}
  h1 {{ color: #1a237e; border-bottom: 2px solid #3f51b5; padding-bottom: 8px; }}
  h2 {{ color: #283593; margin-top: 32px; }}
  table {{ border-collapse: collapse; width: 100%; margin-bottom: 24px; }}
  th {{ background: #3f51b5; color: white; padding: 10px 16px; text-align: left; }}
  td {{ padding: 8px 16px; border-bottom: 1px solid #e0e0e0; }}
  tr:nth-child(even) {{ background: #f5f5f5; }}
  .pos {{ color: #2e7d32; font-weight: bold; }}
  .neg {{ color: #c62828; font-weight: bold; }}
  .metric {{ font-size: 1.1em; }}
</style>
</head>
<body>
<h1>Backtest Report</h1>
<p><b>Trader ID:</b> {trader_id} &nbsp;|&nbsp;
   <b>Period:</b> {start} — {end} &nbsp;|&nbsp;
   <b>Run time:</b> {run_time:.2f}s</p>

<h2>Performance Summary</h2>
<table>
<tr><th>Metric</th><th>Value</th></tr>
{summary_rows}
</table>

<h2>Equity Curve Data</h2>
<p>Use <code>result.equity_series()</code> to get a pandas Series for plotting.</p>

</body>
</html>
"""


def generate_html_report(
    result: "BacktestResult",
    output_path: Optional[str | Path] = None,
) -> str:
    """
    Generate an HTML report from a BacktestResult.

    Parameters
    ----------
    result : BacktestResult
    output_path : str | Path, optional
        Where to save the HTML file. If None, returns the HTML string.

    Returns
    -------
    str
        The HTML report as a string.
    """
    summary = result.summary()

    def _fmt(key, val) -> str:
        pct_keys = {"total_return_pct", "annualized_return_pct", "annualized_volatility_pct",
                    "max_drawdown_pct", "win_rate_pct"}
        if key in pct_keys:
            css = "pos" if float(val) >= 0 else "neg"
            return f'<td class="{css}">{float(val):.2f}%</td>'
        elif isinstance(val, float):
            return f"<td>{val:.4f}</td>"
        else:
            return f"<td>{val}</td>"

    rows = []
    labels = {
        "starting_balance": "Starting Balance",
        "ending_balance": "Ending Balance",
        "total_return_pct": "Total Return",
        "annualized_return_pct": "Annualized Return",
        "annualized_volatility_pct": "Annualized Volatility",
        "sharpe_ratio": "Sharpe Ratio",
        "sortino_ratio": "Sortino Ratio",
        "calmar_ratio": "Calmar Ratio",
        "max_drawdown_pct": "Max Drawdown",
        "max_drawdown_abs": "Max Drawdown (abs)",
        "total_orders": "Total Orders",
        "total_positions": "Total Trades",
        "total_fills": "Total Fills",
        "total_commissions": "Total Commissions",
        "win_rate_pct": "Win Rate",
        "profit_factor": "Profit Factor",
        "expectancy": "Expectancy",
        "avg_win": "Avg Win",
        "avg_loss": "Avg Loss",
    }
    for key, label in labels.items():
        val = summary.get(key, "N/A")
        rows.append(f"<tr><td><b>{label}</b></td>{_fmt(key, val)}</tr>")

    start_ts = pd.Timestamp(result.start_time_ns, unit="ns")
    end_ts = pd.Timestamp(result.end_time_ns, unit="ns")

    html = _HTML_TEMPLATE.format(
        trader_id=result.trader_id,
        start=start_ts.strftime("%Y-%m-%d"),
        end=end_ts.strftime("%Y-%m-%d"),
        run_time=result.run_time_seconds,
        summary_rows="\n".join(rows),
    )

    if output_path:
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(html, encoding="utf-8")
        print(f"Report saved to {out}")

    return html
