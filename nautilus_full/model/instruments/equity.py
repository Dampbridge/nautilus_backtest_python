"""Equity (stock) instrument."""
from __future__ import annotations

from decimal import Decimal
from typing import Optional

from nautilus_full.core.enums import AssetClass, InstrumentClass
from nautilus_full.core.identifiers import InstrumentId
from nautilus_full.core.objects import Currency, Price, Quantity
from nautilus_full.model.instruments.base import Instrument


class Equity(Instrument):
    """
    A tradable equity (stock / ETF / index fund).

    Parameters
    ----------
    instrument_id : InstrumentId
        e.g. ``AAPL.NASDAQ``
    currency : Currency
        Settlement currency (usually USD for US equities).
    price_precision : int
        Decimal places for price quotes.
    price_increment : Price
        Minimum price movement (tick size).
    lot_size : Quantity
        Minimum trade size (usually 1 share for US equities).
    isin : str, optional
        International Securities Identification Number.
    """

    def __init__(
        self,
        instrument_id: InstrumentId,
        raw_symbol: str,
        currency: Currency,
        price_precision: int,
        price_increment: Price,
        lot_size: Quantity,
        max_quantity: Optional[Quantity] = None,
        min_quantity: Optional[Quantity] = None,
        max_price: Optional[Price] = None,
        min_price: Optional[Price] = None,
        margin_init: Decimal = Decimal("0"),
        margin_maint: Decimal = Decimal("0"),
        maker_fee: Decimal = Decimal("0"),
        taker_fee: Decimal = Decimal("0"),
        isin: Optional[str] = None,
        ts_event: int = 0,
        ts_init: int = 0,
    ) -> None:
        super().__init__(
            instrument_id=instrument_id,
            raw_symbol=raw_symbol,
            asset_class=AssetClass.EQUITY,
            instrument_class=InstrumentClass.SPOT,
            quote_currency=currency,
            is_inverse=False,
            price_precision=price_precision,
            size_precision=0,  # whole shares
            price_increment=price_increment,
            size_increment=lot_size,
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
            info={"isin": isin} if isin else {},
        )
        self.isin = isin
        self.currency = currency

    @classmethod
    def from_dict(cls, data: dict) -> "Equity":
        instrument_id = InstrumentId.from_str(data["instrument_id"])
        from nautilus_full.core.objects import Currency
        currency = Currency.from_str(data.get("currency", "USD"))
        pp = data.get("price_precision", 2)
        return cls(
            instrument_id=instrument_id,
            raw_symbol=data.get("raw_symbol", instrument_id.symbol),
            currency=currency,
            price_precision=pp,
            price_increment=Price(data.get("price_increment", "0.01"), pp),
            lot_size=Quantity(data.get("lot_size", 1), 0),
            taker_fee=Decimal(str(data.get("taker_fee", "0"))),
            maker_fee=Decimal(str(data.get("maker_fee", "0"))),
            isin=data.get("isin"),
        )
