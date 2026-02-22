"""
Market data structures.

Bar            — OHLCV bar
QuoteTick      — Best bid/ask snapshot
TradeTick      — Individual trade/print
OrderBookDelta — Single-level order book update
OrderBook      — Full L2 order book (aggregated by price level)
"""
from __future__ import annotations

import bisect
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional

from nautilus_full.core.enums import (
    AggressorSide,
    BarAggregation,
    BookAction,
    BookType,
    OrderSide,
    PriceType,
)
from nautilus_full.core.identifiers import InstrumentId
from nautilus_full.core.objects import Price, Quantity


# ── BarType ───────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class BarSpec:
    """Specification of bar aggregation: step + type."""
    step: int                   # e.g. 5 for a 5-minute bar
    aggregation: BarAggregation
    price_type: PriceType = PriceType.LAST

    def __str__(self) -> str:
        return f"{self.step}-{self.aggregation.name}-{self.price_type.name}"


@dataclass(frozen=True)
class BarType:
    """
    Fully qualified bar type: instrument + spec.

    Example: ``BTCUSDT.BINANCE-1-MINUTE-LAST``
    """
    instrument_id: InstrumentId
    bar_spec: BarSpec

    def __str__(self) -> str:
        return f"{self.instrument_id}-{self.bar_spec}"


# ── Bar ───────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Bar:
    """OHLCV bar."""
    bar_type: BarType
    open: Price
    high: Price
    low: Price
    close: Price
    volume: Quantity
    ts_event: int   # nanoseconds — bar close / event time
    ts_init: int    # nanoseconds — when object was created

    @property
    def instrument_id(self) -> InstrumentId:
        return self.bar_type.instrument_id

    def __repr__(self) -> str:
        return (
            f"Bar({self.bar_type} "
            f"O={self.open} H={self.high} L={self.low} C={self.close} "
            f"V={self.volume})"
        )


# ── QuoteTick ─────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class QuoteTick:
    """Best bid/ask snapshot (Level 1)."""
    instrument_id: InstrumentId
    bid_price: Price
    ask_price: Price
    bid_size: Quantity
    ask_size: Quantity
    ts_event: int
    ts_init: int

    @property
    def mid_price(self) -> Decimal:
        return (self.bid_price.value + self.ask_price.value) / 2

    @property
    def spread(self) -> Decimal:
        return self.ask_price.value - self.bid_price.value

    def __repr__(self) -> str:
        return (
            f"QuoteTick({self.instrument_id} "
            f"bid={self.bid_price} ask={self.ask_price})"
        )


# ── TradeTick ─────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class TradeTick:
    """Individual trade / market print."""
    instrument_id: InstrumentId
    price: Price
    size: Quantity
    aggressor_side: AggressorSide
    trade_id: str
    ts_event: int
    ts_init: int

    def __repr__(self) -> str:
        return (
            f"TradeTick({self.instrument_id} "
            f"{self.aggressor_side.name} {self.size}@{self.price})"
        )


# ── OrderBookDelta ─────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class BookOrder:
    """A single order at a price level in the book."""
    order_id: str     # Venue-assigned order id (for L3)
    price: Price
    size: Quantity
    side: OrderSide

    def __repr__(self) -> str:
        return f"BookOrder({self.side.name} {self.size}@{self.price})"


@dataclass(frozen=True)
class OrderBookDelta:
    """
    A single incremental update to the order book.

    action  — ADD / UPDATE / DELETE / CLEAR
    order   — The order being added, updated, or deleted (None for CLEAR)
    """
    instrument_id: InstrumentId
    action: BookAction
    order: Optional[BookOrder]    # None when action == CLEAR
    flags: int = 0                # Exchange-specific flags
    sequence: int = 0             # Sequence number from exchange
    ts_event: int = 0
    ts_init: int = 0

    def __repr__(self) -> str:
        return f"OrderBookDelta({self.instrument_id} {self.action.name} {self.order})"


