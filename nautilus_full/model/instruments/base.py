"""Abstract Instrument base class."""
from __future__ import annotations

from decimal import Decimal
from typing import Optional

from nautilus_full.core.enums import AssetClass, InstrumentClass
from nautilus_full.core.identifiers import InstrumentId, Venue
from nautilus_full.core.objects import Currency, Price, Quantity


class Instrument:
    """
    Abstract instrument definition.

    All instruments carry pricing metadata used by the matching engine,
    position tracking, and risk calculations.
    """

    def __init__(
        self,
        instrument_id: InstrumentId,
        raw_symbol: str,
        asset_class: AssetClass,
        instrument_class: InstrumentClass,
        quote_currency: Currency,
        is_inverse: bool,
        price_precision: int,
        size_precision: int,
        price_increment: Price,
        size_increment: Quantity,
        multiplier: Quantity,
        lot_size: Optional[Quantity],
        max_quantity: Optional[Quantity],
        min_quantity: Optional[Quantity],
        max_notional: Optional["Money"] = None,
        min_notional: Optional["Money"] = None,
        max_price: Optional[Price] = None,
        min_price: Optional[Price] = None,
        margin_init: Decimal = Decimal("0"),
        margin_maint: Decimal = Decimal("0"),
        maker_fee: Decimal = Decimal("0"),
        taker_fee: Decimal = Decimal("0"),
        ts_event: int = 0,
        ts_init: int = 0,
        info: Optional[dict] = None,
    ) -> None:
        self.id = instrument_id
        self.raw_symbol = raw_symbol
        self.asset_class = asset_class
        self.instrument_class = instrument_class
        self.quote_currency = quote_currency
        self.is_inverse = is_inverse

        self.price_precision = price_precision
        self.size_precision = size_precision
        self.price_increment = price_increment
        self.size_increment = size_increment
        self.multiplier = multiplier
        self.lot_size = lot_size

        self.max_quantity = max_quantity
        self.min_quantity = min_quantity
        self.max_notional = max_notional
        self.min_notional = min_notional
        self.max_price = max_price
        self.min_price = min_price

        self.margin_init = margin_init
        self.margin_maint = margin_maint
        self.maker_fee = maker_fee
        self.taker_fee = taker_fee

        self.ts_event = ts_event
        self.ts_init = ts_init
        self.info = info or {}

    @property
    def symbol(self) -> str:
        return self.id.symbol

    @property
    def venue(self) -> Venue:
        return self.id.venue

    def make_price(self, value: Decimal) -> Price:
        """Round a value to this instrument's price precision."""
        return Price(value, self.price_precision)

    def make_qty(self, value: Decimal) -> Quantity:
        """Round a value to this instrument's size precision."""
        return Quantity(value, self.size_precision)

    def notional_value(self, quantity: Quantity, price: Price) -> Decimal:
        """
        Calculate notional (contract) value.
        For inverse instruments: notional = qty / price * multiplier
        For linear instruments: notional = qty * price * multiplier
        """
        if self.is_inverse:
            return quantity.value / price.value * self.multiplier.value
        return quantity.value * price.value * self.multiplier.value

    def __repr__(self) -> str:
        return f"{type(self).__name__}(id={self.id})"

    def __hash__(self) -> int:
        return hash(self.id)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Instrument):
            return self.id == other.id
        return NotImplemented
