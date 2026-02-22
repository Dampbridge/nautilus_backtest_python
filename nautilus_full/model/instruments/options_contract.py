"""Options contract."""
from __future__ import annotations

from decimal import Decimal
from typing import Optional

from nautilus_full.core.enums import AssetClass, InstrumentClass, OptionKind
from nautilus_full.core.identifiers import InstrumentId
from nautilus_full.core.objects import Currency, Price, Quantity
from nautilus_full.model.instruments.base import Instrument


class OptionsContract(Instrument):
    """
    Vanilla options contract (European or American style).

    Parameters
    ----------
    option_kind : OptionKind
        CALL or PUT.
    strike_price : Price
        Strike price.
    expiry_date : str
        Expiry date (ISO format).
    underlying : str
        Underlying symbol.
    multiplier : Quantity
        Contract multiplier (e.g. 100 for equity options).
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
        option_kind: OptionKind,
        strike_price: Price,
        expiry_date: str,
        underlying: str,
        is_european: bool = True,
        lot_size: Optional[Quantity] = None,
        margin_init: Decimal = Decimal("0"),
        margin_maint: Decimal = Decimal("0"),
        maker_fee: Decimal = Decimal("0"),
        taker_fee: Decimal = Decimal("0"),
        ts_event: int = 0,
        ts_init: int = 0,
    ) -> None:
        super().__init__(
            instrument_id=instrument_id,
            raw_symbol=raw_symbol,
            asset_class=asset_class,
            instrument_class=InstrumentClass.OPTION,
            quote_currency=currency,
            is_inverse=False,
            price_precision=price_precision,
            size_precision=size_precision,
            price_increment=price_increment,
            size_increment=size_increment,
            multiplier=multiplier,
            lot_size=lot_size or size_increment,
            margin_init=margin_init,
            margin_maint=margin_maint,
            maker_fee=maker_fee,
            taker_fee=taker_fee,
            ts_event=ts_event,
            ts_init=ts_init,
        )
        self.option_kind = option_kind
        self.strike_price = strike_price
        self.expiry_date = expiry_date
        self.underlying = underlying
        self.is_european = is_european
        self.currency = currency

    @property
    def is_call(self) -> bool:
        return self.option_kind == OptionKind.CALL

    @property
    def is_put(self) -> bool:
        return self.option_kind == OptionKind.PUT

    def intrinsic_value(self, underlying_price: Decimal) -> Decimal:
        if self.is_call:
            return max(Decimal("0"), underlying_price - self.strike_price.value)
        return max(Decimal("0"), self.strike_price.value - underlying_price)
