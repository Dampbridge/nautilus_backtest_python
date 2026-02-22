"""Exchange-traded futures contract."""
from __future__ import annotations

from decimal import Decimal
from typing import Optional

from nautilus_full.core.enums import AssetClass, InstrumentClass
from nautilus_full.core.identifiers import InstrumentId
from nautilus_full.core.objects import Currency, Price, Quantity
from nautilus_full.model.instruments.base import Instrument


class FuturesContract(Instrument):
    """
    Exchange-traded futures contract.

    Parameters
    ----------
    underlying : str
        The underlying asset or index (e.g. "ES", "CL", "GC").
    expiry_date : str
        Expiry date as ISO format string (e.g. "2025-12-19").
    multiplier : Quantity
        Contract multiplier (e.g. 50 for ES = $50 per index point).
    """

    def __init__(
        self,
        instrument_id: InstrumentId,
        raw_symbol: str,
        asset_class: AssetClass,
        currency: Currency,
        price_precision: int,
        size_precision: int,
        price_increment: Price,
        size_increment: Quantity,
        multiplier: Quantity,
        expiry_date: str,
        underlying: str,
        lot_size: Optional[Quantity] = None,
        max_quantity: Optional[Quantity] = None,
        min_quantity: Optional[Quantity] = None,
        max_price: Optional[Price] = None,
        min_price: Optional[Price] = None,
        margin_init: Decimal = Decimal("0.05"),
        margin_maint: Decimal = Decimal("0.025"),
        maker_fee: Decimal = Decimal("0"),
        taker_fee: Decimal = Decimal("0"),
        is_inverse: bool = False,
        ts_event: int = 0,
        ts_init: int = 0,
    ) -> None:
        super().__init__(
            instrument_id=instrument_id,
            raw_symbol=raw_symbol,
            asset_class=asset_class,
            instrument_class=InstrumentClass.FUTURE,
            quote_currency=currency,
            is_inverse=is_inverse,
            price_precision=price_precision,
            size_precision=size_precision,
            price_increment=price_increment,
            size_increment=size_increment,
            multiplier=multiplier,
            lot_size=lot_size or size_increment,
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
        self.expiry_date = expiry_date
        self.underlying = underlying
        self.currency = currency

    @property
    def is_expired(self) -> bool:
        import datetime
        today = datetime.date.today().isoformat()
        return self.expiry_date < today
