"""Strategy configuration base."""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional


@dataclass
class StrategyConfig:
    """
    Base configuration for all strategies.

    Subclass this and add your own parameters:

    >>> @dataclass
    ... class MyConfig(StrategyConfig):
    ...     fast_period: int = 10
    ...     slow_period: int = 30
    """
    strategy_id: Optional[str] = None
    order_id_tag: str = "001"
    manage_contingent_orders: bool = True
    close_positions_on_stop: bool = True
    oms_type: str = "HEDGING"  # "HEDGING" or "NETTING"

    def to_dict(self) -> dict:
        import dataclasses
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "StrategyConfig":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})
