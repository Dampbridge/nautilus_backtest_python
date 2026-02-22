"""MACD (Moving Average Convergence Divergence)."""
from decimal import Decimal
from typing import Optional
from nautilus_full.indicators.base import Indicator
from nautilus_full.indicators.ema import ExponentialMovingAverage


class MACD(Indicator):
    """
    MACD = EMA(fast) - EMA(slow)
    Signal = EMA(MACD, signal_period)
    Histogram = MACD - Signal
    """

    def __init__(
        self,
        fast_period: int = 12,
        slow_period: int = 26,
        signal_period: int = 9,
    ) -> None:
        super().__init__(slow_period, name=f"MACD({fast_period},{slow_period},{signal_period})")
        self._fast = ExponentialMovingAverage(fast_period)
        self._slow = ExponentialMovingAverage(slow_period)
        self._signal_ema = ExponentialMovingAverage(signal_period)
        self._signal_period = signal_period
        self._macd_val: Optional[Decimal] = None
        self._signal_val: Optional[Decimal] = None
        self._hist_val: Optional[Decimal] = None

    def _update(self, value: Decimal) -> None:
        self._fast.update_raw(value)
        self._slow.update_raw(value)

        if self._fast.initialized and self._slow.initialized:
            macd = self._fast.value - self._slow.value
            self._macd_val = macd
            self._signal_ema.update_raw(macd)
            if self._signal_ema.initialized:
                self._signal_val = self._signal_ema.value
                self._hist_val = macd - self._signal_val

    @property
    def initialized(self) -> bool:
        return self._signal_ema.initialized

    @property
    def value(self) -> Optional[Decimal]:
        return self._macd_val

    @property
    def macd(self) -> Optional[Decimal]:
        return self._macd_val

    @property
    def signal(self) -> Optional[Decimal]:
        return self._signal_val

    @property
    def histogram(self) -> Optional[Decimal]:
        return self._hist_val

    def reset(self) -> None:
        super().reset()
        self._fast.reset()
        self._slow.reset()
        self._signal_ema.reset()
        self._macd_val = self._signal_val = self._hist_val = None
