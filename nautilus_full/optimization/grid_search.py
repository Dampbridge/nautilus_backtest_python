"""
Grid search parameter optimization.

Runs a backtest for every combination of parameter values and returns
a ranked DataFrame of results.

Usage
-----
>>> from nautilus_full.optimization.grid_search import GridSearch
>>> gs = GridSearch(
...     data=bars,
...     strategy_cls=MyStrategy,
...     param_grid={"fast_period": [5, 10, 20], "slow_period": [30, 50, 100]},
...     cash=100_000,
... )
>>> results_df = gs.run()
>>> print(results_df.sort_values("sharpe_ratio", ascending=False).head(10))
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass
from decimal import Decimal
from typing import Callable, Optional, Type

import pandas as pd

from nautilus_full.backtest.engine import BacktestEngine
from nautilus_full.backtest.results import BacktestResult
from nautilus_full.core.enums import AccountType, OmsType
from nautilus_full.core.objects import Currency, Money, USD
from nautilus_full.model.data import Bar
from nautilus_full.model.instruments.base import Instrument
from nautilus_full.trading.strategy import Strategy


class GridSearch:
    """
    Exhaustive parameter grid search.

    Parameters
    ----------
    data : list[Bar]
        Historical data.
    strategy_cls : type[Strategy]
        Strategy class to optimize. Must accept param_grid keys as constructor args
        or as StrategyConfig fields.
    param_grid : dict[str, list]
        Parameter name -> list of values to try.
    instrument : Instrument
        The instrument to trade.
    venue_name : str
        Venue identifier.
    cash : float
        Starting capital for each run.
    currency : Currency
        Account currency.
    commission : float
        Per-trade commission rate.
    metric : str | Callable
        The metric to optimize. Can be a BacktestResult attribute name
        (e.g. "sharpe_ratio") or a callable(result) -> float.
    n_jobs : int
        Number of parallel workers (1 = sequential).
    """

    def __init__(
        self,
        data: list[Bar],
        strategy_cls: Type[Strategy],
        param_grid: dict[str, list],
        instrument: Instrument,
        venue_name: str = "SIM",
        cash: float = 100_000.0,
        currency: Currency = USD,
        commission: float = 0.001,
        metric: str | Callable = "sharpe_ratio",
        n_jobs: int = 1,
    ) -> None:
        self._data = data
        self._strategy_cls = strategy_cls
        self._param_grid = param_grid
        self._instrument = instrument
        self._venue_name = venue_name
        self._cash = cash
        self._currency = currency
        self._commission = commission
        self._metric = metric
        self._n_jobs = n_jobs

    def run(self) -> pd.DataFrame:
        """
        Run the grid search.

        Returns
        -------
        pd.DataFrame
            One row per parameter combination, sorted by the target metric.
        """
        keys = list(self._param_grid.keys())
        values = list(self._param_grid.values())
        combinations = list(itertools.product(*values))

        print(f"Grid search: {len(combinations)} combinations × {len(self._data)} bars")

        records = []
        for i, combo in enumerate(combinations):
            params = dict(zip(keys, combo))
            result = self._run_single(params)
            row = dict(params)
            row.update({
                "total_return_pct": result.total_return_pct,
                "sharpe_ratio": result.sharpe_ratio,
                "sortino_ratio": result.sortino_ratio,
                "max_drawdown_pct": result.max_drawdown_pct,
                "win_rate_pct": result.win_rate * 100,
                "profit_factor": result.profit_factor,
                "total_trades": result.total_positions,
            })
            if callable(self._metric):
                row["metric"] = self._metric(result)
            records.append(row)

            if (i + 1) % 10 == 0:
                print(f"  {i+1}/{len(combinations)} done")

        df = pd.DataFrame(records)
        sort_col = "metric" if callable(self._metric) else self._metric
        if sort_col in df.columns:
            df = df.sort_values(sort_col, ascending=False)
        return df.reset_index(drop=True)

    def _run_single(self, params: dict) -> BacktestResult:
        from nautilus_full.venues.models import MakerTakerFeeModel, ZeroFeeModel

        engine = BacktestEngine()
        engine.add_venue(
            venue_name=self._venue_name,
            oms_type=OmsType.NETTING,
            account_type=AccountType.CASH,
            base_currency=self._currency,
            starting_balances=[Money(Decimal(str(self._cash)), self._currency)],
            fee_model=MakerTakerFeeModel() if self._commission > 0 else ZeroFeeModel(),
        )
        engine.add_instrument(self._instrument)
        engine.add_data(self._data)

        # Construct strategy with params
        try:
            from nautilus_full.trading.config import StrategyConfig
            import dataclasses
            strategy = self._strategy_cls(**params)
        except Exception:
            strategy = self._strategy_cls()

        engine.add_strategy(strategy)
        engine.run()
        return engine.get_result()

    def best_params(self, df: pd.DataFrame) -> dict:
        """Return the best parameter combination from the results DataFrame."""
        param_keys = list(self._param_grid.keys())
        return df.iloc[0][param_keys].to_dict()
