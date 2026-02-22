"""FX currency pair."""
from __future__ import annotations

from decimal import Decimal
from typing import Optional

from nautilus_full.core.enums import AssetClass, InstrumentClass
from nautilus_full.core.identifiers import InstrumentId
from nautilus_full.core.objects import Currency, Price, Quantity
from nautilus_full.model.instruments.base import Instrument


class CurrencyPair(Instrument):
    """
    Foreign exchange currency pair (spot or NDF).

    The conventional representation is ``BASE/QUOTE`` (e.g. EUR/USD).
    One unit of base currency trades for ``price`` units of quote currency.

    Parameters
    ----------
    base_currency : Currency
        The currency being bought/sold (e.g. EUR in EUR/USD).
    quote_currency : Currency
        The pricing currency (e.g. USD in EUR/USD).
    price_precision : int
        Number of decimal places (4 for most pairs, 2 for JPY pairs).
    """

    def __init__(
        self,
        instrument_id: InstrumentId,
        raw_symbol: str,
        base_currency: Currency,
        quote_currency: Currency,
        price_precision: int,
        size_precision: int,
        price_increment: Price,
        size_increment: Quantity,
        lot_size: Optional[Quantity] = None,
        max_quantity: Optional[Quantity] = None,
        min_quantity: Optional[Quantity] = None,
        max_price: Optional[Price] = None,
        min_price: Optional[Price] = None,
        margin_init: Decimal = Decimal("0.03"),
        margin_maint: Decimal = Decimal("0.03"),
        maker_fee: Decimal = Decimal("0"),
        taker_fee: Decimal = Decimal("0"),
        ts_event: int = 0,
        ts_init: int = 0,
    ) -> None:
        super().__init__(
            instrument_id=instrument_id,
            raw_symbol=raw_symbol,
            asset_class=AssetClass.FX,
            instrument_class=InstrumentClass.SPOT,
            quote_currency=quote_currency,
            is_inverse=False,
            price_precision=price_precision,
            size_precision=size_precision,
            price_increment=price_increment,
            size_increment=size_increment,
            multiplier=Quantity(1, 0),
            lot_size=lot_size,
            max_quantity=max_quantity,
            min_quantity=min_quantity,
            max_price=max_price,
            min_price=min_price,
            margin_init=margin_init,
            margin_maint=margin_maint,
            maker_fee=maker_fee,
            taker_fee=taker_fee,
            ts_event=ts_event,
            ts_init=ts_init,
        )
        self.base_currency = base_currency

    @classmethod
    def from_dict(cls, data: dict) -> "CurrencyPair":
        from nautilus_full.core.objects import Currency
        instrument_id = InstrumentId.from_str(data["instrument_id"])
        base = Currency.from_str(data["base_currency"])
        quote = Currency.from_str(data["quote_currency"])
        pp = data.get("price_precision", 5)
        sp = data.get("size_precision", 0)
        return cls(
            instrument_id=instrument_id,
            raw_symbol=data.get("raw_symbol", instrument_id.symbol),
            base_currency=base,
            quote_currency=quote,
            price_precision=pp,
            size_precision=sp,
            price_increment=Price(data.get("price_increment", "0.00001"), pp),
            size_increment=Quantity(data.get("size_increment", "1000"), sp),
            lot_size=Quantity(data.get("lot_size", "1000"), sp),
            taker_fee=Decimal(str(data.get("taker_fee", "0"))),
            maker_fee=Decimal(str(data.get("maker_fee", "0"))),
        )
