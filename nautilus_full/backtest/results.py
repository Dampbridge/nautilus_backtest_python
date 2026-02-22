"""
BacktestResult — immutable result container with pandas integration.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional

import pandas as pd


@dataclass
class BacktestResult:
    """
    Complete backtest result including performance statistics,
    equity curve, and trade-level data.
    """
    # Run metadata
    trader_id: str
    start_time_ns: int
    end_time_ns: int
    run_time_seconds: float = 0.0

    # Balance
    starting_balance: Decimal = Decimal("0")
    ending_balance: Decimal = Decimal("0")
    total_return: Decimal = Decimal("0")

    # Activity
    total_orders: int = 0
    total_positions: int = 0
    total_fills: int = 0
    total_commissions: Decimal = Decimal("0")

    # Performance
    total_return_pct: float = 0.0
    annualized_return_pct: float = 0.0
    annualized_volatility_pct: float = 0.0
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    calmar_ratio: float = 0.0

    # Drawdown
    max_drawdown_pct: float = 0.0
    max_drawdown_abs: float = 0.0

    # Trade stats
    win_rate: float = 0.0
    profit_factor: float = 0.0
    expectancy: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0

    # Curves (stored as lists for pickling)
    balance_curve: list[tuple[int, Decimal]] = field(default_factory=list)

    # Extra info
    extra: dict = field(default_factory=dict)

    # ── Pandas helpers ─────────────────────────────────────────────────────

    def equity_series(self) -> pd.Series:
        """Equity curve as a pandas Series indexed by datetime."""
        if not self.balance_curve:
            return pd.Series(dtype=float)
        ts = [pd.Timestamp(t, unit="ns") for t, _ in self.balance_curve]
        values = [float(e) for _, e in self.balance_curve]
        return pd.Series(values, index=ts, name="equity")

    def drawdown_series(self) -> pd.Series:
        """Drawdown series as a pandas Series."""
        equity = self.equity_series()
        if equity.empty:
            return pd.Series(dtype=float)
        rolling_max = equity.cummax()
        dd = (equity - rolling_max) / rolling_max.where(rolling_max != 0, other=1)
        return dd

    def summary(self) -> pd.Series:
        """All scalar statistics as a pandas Series."""
        data = {
            "trader_id": self.trader_id,
            "start": pd.Timestamp(self.start_time_ns, unit="ns"),
            "end": pd.Timestamp(self.end_time_ns, unit="ns"),
            "starting_balance": float(self.starting_balance),
            "ending_balance": float(self.ending_balance),
            "total_return_pct": self.total_return_pct,
            "annualized_return_pct": self.annualized_return_pct,
            "annualized_volatility_pct": self.annualized_volatility_pct,
            "sharpe_ratio": self.sharpe_ratio,
            "sortino_ratio": self.sortino_ratio,
            "calmar_ratio": self.calmar_ratio,
            "max_drawdown_pct": self.max_drawdown_pct,
            "max_drawdown_abs": self.max_drawdown_abs,
            "total_orders": self.total_orders,
            "total_positions": self.total_positions,
            "total_fills": self.total_fills,
            "total_commissions": float(self.total_commissions),
            "win_rate_pct": self.win_rate * 100,
            "profit_factor": self.profit_factor,
            "expectancy": self.expectancy,
            "avg_win": self.avg_win,
            "avg_loss": self.avg_loss,
        }
        return pd.Series(data)

    def __repr__(self) -> str:
        return (
            f"BacktestResult(\n"
            f"  return    = {self.total_return_pct:.2f}%\n"
            f"  sharpe    = {self.sharpe_ratio:.3f}\n"
            f"  sortino   = {self.sortino_ratio:.3f}\n"
            f"  max_dd    = {self.max_drawdown_pct:.2f}%\n"
            f"  win_rate  = {self.win_rate*100:.1f}%\n"
            f"  trades    = {self.total_positions}\n"
            f")"
        )
