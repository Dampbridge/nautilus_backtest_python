"""
Portfolio — real-time PnL tracking, margin calculations, and equity curve.

The Portfolio aggregates positions across all venues/instruments to produce:
  - Net account value
  - Open PnL
  - Realized PnL
  - Margin utilization
"""
from __future__ import annotations

from decimal import Decimal
from typing import Optional

from nautilus_full.core.identifiers import AccountId, InstrumentId, StrategyId, Venue
from nautilus_full.core.objects import Currency, Money, Price
from nautilus_full.state.cache import Cache


class Portfolio:
    """
    Real-time portfolio tracker.

    Depends on the Cache for positions and accounts.
    Depends on mark prices from the Cache for unrealized PnL.
    """

    def __init__(self, cache: Cache) -> None:
        self._cache = cache
        self._realized_pnl_by_strategy: dict[StrategyId, Decimal] = {}
        self._equity_curve: list[tuple[int, Decimal]] = []  # (ts_ns, equity)

    # ── Net Position queries ────────────────────────────────────────────────

    def net_position(
        self,
        instrument_id: InstrumentId,
        strategy_id: Optional[StrategyId] = None,
    ) -> Decimal:
        """Signed net quantity for an instrument (positive=long, negative=short)."""
        positions = self._cache.positions_open(
            instrument_id=instrument_id, strategy_id=strategy_id
        )
        return sum(p.signed_qty for p in positions)

    def is_flat(
        self,
        instrument_id: InstrumentId,
        strategy_id: Optional[StrategyId] = None,
    ) -> bool:
        return self.net_position(instrument_id, strategy_id) == Decimal("0")

    def is_net_long(
        self,
        instrument_id: InstrumentId,
        strategy_id: Optional[StrategyId] = None,
    ) -> bool:
        return self.net_position(instrument_id, strategy_id) > 0

    def is_net_short(
        self,
        instrument_id: InstrumentId,
        strategy_id: Optional[StrategyId] = None,
    ) -> bool:
        return self.net_position(instrument_id, strategy_id) < 0

    # ── PnL ────────────────────────────────────────────────────────────────

    def unrealized_pnl(
        self,
        instrument_id: Optional[InstrumentId] = None,
        strategy_id: Optional[StrategyId] = None,
    ) -> Decimal:
        """Total unrealized PnL across open positions."""
        positions = self._cache.positions_open(instrument_id, strategy_id)
        total = Decimal("0")
        for pos in positions:
            mark = self._cache.price(pos.instrument_id)
            if mark:
                pos.update_unrealized_pnl(mark)
            total += pos.unrealized_pnl
        return total

    def realized_pnl(
        self,
        instrument_id: Optional[InstrumentId] = None,
        strategy_id: Optional[StrategyId] = None,
    ) -> Decimal:
        """Total realized PnL across all (open + closed) positions."""
        return sum(
            p.realized_pnl
            for p in self._cache.positions(instrument_id, strategy_id)
        )

    def total_pnl(
        self,
        instrument_id: Optional[InstrumentId] = None,
        strategy_id: Optional[StrategyId] = None,
    ) -> Decimal:
        return self.realized_pnl(instrument_id, strategy_id) + self.unrealized_pnl(instrument_id, strategy_id)

    def commissions(self) -> Decimal:
        return sum(p.commissions for p in self._cache.positions())

    # ── Account value ──────────────────────────────────────────────────────

    def account_value(self, venue: Optional[Venue] = None) -> Decimal:
        """
        Total account value across all accounts (or for a specific venue).

        = cash balance + unrealized PnL on open positions
        """
        total = Decimal("0")
        for account in self._cache.accounts():
            if venue and hasattr(account, "id"):
                acc_venue = str(account.id).split("-")[0]
                if acc_venue != str(venue):
                    continue
            # Sum balances
            if hasattr(account, "balances"):
                for bal in account.balances().values():
                    total += bal.total.amount
        return total + self.unrealized_pnl()

    def record_equity(self, ts_ns: int, equity: Decimal) -> None:
        self._equity_curve.append((ts_ns, equity))

    @property
    def equity_curve(self) -> list[tuple[int, Decimal]]:
        return self._equity_curve
