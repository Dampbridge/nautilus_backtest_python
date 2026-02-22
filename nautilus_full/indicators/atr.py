"""Average True Range."""
from decimal import Decimal
from typing import Optional
from nautilus_full.indicators.base import Indicator
from nautilus_full.model.data import Bar


class AverageTrueRange(Indicator):
    """
    Wilder's smoothed ATR.

    TrueRange = max(High-Low, |High-PrevClose|, |Low-PrevClose|)
    ATR_t = (ATR_{t-1} * (period-1) + TR_t) / period   (Wilder smoothing)
    """

    def __init__(self, period: int) -> None:
        super().__init__(period, name=f"ATR({period})")
        self._prev_close: Optional[Decimal] = None
        self._value: Optional[Decimal] = None
        self._tr_sum: Decimal = Decimal("0")
        self._tr_count: int = 0

    def handle_bar(self, bar: Bar) -> None:
        high = bar.high.value
        low = bar.low.value
        close = bar.close.value

        if self._prev_close is None:
            tr = high - low
        else:
            tr = max(
                high - low,
                abs(high - self._prev_close),
                abs(low - self._prev_close),
            )

        self._prev_close = close
        self.update_raw(tr)

    def _update(self, value: Decimal) -> None:
        if self._count <= self.period:
            self._tr_sum += value
            self._tr_count += 1
            if self._initialized:
                self._value = self._tr_sum / Decimal(self.period)
        else:
            # Wilder smoothing
            if self._value is not None:
                self._value = (
                    self._value * Decimal(self.period - 1) + value
                ) / Decimal(self.period)

    @property
    def value(self) -> Optional[Decimal]:
        return self._value if self._initialized else None

    def reset(self) -> None:
        super().reset()
        self._prev_close = None
        self._value = None
        self._tr_sum = Decimal("0")
        self._tr_count = 0
