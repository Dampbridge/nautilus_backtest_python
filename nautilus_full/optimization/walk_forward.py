"""
Walk-forward analysis.

Splits data into sequential in-sample (IS) and out-of-sample (OOS) windows,
optimizes on IS, then tests on OOS. Provides a realistic estimate of live
performance.

Window types:
  - Rolling (anchored start): each IS window uses all data from start to IS_end
  - Expanding: the IS start advances with each fold (fixed window size)

Usage
-----
>>> wfa = WalkForwardAnalyzer(
...     data=bars,
...     strategy_cls=MyStrategy,
...     param_grid={"fast": [5, 10], "slow": [20, 50]},
...     instrument=instr,
...     is_periods=252,    # 1 year in-sample
...     oos_periods=63,    # 1 quarter out-of-sample
...     expanding=False,   # rolling window
... )
>>> summary = wfa.run()
>>> print(summary)
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Callable, Optional, Type

import pandas as pd

from nautilus_full.backtest.results import BacktestResult
from nautilus_full.model.data import Bar
from nautilus_full.model.instruments.base import Instrument
from nautilus_full.optimization.grid_search import GridSearch
from nautilus_full.trading.strategy import Strategy


@dataclass
class WalkForwardFold:
    fold: int
    is_start_idx: int
    is_end_idx: int
    oos_start_idx: int
    oos_end_idx: int
    best_params: dict
    is_result: BacktestResult
    oos_result: BacktestResult


@dataclass
class WalkForwardSummary:
    folds: list[WalkForwardFold]

    def to_dataframe(self) -> pd.DataFrame:
        rows = []
        for fold in self.folds:
            row = {
                "fold": fold.fold,
                **{f"param_{k}": v for k, v in fold.best_params.items()},
                "is_sharpe": fold.is_result.sharpe_ratio,
                "is_return_pct": fold.is_result.total_return_pct,
                "oos_sharpe": fold.oos_result.sharpe_ratio,
                "oos_return_pct": fold.oos_result.total_return_pct,
                "oos_max_dd_pct": fold.oos_result.max_drawdown_pct,
                "oos_win_rate_pct": fold.oos_result.win_rate * 100,
            }
            rows.append(row)
        return pd.DataFrame(rows)

    def oos_equity_curve(self) -> list[tuple]:
        """Concatenated out-of-sample equity curve across all folds."""
        result = []
        for fold in self.folds:
            result.extend(fold.oos_result.balance_curve)
        return sorted(result, key=lambda x: x[0])

    def avg_oos_sharpe(self) -> float:
        return sum(f.oos_result.sharpe_ratio for f in self.folds) / len(self.folds)

    def avg_oos_return_pct(self) -> float:
        return sum(f.oos_result.total_return_pct for f in self.folds) / len(self.folds)


class WalkForwardAnalyzer:
    """
    Walk-forward optimization and validation.

    Parameters
    ----------
    data : list[Bar]
        Full historical data sorted by time.
    strategy_cls : type[Strategy]
        Strategy class.
    param_grid : dict[str, list]
        Parameter search space.
    instrument : Instrument
        The instrument to trade.
    is_periods : int
        Number of bars in each in-sample window.
    oos_periods : int
        Number of bars in each out-of-sample window.
    expanding : bool
        If False (rolling), the IS window has fixed length.
        If True (expanding), IS window grows with each fold.
    metric : str
        Metric to optimize on IS data.
    cash : float
        Starting capital.
    commission : float
        Commission rate.
    """

    def __init__(
        self,
        data: list[Bar],
        strategy_cls: Type[Strategy],
        param_grid: dict[str, list],
        instrument: Instrument,
        is_periods: int = 252,
        oos_periods: int = 63,
        expanding: bool = False,
        metric: str = "sharpe_ratio",
        cash: float = 100_000.0,
        commission: float = 0.001,
    ) -> None:
        self._data = sorted(data, key=lambda b: b.ts_event)
        self._strategy_cls = strategy_cls
        self._param_grid = param_grid
        self._instrument = instrument
        self._is_periods = is_periods
        self._oos_periods = oos_periods
        self._expanding = expanding
        self._metric = metric
        self._cash = cash
        self._commission = commission

    def run(self) -> WalkForwardSummary:
        """Run the full walk-forward analysis."""
        n = len(self._data)
        folds = []
        fold_num = 0
        oos_start = self._is_periods

        while oos_start + self._oos_periods <= n:
            fold_num += 1
            oos_end = oos_start + self._oos_periods

            if self._expanding:
                is_start = 0
            else:
                is_start = max(0, oos_start - self._is_periods)
            is_end = oos_start

            is_data = self._data[is_start:is_end]
            oos_data = self._data[oos_start:oos_end]

            print(f"\n=== Fold {fold_num} ===")
            print(f"  IS:  bars {is_start}–{is_end-1} ({len(is_data)} bars)")
            print(f"  OOS: bars {oos_start}–{oos_end-1} ({len(oos_data)} bars)")

            # Optimize on IS
            gs = GridSearch(
                data=is_data,
                strategy_cls=self._strategy_cls,
                param_grid=self._param_grid,
                instrument=self._instrument,
                cash=self._cash,
                commission=self._commission,
                metric=self._metric,
            )
            results_df = gs.run()
            best_params = gs.best_params(results_df)
            is_result = gs._run_single(best_params)

            print(f"  Best IS params: {best_params}")
            print(f"  IS Sharpe: {is_result.sharpe_ratio:.3f}")

            # Validate on OOS
            oos_result = gs._run_single(best_params)  # using oos_data would need re-init
            # Re-run on OOS data
            oos_gs = GridSearch(
                data=oos_data,
                strategy_cls=self._strategy_cls,
                param_grid={k: [v] for k, v in best_params.items()},
                instrument=self._instrument,
                cash=self._cash,
                commission=self._commission,
            )
            oos_result = oos_gs._run_single(best_params)

            print(f"  OOS Sharpe: {oos_result.sharpe_ratio:.3f}, Return: {oos_result.total_return_pct:.2f}%")

            folds.append(WalkForwardFold(
                fold=fold_num,
                is_start_idx=is_start,
                is_end_idx=is_end,
                oos_start_idx=oos_start,
                oos_end_idx=oos_end,
                best_params=best_params,
                is_result=is_result,
                oos_result=oos_result,
            ))

            oos_start += self._oos_periods

        summary = WalkForwardSummary(folds=folds)
        print(f"\n=== Walk-Forward Summary ===")
        print(f"  Folds:           {len(folds)}")
        print(f"  Avg OOS Sharpe:  {summary.avg_oos_sharpe():.3f}")
        print(f"  Avg OOS Return:  {summary.avg_oos_return_pct():.2f}%")
        return summary
