"""Simple Moving Average."""
from decimal import Decimal
from collections import deque
from typing import Optional
from nautilus_full.indicators.base import Indicator


class SimpleMovingAverage(Indicator):
    """
    Arithmetic mean of the last ``period`` close prices.

    SMA_t = (P_{t} + P_{t-1} + ... + P_{t-period+1}) / period
    """

    def __init__(self, period: int) -> None:
        super().__init__(period, name=f"SMA({period})")
        self._sum = Decimal("0")
        self._window: deque[Decimal] = deque(maxlen=period)
        self._value: Optional[Decimal] = None

    def _update(self, value: Decimal) -> None:
        if len(self._window) == self.period:
            self._sum -= self._window[0]
        self._window.append(value)
        self._sum += value
        if self._initialized:
            self._value = self._sum / Decimal(self.period)

    @property
    def value(self) -> Optional[Decimal]:
        return self._value

    def reset(self) -> None:
        super().reset()
        self._sum = Decimal("0")
        self._window.clear()
        self._value = None
