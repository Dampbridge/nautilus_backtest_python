"""Crypto perpetual swap (inverse or linear)."""
from __future__ import annotations

from decimal import Decimal
from typing import Optional

from nautilus_full.core.enums import AssetClass, InstrumentClass
from nautilus_full.core.identifiers import InstrumentId
from nautilus_full.core.objects import Currency, Price, Quantity
from nautilus_full.model.instruments.base import Instrument


class CryptoPerpetual(Instrument):
    """
    Cryptocurrency perpetual futures contract.

    Can be linear (quote-margined, e.g. BTCUSDT on Binance) or
    inverse (base-margined, e.g. BTCUSD on BitMEX).

    Parameters
    ----------
    base_currency : Currency
        The underlying asset (e.g. BTC).
    quote_currency : Currency
        The price denomination (e.g. USDT).
    settlement_currency : Currency
        Margin/settlement currency (= quote for linear, base for inverse).
    is_inverse : bool
        True for inverse (base-margined) contracts.
    funding_rate_8h : Decimal
        Approximate 8-hour funding rate for margin calculations.
    """

    def __init__(
        self,
        instrument_id: InstrumentId,
        raw_symbol: str,
        base_currency: Currency,
        quote_currency: Currency,
        settlement_currency: Currency,
        is_inverse: bool,
        price_precision: int,
        size_precision: int,
        price_increment: Price,
        size_increment: Quantity,
        max_quantity: Optional[Quantity] = None,
        min_quantity: Optional[Quantity] = None,
        max_price: Optional[Price] = None,
        min_price: Optional[Price] = None,
        margin_init: Decimal = Decimal("0.05"),
        margin_maint: Decimal = Decimal("0.025"),
        maker_fee: Decimal = Decimal("0.0002"),
        taker_fee: Decimal = Decimal("0.0004"),
        funding_rate_8h: Decimal = Decimal("0.0001"),
        multiplier: Decimal = Decimal("1"),
        ts_event: int = 0,
        ts_init: int = 0,
    ) -> None:
        super().__init__(
            instrument_id=instrument_id,
            raw_symbol=raw_symbol,
            asset_class=AssetClass.CRYPTO,
            instrument_class=InstrumentClass.SWAP,
            quote_currency=quote_currency,
            is_inverse=is_inverse,
            price_precision=price_precision,
            size_precision=size_precision,
            price_increment=price_increment,
            size_increment=size_increment,
            multiplier=Quantity(multiplier, size_precision),
            lot_size=size_increment,
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
        self.settlement_currency = settlement_currency
        self.funding_rate_8h = funding_rate_8h

    @classmethod
    def from_dict(cls, data: dict) -> "CryptoPerpetual":
        from nautilus_full.core.objects import Currency
        instrument_id = InstrumentId.from_str(data["instrument_id"])
        base = Currency.from_str(data["base_currency"])
        quote = Currency.from_str(data["quote_currency"])
        settle = Currency.from_str(data.get("settlement_currency", data["quote_currency"]))
        pp = data.get("price_precision", 2)
        sp = data.get("size_precision", 3)
        return cls(
            instrument_id=instrument_id,
            raw_symbol=data.get("raw_symbol", instrument_id.symbol),
            base_currency=base,
            quote_currency=quote,
            settlement_currency=settle,
            is_inverse=data.get("is_inverse", False),
            price_precision=pp,
            size_precision=sp,
            price_increment=Price(data.get("price_increment", "0.01"), pp),
            size_increment=Quantity(data.get("size_increment", "0.001"), sp),
            taker_fee=Decimal(str(data.get("taker_fee", "0.0004"))),
            maker_fee=Decimal(str(data.get("maker_fee", "0.0002"))),
            margin_init=Decimal(str(data.get("margin_init", "0.05"))),
            margin_maint=Decimal(str(data.get("margin_maint", "0.025"))),
        )
