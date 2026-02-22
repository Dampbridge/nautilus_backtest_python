"""
Typed identifier wrappers.

All identifiers are thin str wrappers so they are hashable, comparable, and
printable while remaining distinct types in type-checking.
"""
from __future__ import annotations


class _Id(str):
    """Base for all identifier types."""
    __slots__ = ()

    def __new__(cls, value: str) -> "_Id":
        if not value or not value.strip():
            raise ValueError(f"{cls.__name__} value cannot be empty")
        return super().__new__(cls, value)

    def __repr__(self) -> str:
        return f"{type(self).__name__}('{self}')"


class TraderId(_Id):
    """Unique identifier for a trader instance."""
    __slots__ = ()


class StrategyId(_Id):
    """Unique identifier for a strategy."""
    __slots__ = ()


class ActorId(_Id):
    """Unique identifier for an actor component."""
    __slots__ = ()


class Venue(_Id):
    """Exchange / venue identifier."""
    __slots__ = ()

    @property
    def value(self) -> str:
        return str(self)


class InstrumentId:
    """
    Composite identifier: ``{symbol}.{venue}``.

    Examples
    --------
    >>> InstrumentId.from_str("BTCUSDT.BINANCE")
    InstrumentId('BTCUSDT.BINANCE')
    """
    __slots__ = ("symbol", "venue", "_str")

    def __init__(self, symbol: str, venue: Venue | str) -> None:
        self.symbol = symbol
        self.venue = Venue(str(venue)) if not isinstance(venue, Venue) else venue
        self._str = f"{symbol}.{self.venue}"

    @classmethod
    def from_str(cls, value: str) -> "InstrumentId":
        parts = value.rsplit(".", 1)
        if len(parts) != 2:
            raise ValueError(f"Invalid InstrumentId format: '{value}' (expected 'SYMBOL.VENUE')")
        return cls(symbol=parts[0], venue=Venue(parts[1]))

    def __str__(self) -> str:
        return self._str

    def __repr__(self) -> str:
        return f"InstrumentId('{self._str}')"

    def __hash__(self) -> int:
        return hash(self._str)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, InstrumentId):
            return self._str == other._str
        return NotImplemented

    def __lt__(self, other: "InstrumentId") -> bool:
        return self._str < other._str


class ClientOrderId(_Id):
    """Client-side order identifier (assigned by the strategy/trader)."""
    __slots__ = ()


class VenueOrderId(_Id):
    """Venue-side order identifier (assigned by the exchange)."""
    __slots__ = ()


class TradeId(_Id):
    """Unique identifier for an individual trade/fill."""
    __slots__ = ()


class PositionId(_Id):
    """Unique identifier for a position."""
    __slots__ = ()


class AccountId(_Id):
    """Unique identifier for an account."""
    __slots__ = ()


class OrderListId(_Id):
    """Unique identifier for a contingency order list (OCO, OTO, etc.)."""
    __slots__ = ()


class ClientId(_Id):
    """Unique identifier for a data/execution client."""
    __slots__ = ()


class ComponentId(_Id):
    """Unique identifier for a framework component."""
    __slots__ = ()
