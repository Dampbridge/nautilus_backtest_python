"""Exponential Moving Average."""
from decimal import Decimal
from typing import Optional
from nautilus_full.indicators.base import Indicator


class ExponentialMovingAverage(Indicator):
    """
    Exponentially-weighted moving average.

    EMA_t = alpha * P_t + (1 - alpha) * EMA_{t-1}
    where alpha = 2 / (period + 1)
    """

    def __init__(self, period: int) -> None:
        super().__init__(period, name=f"EMA({period})")
        self._alpha = Decimal(2) / Decimal(period + 1)
        self._value: Optional[Decimal] = None

    def _update(self, value: Decimal) -> None:
        if self._value is None:
            # Seed with SMA over first ``period`` values
            if self._count <= self.period:
                self._value = (
                    sum(self._inputs, Decimal("0")) / Decimal(len(self._inputs))
                )
        else:
            self._value = self._alpha * value + (1 - self._alpha) * self._value

    @property
    def value(self) -> Optional[Decimal]:
        return self._value if self._initialized else None

    def reset(self) -> None:
        super().reset()
        self._value = None
