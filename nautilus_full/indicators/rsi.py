"""Relative Strength Index."""
from decimal import Decimal
from typing import Optional
from nautilus_full.indicators.base import Indicator


class RelativeStrengthIndex(Indicator):
    """
    Wilder's RSI.

    RSI = 100 - 100/(1 + RS)  where RS = avg_gain / avg_loss
    """

    def __init__(self, period: int) -> None:
        super().__init__(period, name=f"RSI({period})")
        self._prev_close: Optional[Decimal] = None
        self._avg_gain: Optional[Decimal] = None
        self._avg_loss: Optional[Decimal] = None
        self._value: Optional[Decimal] = None

    def _update(self, value: Decimal) -> None:
        if self._prev_close is None:
            self._prev_close = value
            return

        delta = value - self._prev_close
        gain = max(delta, Decimal("0"))
        loss = max(-delta, Decimal("0"))
        self._prev_close = value

        if self._count <= self.period:
            # Build initial averages as simple means
            if self._avg_gain is None:
                self._avg_gain = gain
                self._avg_loss = loss
            else:
                self._avg_gain = self._avg_gain + gain
                self._avg_loss = self._avg_loss + loss
            if self._initialized:
                self._avg_gain = self._avg_gain / Decimal(self.period)
                self._avg_loss = self._avg_loss / Decimal(self.period)
        else:
            # Wilder smoothing
            self._avg_gain = (
                self._avg_gain * Decimal(self.period - 1) + gain
            ) / Decimal(self.period)
            self._avg_loss = (
                self._avg_loss * Decimal(self.period - 1) + loss
            ) / Decimal(self.period)

        if self._initialized and self._avg_loss is not None:
            if self._avg_loss == 0:
                self._value = Decimal("100")
            else:
                rs = self._avg_gain / self._avg_loss
                self._value = Decimal("100") - Decimal("100") / (1 + rs)

    @property
    def value(self) -> Optional[Decimal]:
        return self._value if self._initialized else None

    @property
    def is_overbought(self) -> bool:
        return self._value is not None and self._value >= Decimal("70")

    @property
    def is_oversold(self) -> bool:
        return self._value is not None and self._value <= Decimal("30")

    def reset(self) -> None:
        super().reset()
        self._prev_close = None
        self._avg_gain = None
        self._avg_loss = None
        self._value = None
