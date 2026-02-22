"""
Simulation models for venue behaviour.

FillModel   — controls fill probability and slippage.
FeeModel    — calculates commissions (maker/taker/flat).
LatencyModel — simulates order processing latency.
"""
from __future__ import annotations

import random
from decimal import Decimal
from typing import Optional

from nautilus_full.core.enums import LiquiditySide, OrderSide
from nautilus_full.core.objects import Currency, Money, Price, Quantity
from nautilus_full.model.instruments.base import Instrument
from nautilus_full.model.orders.base import Order


# ── Fill Model ────────────────────────────────────────────────────────────────

class FillModel:
    """
    Controls whether and at what price an order fills in simulation.

    Parameters
    ----------
    prob_fill_on_limit : float
        Probability [0,1] that a limit order fills when price exactly equals
        the limit (vs. needing to go strictly through it). Default 0.5.
    prob_slippage : float
        Probability [0,1] of an extra tick of slippage on market orders.
    random_seed : int, optional
        Seed for reproducibility.
    max_slippage_ticks : int
        Maximum number of ticks of slippage to apply.
    """

    def __init__(
        self,
        prob_fill_on_limit: float = 0.5,
        prob_slippage: float = 0.0,
        random_seed: Optional[int] = None,
        max_slippage_ticks: int = 1,
    ) -> None:
        self.prob_fill_on_limit = prob_fill_on_limit
        self.prob_slippage = prob_slippage
        self.max_slippage_ticks = max_slippage_ticks
        self._rng = random.Random(random_seed)

    def is_limit_filled(self, is_exactly_at_limit: bool) -> bool:
        """Return True if the limit order should fill at the limit price."""
        if not is_exactly_at_limit:
            return True  # Price went through: always fills
        return self._rng.random() < self.prob_fill_on_limit

    def apply_slippage(
        self, price: Price, side: OrderSide, instrument: Instrument
    ) -> Price:
        """Apply random slippage to a market fill price."""
        if self.prob_slippage > 0 and self._rng.random() < self.prob_slippage:
            ticks = self._rng.randint(1, self.max_slippage_ticks)
            offset = instrument.price_increment.value * ticks
            if side == OrderSide.BUY:
                return Price(price.value + offset, instrument.price_precision)
            else:
                return Price(price.value - offset, instrument.price_precision)
        return price


class DefaultFillModel(FillModel):
    """No slippage, guaranteed fills when price crosses limit."""

    def __init__(self) -> None:
        super().__init__(prob_fill_on_limit=1.0, prob_slippage=0.0)


# ── Fee Model ─────────────────────────────────────────────────────────────────

class FeeModel:
    """Calculates trading commissions per fill."""

    def calculate(
        self,
        order: Order,
        fill_qty: Quantity,
        fill_px: Price,
        instrument: Instrument,
        liquidity_side: LiquiditySide,
    ) -> Money:
        raise NotImplementedError


class MakerTakerFeeModel(FeeModel):
    """
    Percentage-based maker/taker fee model.

    Fee = fill_qty * fill_px * fee_rate (applied on notional).
    For inverse instruments: fee_rate is applied to base qty.
    """

    def calculate(
        self,
        order: Order,
        fill_qty: Quantity,
        fill_px: Price,
        instrument: Instrument,
        liquidity_side: LiquiditySide,
    ) -> Money:
        rate = (
            instrument.maker_fee
            if liquidity_side == LiquiditySide.MAKER
            else instrument.taker_fee
        )
        notional = instrument.notional_value(fill_qty, fill_px)
        commission_amount = notional * rate
        return Money(commission_amount, instrument.quote_currency)


class FixedFeeModel(FeeModel):
    """Flat fee per trade (e.g. $1 per contract for futures)."""

    def __init__(self, fee_per_trade: Money) -> None:
        self.fee_per_trade = fee_per_trade

    def calculate(
        self,
        order: Order,
        fill_qty: Quantity,
        fill_px: Price,
        instrument: Instrument,
        liquidity_side: LiquiditySide,
    ) -> Money:
        return self.fee_per_trade


class PerShareFeeModel(FeeModel):
    """Per-share fee (common for US equity brokers)."""

    def __init__(self, fee_per_share: Money) -> None:
        self.fee_per_share = fee_per_share

    def calculate(
        self,
        order: Order,
        fill_qty: Quantity,
        fill_px: Price,
        instrument: Instrument,
        liquidity_side: LiquiditySide,
    ) -> Money:
        return Money(
            self.fee_per_share.amount * fill_qty.value,
            self.fee_per_share.currency,
        )


class ZeroFeeModel(FeeModel):
    """No commissions (for zero-fee brokers or simplified backtests)."""

    def calculate(self, order, fill_qty, fill_px, instrument, liquidity_side) -> Money:
        return Money(Decimal("0"), instrument.quote_currency)


# ── Latency Model ─────────────────────────────────────────────────────────────

class LatencyModel:
    """
    Simulates order submission and fill notification latency.

    In backtesting, latency is typically ignored (0 ns), but this model
    can be used to test sensitivity to execution delays.
    """

    def __init__(
        self,
        base_latency_ns: int = 0,
        insert_latency_ns: int = 0,
        update_latency_ns: int = 0,
        cancel_latency_ns: int = 0,
    ) -> None:
        self.base_latency_ns = base_latency_ns
        self.insert_latency_ns = insert_latency_ns
        self.update_latency_ns = update_latency_ns
        self.cancel_latency_ns = cancel_latency_ns

    def submit_delay(self) -> int:
        return self.base_latency_ns + self.insert_latency_ns

    def cancel_delay(self) -> int:
        return self.base_latency_ns + self.cancel_latency_ns

    def update_delay(self) -> int:
        return self.base_latency_ns + self.update_latency_ns


# ── Slippage Model ────────────────────────────────────────────────────────────

class SlippageModel:
    """
    Percentage-based slippage applied to fill price.

    slippage_pct : Decimal
        E.g. Decimal("0.0001") for 1 basis point of slippage.
    """

    def __init__(self, slippage_pct: Decimal = Decimal("0")) -> None:
        self.slippage_pct = slippage_pct

    def apply(self, price: Price, side: OrderSide, instrument: Instrument) -> Price:
        if self.slippage_pct == 0:
            return price
        if side == OrderSide.BUY:
            return Price(
                price.value * (1 + self.slippage_pct),
                instrument.price_precision,
            )
        return Price(
            price.value * (1 - self.slippage_pct),
            instrument.price_precision,
        )
