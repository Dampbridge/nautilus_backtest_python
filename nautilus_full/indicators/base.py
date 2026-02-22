"""Indicator abstract base class."""
from __future__ import annotations

from collections import deque
from decimal import Decimal
from typing import Optional

from nautilus_full.model.data import Bar


class Indicator:
    """
    Abstract base class for all indicators.

    Subclasses must implement:
      _update(value: Decimal) -> None
      value property

    The ``initialized`` flag becomes True once ``period`` observations
    have been received.
    """

    def __init__(self, period: int, name: Optional[str] = None) -> None:
        if period < 1:
            raise ValueError(f"period must be >= 1, got {period}")
        self.period = period
        self.name = name or type(self).__name__
        self._count = 0
        self._initialized = False
        self._inputs: deque[Decimal] = deque(maxlen=period)

    @property
    def initialized(self) -> bool:
        return self._initialized

    @property
    def count(self) -> int:
        return self._count

    def handle_bar(self, bar: Bar) -> None:
        """Called by Strategy._handle_bar() with each new bar."""
        self.update_raw(bar.close.value)

    def update_raw(self, value: Decimal) -> None:
        self._count += 1
        self._inputs.append(value)
        if not self._initialized and self._count >= self.period:
            self._initialized = True
        self._update(value)

    def _update(self, value: Decimal) -> None:
        """Subclasses implement this."""
        raise NotImplementedError

    @property
    def value(self) -> Optional[Decimal]:
        raise NotImplementedError

    def reset(self) -> None:
        self._count = 0
        self._initialized = False
        self._inputs.clear()

    def __repr__(self) -> str:
        return f"{self.name}(period={self.period}, value={self.value})"
