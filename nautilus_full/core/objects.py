"""
Core value objects: Price, Quantity, Money, Currency, AccountBalance.

All monetary values use Python Decimal for exact arithmetic — never float.
"""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from typing import Optional

from nautilus_full.core.enums import CurrencyType


# ── Currency ──────────────────────────────────────────────────────────────────

class Currency:
    """
    Immutable currency descriptor.

    Parameters
    ----------
    code : str
        ISO 4217 code (e.g. "USD") or crypto ticker (e.g. "BTC").
    precision : int
        Decimal places for amounts in this currency.
    currency_type : CurrencyType
        FIAT, CRYPTO, or COMMODITY.
    """
    __slots__ = ("code", "precision", "currency_type")

    # Registry of well-known currencies
    _registry: dict[str, "Currency"] = {}

    def __init__(self, code: str, precision: int, currency_type: CurrencyType) -> None:
        self.code = code.upper()
        self.precision = precision
        self.currency_type = currency_type

    @classmethod
    def from_str(cls, code: str) -> "Currency":
        code = code.upper()
        if code in cls._registry:
            return cls._registry[code]
        raise ValueError(f"Unknown currency: '{code}'. Register it first or use Currency() directly.")

    def __str__(self) -> str:
        return self.code

    def __repr__(self) -> str:
        return f"Currency(code='{self.code}', precision={self.precision}, type={self.currency_type.name})"

    def __hash__(self) -> int:
        return hash(self.code)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Currency):
            return self.code == other.code
        return NotImplemented


def _register_currency(code: str, precision: int, ctype: CurrencyType) -> Currency:
    c = Currency(code, precision, ctype)
    Currency._registry[code] = c
    return c


# Well-known currencies
USD = _register_currency("USD", 2, CurrencyType.FIAT)
EUR = _register_currency("EUR", 2, CurrencyType.FIAT)
GBP = _register_currency("GBP", 2, CurrencyType.FIAT)
JPY = _register_currency("JPY", 0, CurrencyType.FIAT)
CHF = _register_currency("CHF", 2, CurrencyType.FIAT)
CAD = _register_currency("CAD", 2, CurrencyType.FIAT)
AUD = _register_currency("AUD", 2, CurrencyType.FIAT)
HKD = _register_currency("HKD", 2, CurrencyType.FIAT)
BTC = _register_currency("BTC", 8, CurrencyType.CRYPTO)
ETH = _register_currency("ETH", 8, CurrencyType.CRYPTO)
USDT = _register_currency("USDT", 2, CurrencyType.CRYPTO)
USDC = _register_currency("USDC", 2, CurrencyType.CRYPTO)
BNB = _register_currency("BNB", 8, CurrencyType.CRYPTO)
SOL = _register_currency("SOL", 8, CurrencyType.CRYPTO)
XAU = _register_currency("XAU", 3, CurrencyType.COMMODITY)  # Gold


# ── Price ─────────────────────────────────────────────────────────────────────

class Price:
    """
    Immutable price value with fixed decimal precision.

    Parameters
    ----------
    value : Decimal | str | int | float
        The price value.
    precision : int
        Number of decimal places to store.
    """
    __slots__ = ("value", "precision", "_quantizer")

    def __init__(self, value: Decimal | str | int | float, precision: int) -> None:
        self.precision = precision
        q = Decimal(10) ** -precision
        self._quantizer = q
        try:
            self.value = Decimal(str(value)).quantize(q, rounding=ROUND_HALF_UP)
        except InvalidOperation as exc:
            raise ValueError(f"Cannot create Price from {value!r}") from exc

    @classmethod
    def from_raw(cls, raw: int, precision: int) -> "Price":
        """Create from raw integer (nanosecond-style int * 10^precision)."""
        value = Decimal(raw) / Decimal(10 ** precision)
        return cls(value, precision)

    def as_decimal(self) -> Decimal:
        return self.value

    def as_double(self) -> float:
        return float(self.value)

    def __add__(self, other: "Price | Decimal | int") -> "Price":
        if isinstance(other, Price):
            return Price(self.value + other.value, max(self.precision, other.precision))
        return Price(self.value + Decimal(str(other)), self.precision)

    def __sub__(self, other: "Price | Decimal | int") -> "Price":
        if isinstance(other, Price):
            return Price(self.value - other.value, max(self.precision, other.precision))
        return Price(self.value - Decimal(str(other)), self.precision)

    def __mul__(self, other: "Decimal | int | float") -> "Price":
        return Price(self.value * Decimal(str(other)), self.precision)

    def __le__(self, other: "Price") -> bool:
        return self.value <= other.value

    def __lt__(self, other: "Price") -> bool:
        return self.value < other.value

    def __ge__(self, other: "Price") -> bool:
        return self.value >= other.value

    def __gt__(self, other: "Price") -> bool:
        return self.value > other.value

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Price):
            return self.value == other.value
        return NotImplemented

    def __hash__(self) -> int:
        return hash(self.value)

    def __str__(self) -> str:
        return str(self.value)

    def __repr__(self) -> str:
        return f"Price('{self.value}', precision={self.precision})"


