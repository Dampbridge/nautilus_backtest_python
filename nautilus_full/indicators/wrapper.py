"""
IndicatorWrapper — wraps any callable as an indicator.

Usage inside a strategy::

    def on_start(self):
        self.roc = self.I(
            lambda closes: (closes[-1] / closes[-10] - 1) * 100,
            period=10,
            name="ROC(10)"
        )
        self.register_indicator_for_bars(self.bar_type, self.roc)
"""
from __future__ import annotations

from collections import deque
from decimal import Decimal
from typing import Callable, Optional

from nautilus_full.indicators.base import Indicator
from nautilus_full.model.data import Bar


class IndicatorWrapper(Indicator):
    """
    Wraps an arbitrary function ``func(window: list[Decimal]) -> Decimal``
    as an Indicator.

    Parameters
    ----------
    func : Callable[[list[Decimal]], Decimal]
        Function that takes the rolling window of close prices and returns
        the indicator value.
    period : int
        Window size; the indicator is initialized once ``period`` bars arrive.
    name : str, optional
        Display name.
    price_getter : Callable[[Bar], Decimal], optional
        How to extract price from a bar. Defaults to bar.close.value.
    """

    def __init__(
        self,
        func: Callable[[list[Decimal]], Decimal],
        period: int,
        name: Optional[str] = None,
        price_getter: Optional[Callable[[Bar], Decimal]] = None,
    ) -> None:
        super().__init__(period, name=name or f"I({func.__name__}, {period})")
        self._func = func
        self._price_getter = price_getter or (lambda bar: bar.close.value)
        self._window: deque[Decimal] = deque(maxlen=period)
        self._value: Optional[Decimal] = None

    def handle_bar(self, bar: Bar) -> None:
        px = self._price_getter(bar)
        self._window.append(px)
        self._count += 1
        if not self._initialized and self._count >= self.period:
            self._initialized = True
        self._update(px)

    def _update(self, value: Decimal) -> None:
        if self._initialized:
            try:
                result = self._func(list(self._window))
                self._value = Decimal(str(result))
            except Exception:
                self._value = None

    @property
    def value(self) -> Optional[Decimal]:
        return self._value

    def reset(self) -> None:
        super().reset()
        self._window.clear()
        self._value = None


def I(
    func: Callable,
    period: int,
    name: Optional[str] = None,
    price_getter: Optional[Callable[[Bar], Decimal]] = None,
) -> IndicatorWrapper:
    """
    Convenience factory for creating an IndicatorWrapper.

    >>> roc = I(lambda w: (w[-1] / w[-10] - 1) * 100, period=10, name="ROC")
    """
    return IndicatorWrapper(func, period, name=name, price_getter=price_getter)