@dataclass(frozen=True)
class OrderBookDeltas:
    """Batch of OrderBookDelta objects for a single snapshot or update."""
    instrument_id: InstrumentId
    deltas: list[OrderBookDelta]
    ts_event: int = 0
    ts_init: int = 0


# ── OrderBook ─────────────────────────────────────────────────────────────────

class _Level:
    """Aggregated price level (L2): price + total size."""
    __slots__ = ("price", "size")

    def __init__(self, price: Decimal, size: Decimal) -> None:
        self.price = price
        self.size = size

    def __repr__(self) -> str:
        return f"Level({self.price}x{self.size})"


class OrderBook:
    """
    Full L2 order book aggregated by price level.

    Bids are kept in descending order (highest first).
    Asks are kept in ascending order (lowest first).

    Supports both:
    - Real L2 updates from OrderBookDelta events
    - Synthetic updates from QuoteTick / Bar data for simulation
    """

    def __init__(
        self,
        instrument_id: InstrumentId,
        book_type: BookType = BookType.L2_MBP,
    ) -> None:
        self.instrument_id = instrument_id
        self.book_type = book_type
        self.sequence: int = 0
        self.ts_last: int = 0

        # dict[price_as_Decimal -> size_as_Decimal]
        self._bids: dict[Decimal, Decimal] = {}
        self._asks: dict[Decimal, Decimal] = {}

        # Sorted price lists (maintained in sync with the dicts)
        self._bid_prices: list[Decimal] = []  # descending
        self._ask_prices: list[Decimal] = []  # ascending

    # ── Book updates ───────────────────────────────────────────────────────

    def apply_delta(self, delta: OrderBookDelta) -> None:
        """Apply a single delta to the book."""
        if delta.action == BookAction.CLEAR:
            self.clear()
            return

        order = delta.order
        assert order is not None
        px = order.price.value
        sz = order.size.value
        side = order.side

        if delta.action == BookAction.ADD:
            self._update_level(side, px, sz, add=True)
        elif delta.action == BookAction.UPDATE:
            self._update_level(side, px, sz, add=False)
        elif delta.action == BookAction.DELETE:
            self._delete_level(side, px)

        self.sequence = delta.sequence
        self.ts_last = delta.ts_event

    def apply_deltas(self, deltas: OrderBookDeltas) -> None:
        for delta in deltas.deltas:
            self.apply_delta(delta)

    def update_from_quote(self, quote: QuoteTick) -> None:
        """Synthetic L1 update from a quote tick."""
        self.clear()
        self._update_level(OrderSide.BUY, quote.bid_price.value, quote.bid_size.value, add=False)
        self._update_level(OrderSide.SELL, quote.ask_price.value, quote.ask_size.value, add=False)
        self.ts_last = quote.ts_event

    def update_from_bar(self, bar: Bar, spread_pct: Decimal = Decimal("0.0001")) -> None:
        """
        Synthetic L1 update from a bar (mid-price approximation).
        Sets bid = close*(1-spread/2), ask = close*(1+spread/2).
        """
        self.clear()
        mid = bar.close.value
        half_spread = mid * spread_pct / 2
        bid_px = mid - half_spread
        ask_px = mid + half_spread
        # Large synthetic size so we never "run out of book"
        size = Decimal("1e9")
        self._update_level(OrderSide.BUY, bid_px, size, add=False)
        self._update_level(OrderSide.SELL, ask_px, size, add=False)
        self.ts_last = bar.ts_event

    def clear(self) -> None:
        self._bids.clear()
        self._asks.clear()
        self._bid_prices.clear()
        self._ask_prices.clear()

    # ── Best price / spread ────────────────────────────────────────────────

    @property
    def best_bid_price(self) -> Optional[Decimal]:
        return self._bid_prices[-1] if self._bid_prices else None

    @property
    def best_ask_price(self) -> Optional[Decimal]:
        return self._ask_prices[0] if self._ask_prices else None

    @property
    def best_bid_size(self) -> Optional[Decimal]:
        bp = self.best_bid_price
        return self._bids.get(bp) if bp is not None else None

    @property
    def best_ask_size(self) -> Optional[Decimal]:
        ap = self.best_ask_price
        return self._asks.get(ap) if ap is not None else None

    @property
    def spread(self) -> Optional[Decimal]:
        bp, ap = self.best_bid_price, self.best_ask_price
        if bp is not None and ap is not None:
            return ap - bp
        return None

    @property
    def mid_price(self) -> Optional[Decimal]:
        bp, ap = self.best_bid_price, self.best_ask_price
        if bp is not None and ap is not None:
            return (bp + ap) / 2
        return None

    # ── Depth queries ──────────────────────────────────────────────────────

    def bids(self, depth: int = 10) -> list[tuple[Decimal, Decimal]]:
        """Return top ``depth`` bid levels as (price, size) descending."""
        prices = self._bid_prices[-depth:] if depth else self._bid_prices
        return [(p, self._bids[p]) for p in reversed(prices)]

    def asks(self, depth: int = 10) -> list[tuple[Decimal, Decimal]]:
        """Return top ``depth`` ask levels as (price, size) ascending."""
        prices = self._ask_prices[:depth] if depth else self._ask_prices
        return [(p, self._asks[p]) for p in prices]

    def volume_at_price(self, side: OrderSide, price: Decimal) -> Decimal:
        """Available size at a specific price level."""
        book = self._bids if side == OrderSide.BUY else self._asks
        return book.get(price, Decimal("0"))

    def simulate_market_fill(
        self, side: OrderSide, quantity: Decimal
    ) -> list[tuple[Decimal, Decimal]]:
        """
        Simulate sweeping the book for a market order.

        Returns list of (price, filled_qty) tuples in fill order.
        Does NOT modify the book state.
        """
        fills: list[tuple[Decimal, Decimal]] = []
        remaining = quantity

        if side == OrderSide.BUY:
            levels = list(self.asks())   # ascending (lowest ask first)
        else:
            levels = list(self.bids())   # descending (highest bid first)

        for price, avail in levels:
            if remaining <= 0:
                break
            fill_qty = min(remaining, avail)
            fills.append((price, fill_qty))
            remaining -= fill_qty

        return fills

    # ── Internal helpers ───────────────────────────────────────────────────

    def _update_level(
        self, side: OrderSide, price: Decimal, size: Decimal, add: bool
    ) -> None:
        if side == OrderSide.BUY:
            book, prices = self._bids, self._bid_prices
            if size <= 0:
                self._delete_level(side, price)
                return
            if price not in book:
                # Insert in ascending order (bids stored ascending, reversed on read)
                bisect.insort(prices, price)
            book[price] = (book.get(price, Decimal("0")) + size) if add else size
        else:
            book, prices = self._asks, self._ask_prices
            if size <= 0:
                self._delete_level(side, price)
                return
            if price not in book:
                bisect.insort(prices, price)
            book[price] = (book.get(price, Decimal("0")) + size) if add else size

    def _delete_level(self, side: OrderSide, price: Decimal) -> None:
        if side == OrderSide.BUY:
            self._bids.pop(price, None)
            try:
                self._bid_prices.remove(price)
            except ValueError:
                pass
        else:
            self._asks.pop(price, None)
            try:
                self._ask_prices.remove(price)
            except ValueError:
                pass

    def __repr__(self) -> str:
        return (
            f"OrderBook({self.instrument_id} "
            f"bid={self.best_bid_price} ask={self.best_ask_price} "
            f"spread={self.spread})"
        )


# ── InstrumentStatus ──────────────────────────────────────────────────────────

@dataclass(frozen=True)
class InstrumentStatus:
    """Market status update for an instrument."""
    instrument_id: InstrumentId
    status: str   # "OPEN", "HALT", "CLOSE", etc.
    ts_event: int
    ts_init: int