# ── Quantity ──────────────────────────────────────────────────────────────────

class Quantity:
    """
    Immutable quantity value with fixed decimal precision.
    """
    __slots__ = ("value", "precision", "_quantizer")

    def __init__(self, value: Decimal | str | int | float, precision: int) -> None:
        self.precision = precision
        q = Decimal(10) ** -precision
        self._quantizer = q
        try:
            self.value = Decimal(str(value)).quantize(q, rounding=ROUND_HALF_UP)
        except InvalidOperation as exc:
            raise ValueError(f"Cannot create Quantity from {value!r}") from exc

    @classmethod
    def zero(cls, precision: int = 0) -> "Quantity":
        return cls(Decimal("0"), precision)

    def is_zero(self) -> bool:
        return self.value == Decimal("0")

    def is_positive(self) -> bool:
        return self.value > Decimal("0")

    def __add__(self, other: "Quantity | Decimal") -> "Quantity":
        if isinstance(other, Quantity):
            return Quantity(self.value + other.value, max(self.precision, other.precision))
        return Quantity(self.value + other, self.precision)

    def __sub__(self, other: "Quantity | Decimal") -> "Quantity":
        if isinstance(other, Quantity):
            return Quantity(self.value - other.value, max(self.precision, other.precision))
        return Quantity(self.value - other, self.precision)

    def __mul__(self, other: "Decimal | int | float") -> "Quantity":
        return Quantity(self.value * Decimal(str(other)), self.precision)

    def __le__(self, other: "Quantity") -> bool:
        return self.value <= other.value

    def __lt__(self, other: "Quantity") -> bool:
        return self.value < other.value

    def __ge__(self, other: "Quantity") -> bool:
        return self.value >= other.value

    def __gt__(self, other: "Quantity") -> bool:
        return self.value > other.value

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Quantity):
            return self.value == other.value
        return NotImplemented

    def __hash__(self) -> int:
        return hash(self.value)

    def __str__(self) -> str:
        return str(self.value)

    def __repr__(self) -> str:
        return f"Quantity('{self.value}', precision={self.precision})"


# ── Money ─────────────────────────────────────────────────────────────────────

class Money:
    """
    Immutable monetary value: amount + currency.
    """
    __slots__ = ("amount", "currency")

    def __init__(self, amount: Decimal | str | int | float, currency: Currency) -> None:
        self.currency = currency
        q = Decimal(10) ** -currency.precision
        self.amount = Decimal(str(amount)).quantize(q, rounding=ROUND_HALF_UP)

    def __add__(self, other: "Money") -> "Money":
        if other.currency != self.currency:
            raise ValueError(f"Cannot add {self.currency} and {other.currency}")
        return Money(self.amount + other.amount, self.currency)

    def __sub__(self, other: "Money") -> "Money":
        if other.currency != self.currency:
            raise ValueError(f"Cannot subtract {self.currency} and {other.currency}")
        return Money(self.amount - other.amount, self.currency)

    def __mul__(self, factor: Decimal | int | float) -> "Money":
        return Money(self.amount * Decimal(str(factor)), self.currency)

    def __neg__(self) -> "Money":
        return Money(-self.amount, self.currency)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Money):
            return self.amount == other.amount and self.currency == other.currency
        return NotImplemented

    def __hash__(self) -> int:
        return hash((self.amount, self.currency))

    def __str__(self) -> str:
        return f"{self.amount} {self.currency}"

    def __repr__(self) -> str:
        return f"Money('{self.amount}', {self.currency!r})"


# ── AccountBalance ────────────────────────────────────────────────────────────

class AccountBalance:
    """
    Full account balance snapshot for one currency.

    Attributes
    ----------
    total : Money
        Total balance (free + locked).
    locked : Money
        Amount reserved for open orders.
    free : Money
        Amount available for new orders.
    """
    __slots__ = ("total", "locked", "free")

    def __init__(self, total: Money, locked: Money, free: Money) -> None:
        if total.currency != locked.currency or total.currency != free.currency:
            raise ValueError("All Money objects must share the same currency")
        self.total = total
        self.locked = locked
        self.free = free

    def __repr__(self) -> str:
        return (
            f"AccountBalance("
            f"total={self.total}, locked={self.locked}, free={self.free})"
        )


# ── MarginBalance ─────────────────────────────────────────────────────────────

class MarginBalance:
    """
    Margin account balance for one instrument.

    Attributes
    ----------
    initial : Money
        Initial margin required to open the position.
    maintenance : Money
        Minimum margin to maintain the position.
    instrument_id : str | None
        The instrument this margin relates to.
    """
    __slots__ = ("initial", "maintenance", "instrument_id")

    def __init__(
        self,
        initial: Money,
        maintenance: Money,
        instrument_id: Optional[str] = None,
    ) -> None:
        self.initial = initial
        self.maintenance = maintenance
        self.instrument_id = instrument_id

    def __repr__(self) -> str:
        return (
            f"MarginBalance("
            f"initial={self.initial}, maintenance={self.maintenance}, "
            f"instrument={self.instrument_id})"
        )
