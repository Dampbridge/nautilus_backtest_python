"""
Performance statistics computation.

Takes an equity curve (list of (ts_ns, equity)) or a BacktestResult and
computes comprehensive performance metrics using numpy/pandas.
"""
from __future__ import annotations

import math
from decimal import Decimal
from typing import Optional, TYPE_CHECKING

import numpy as np
import pandas as pd

if TYPE_CHECKING:
    from nautilus_full.model.position import Position


def compute_returns(equity_curve: list[tuple[int, Decimal]]) -> pd.Series:
    """
    Compute period returns from an equity curve.

    Parameters
    ----------
    equity_curve : list of (ts_ns, equity)

    Returns
    -------
    pd.Series of float returns indexed by Timestamp.
    """
    if len(equity_curve) < 2:
        return pd.Series(dtype=float)
    ts = [pd.Timestamp(t, unit="ns") for t, _ in equity_curve]
    equity = [float(e) for _, e in equity_curve]
    s = pd.Series(equity, index=ts)
    returns = s.pct_change().dropna()
    return returns


def sharpe_ratio(
    returns: pd.Series,
    risk_free_rate: float = 0.0,
    periods_per_year: int = 252,
) -> float:
    """Annualized Sharpe ratio."""
    if returns.empty or returns.std() == 0:
        return 0.0
    excess = returns - risk_free_rate / periods_per_year
    return float((excess.mean() / excess.std()) * math.sqrt(periods_per_year))


def sortino_ratio(
    returns: pd.Series,
    risk_free_rate: float = 0.0,
    periods_per_year: int = 252,
) -> float:
    """Annualized Sortino ratio (penalizes only downside volatility)."""
    if returns.empty:
        return 0.0
    excess = returns - risk_free_rate / periods_per_year
    downside = excess[excess < 0]
    if downside.empty or downside.std() == 0:
        return 0.0 if excess.mean() <= 0 else float("inf")
    return float((excess.mean() / downside.std()) * math.sqrt(periods_per_year))


def calmar_ratio(
    returns: pd.Series,
    equity_curve: list[tuple[int, Decimal]],
    periods_per_year: int = 252,
) -> float:
    """Calmar ratio = annualized return / max drawdown."""
    ann_ret = annualized_return(returns, periods_per_year)
    mdd = max_drawdown_pct(equity_curve)
    return float(ann_ret / mdd) if mdd != 0 else 0.0


def annualized_return(returns: pd.Series, periods_per_year: int = 252) -> float:
    """Geometric annualized return."""
    if returns.empty:
        return 0.0
    n = len(returns)
    total = (1 + returns).prod()
    return float(total ** (periods_per_year / n) - 1)


def annualized_volatility(returns: pd.Series, periods_per_year: int = 252) -> float:
    """Annualized standard deviation of returns."""
    if returns.empty:
        return 0.0
    return float(returns.std() * math.sqrt(periods_per_year))


def max_drawdown_pct(equity_curve: list[tuple[int, Decimal]]) -> float:
    """Maximum drawdown as a fraction of peak equity."""
    if not equity_curve:
        return 0.0
    equity = [float(e) for _, e in equity_curve]
    peak = equity[0]
    max_dd = 0.0
    for e in equity:
        if e > peak:
            peak = e
        if peak > 0:
            dd = (peak - e) / peak
            max_dd = max(max_dd, dd)
    return max_dd


def max_drawdown_abs(equity_curve: list[tuple[int, Decimal]]) -> float:
    """Maximum drawdown in absolute dollar terms."""
    if not equity_curve:
        return 0.0
    equity = [float(e) for _, e in equity_curve]
    peak = equity[0]
    max_dd = 0.0
    for e in equity:
        if e > peak:
            peak = e
        dd = peak - e
        max_dd = max(max_dd, dd)
    return max_dd


def drawdown_series(equity_curve: list[tuple[int, Decimal]]) -> pd.Series:
    """Full drawdown series as a pandas Series indexed by Timestamp."""
    if not equity_curve:
        return pd.Series(dtype=float)
    ts = [pd.Timestamp(t, unit="ns") for t, _ in equity_curve]
    equity = pd.Series([float(e) for _, e in equity_curve], index=ts)
    rolling_max = equity.cummax()
    dd = (equity - rolling_max) / rolling_max.where(rolling_max != 0, other=1)
    return dd


def win_rate(positions: list["Position"]) -> float:
    """Fraction of closed positions that were profitable."""
    closed = [p for p in positions if p.is_closed]
    if not closed:
        return 0.0
    wins = sum(1 for p in closed if p.realized_pnl > 0)
    return wins / len(closed)


def profit_factor(positions: list["Position"]) -> float:
    """Gross profit / gross loss."""
    closed = [p for p in positions if p.is_closed]
    gross_profit = sum(float(p.realized_pnl) for p in closed if p.realized_pnl > 0)
    gross_loss = abs(sum(float(p.realized_pnl) for p in closed if p.realized_pnl < 0))
    return gross_profit / gross_loss if gross_loss > 0 else 0.0


def avg_win_loss(positions: list["Position"]) -> tuple[float, float]:
    """Average win and average loss (absolute value)."""
    closed = [p for p in positions if p.is_closed]
    wins = [float(p.realized_pnl) for p in closed if p.realized_pnl > 0]
    losses = [float(p.realized_pnl) for p in closed if p.realized_pnl < 0]
    avg_win = sum(wins) / len(wins) if wins else 0.0
    avg_loss = abs(sum(losses) / len(losses)) if losses else 0.0
    return avg_win, avg_loss


def expectancy(positions: list["Position"]) -> float:
    """
    Expected value per trade.

    expectancy = win_rate * avg_win - (1 - win_rate) * avg_loss
    """
    wr = win_rate(positions)
    aw, al = avg_win_loss(positions)
    return wr * aw - (1 - wr) * al


def compute_all_stats(
    equity_curve: list[tuple[int, Decimal]],
    positions: list["Position"],
    starting_balance: Decimal,
    ending_balance: Decimal,
    risk_free_rate: float = 0.0,
    periods_per_year: int = 252,
) -> dict:
    """
    Compute the full suite of performance statistics.

    Returns a dict with all key metrics.
    """
    returns = compute_returns(equity_curve)

    total_return_pct = (
        float((ending_balance - starting_balance) / starting_balance * 100)
        if starting_balance != 0 else 0.0
    )

    stats = {
        # Returns
        "total_return_pct": total_return_pct,
        "annualized_return_pct": annualized_return(returns, periods_per_year) * 100,
        "annualized_volatility_pct": annualized_volatility(returns, periods_per_year) * 100,
        # Risk-adjusted
        "sharpe_ratio": sharpe_ratio(returns, risk_free_rate, periods_per_year),
        "sortino_ratio": sortino_ratio(returns, risk_free_rate, periods_per_year),
        "calmar_ratio": calmar_ratio(returns, equity_curve, periods_per_year),
        # Drawdown
        "max_drawdown_pct": max_drawdown_pct(equity_curve) * 100,
        "max_drawdown_abs": max_drawdown_abs(equity_curve),
        # Trade stats
        "total_trades": len([p for p in positions if p.is_closed]),
        "win_rate_pct": win_rate(positions) * 100,
        "profit_factor": profit_factor(positions),
        "expectancy": expectancy(positions),
        "avg_win": avg_win_loss(positions)[0],
        "avg_loss": avg_win_loss(positions)[1],
        # Balance
        "starting_balance": float(starting_balance),
        "ending_balance": float(ending_balance),
        "total_commissions": float(sum(p.commissions for p in positions)),
    }
    return stats
