"""Bollinger Bands."""
from decimal import Decimal
from collections import deque
from typing import Optional
from nautilus_full.indicators.base import Indicator


class BollingerBands(Indicator):
    """
    Bollinger Bands: middle = SMA(period), upper/lower = middle ± k*stddev.

    Parameters
    ----------
    period : int
        Look-back period.
    k : float
        Number of standard deviations for the bands (default 2.0).
    """

    def __init__(self, period: int, k: float = 2.0) -> None:
        super().__init__(period, name=f"BBands({period},{k})")
        self.k = Decimal(str(k))
        self._window: deque[Decimal] = deque(maxlen=period)
        self._upper: Optional[Decimal] = None
        self._middle: Optional[Decimal] = None
        self._lower: Optional[Decimal] = None

    def _update(self, value: Decimal) -> None:
        self._window.append(value)
        if self._initialized:
            n = Decimal(self.period)
            mean = sum(self._window, Decimal("0")) / n
            variance = sum((x - mean) ** 2 for x in self._window) / n
            std = variance.sqrt()
            self._middle = mean
            self._upper = mean + self.k * std
            self._lower = mean - self.k * std

    @property
    def value(self) -> Optional[Decimal]:
        return self._middle

    @property
    def upper(self) -> Optional[Decimal]:
        return self._upper

    @property
    def middle(self) -> Optional[Decimal]:
        return self._middle

    @property
    def lower(self) -> Optional[Decimal]:
        return self._lower

    @property
    def bandwidth(self) -> Optional[Decimal]:
        if self._upper and self._lower and self._middle and self._middle != 0:
            return (self._upper - self._lower) / self._middle
        return None

    @property
    def percent_b(self) -> Optional[Decimal]:
        """Position of price within the bands: 0=lower, 1=upper."""
        if self._inputs and self._upper and self._lower:
            price = self._inputs[-1]
            band_width = self._upper - self._lower
            if band_width == 0:
                return Decimal("0.5")
            return (price - self._lower) / band_width
        return None

    def reset(self) -> None:
        super().reset()
        self._window.clear()
        self._upper = self._middle = self._lower = None
