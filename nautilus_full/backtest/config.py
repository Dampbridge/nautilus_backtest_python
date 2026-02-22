"""Backtest configuration dataclasses."""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional


@dataclass
class VenueConfig:
    """Configuration for a simulated venue."""
    name: str
    oms_type: str = "HEDGING"           # "HEDGING" or "NETTING"
    account_type: str = "CASH"          # "CASH" or "MARGIN"
    base_currency: str = "USD"
    starting_balances: list[str] = field(default_factory=lambda: ["100000 USD"])
    default_leverage: float = 1.0
    book_spread_pct: float = 0.0001
    fill_model: Optional[str] = None    # "default", "slippage:{pct}"
    fee_model: Optional[str] = None     # "maker_taker", "zero", "fixed:{amount}"

    def parse_balances(self):
        """Parse balance strings like '100000 USD' into (Decimal, str) tuples."""
        result = []
        for b in self.starting_balances:
            parts = b.strip().split()
            if len(parts) == 2:
                result.append((Decimal(parts[0]), parts[1]))
        return result


@dataclass
class BacktestConfig:
    """
    Top-level backtest configuration.

    Parameters
    ----------
    trader_id : str
        Unique identifier for this backtest run.
    log_level : str
        Logging level (DEBUG, INFO, WARNING).
    bypass_logging : bool
        Suppress log output for performance.
    """
    trader_id: str = "BACKTESTER-001"
    log_level: str = "INFO"
    bypass_logging: bool = True
