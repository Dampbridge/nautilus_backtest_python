"""
Account — tracks cash/margin balances per currency.

CashAccount   — no leverage; positions are limited to available cash.
MarginAccount — supports leverage; tracks margin requirements separately.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Optional

from nautilus_full.core.enums import AccountType
from nautilus_full.core.identifiers import AccountId
from nautilus_full.core.objects import AccountBalance, Currency, Money


class Account:
    """Abstract base account."""

    def __init__(
        self,
        account_id: AccountId,
        account_type: AccountType,
        base_currency: Optional[Currency],
    ) -> None:
        self.id = account_id
        self.account_type = account_type
        self.base_currency = base_currency
        # currency -> AccountBalance
        self._balances: dict[Currency, AccountBalance] = {}
        # currency -> cumulative commission
        self.commissions: dict[Currency, Decimal] = {}

    # ── Balance management ─────────────────────────────────────────────────

    def update_balance(
        self, currency: Currency, total: Decimal, locked: Decimal
    ) -> None:
        free = total - locked
        self._balances[currency] = AccountBalance(
            total=Money(total, currency),
            locked=Money(locked, currency),
            free=Money(max(free, Decimal("0")), currency),
        )

    def balance_total(self, currency: Optional[Currency] = None) -> Optional[Money]:
        curr = currency or self.base_currency
        if curr is None:
            return None
        bal = self._balances.get(curr)
        return bal.total if bal else None

    def balance_free(self, currency: Optional[Currency] = None) -> Optional[Money]:
        curr = currency or self.base_currency
        if curr is None:
            return None
        bal = self._balances.get(curr)
        return bal.free if bal else None

    def balance_locked(self, currency: Optional[Currency] = None) -> Optional[Money]:
        curr = currency or self.base_currency
        if curr is None:
            return None
        bal = self._balances.get(curr)
        return bal.locked if bal else None

    def balances(self) -> dict[Currency, AccountBalance]:
        return dict(self._balances)

    def update_commissions(self, currency: Currency, amount: Decimal) -> None:
        self.commissions[currency] = self.commissions.get(currency, Decimal("0")) + amount

    # ── Checking ───────────────────────────────────────────────────────────

    def has_sufficient_balance(self, required: Decimal, currency: Currency) -> bool:
        free = self.balance_free(currency)
        if free is None:
            return False
        return free.amount >= required

    def deduct(self, amount: Decimal, currency: Currency) -> None:
        """Deduct from free balance (for cash reservations)."""
        bal = self._balances.get(currency)
        if bal is None:
            raise ValueError(f"No balance for {currency}")
        new_free = bal.free.amount - amount
        new_locked = bal.locked.amount + amount
        self.update_balance(currency, bal.total.amount, new_locked)

    def credit(self, amount: Decimal, currency: Currency) -> None:
        """Add to total and free balance (for proceeds, PnL)."""
        bal = self._balances.get(currency)
        if bal is None:
            self.update_balance(currency, amount, Decimal("0"))
        else:
            new_total = bal.total.amount + amount
            self.update_balance(currency, new_total, bal.locked.amount)

    def __repr__(self) -> str:
        balances_str = ", ".join(
            f"{c}={b.total}" for c, b in self._balances.items()
        )
        return f"{type(self).__name__}(id={self.id}, [{balances_str}])"


class CashAccount(Account):
    """
    Cash account — positions must be backed by actual cash.
    No borrowing, no leverage.
    """

    def __init__(
        self, account_id: AccountId, base_currency: Optional[Currency] = None
    ) -> None:
        super().__init__(account_id, AccountType.CASH, base_currency)

    def calculate_order_cost(
        self, quantity: Decimal, price: Decimal, currency: Currency
    ) -> Decimal:
        return quantity * price

    def can_submit_order(
        self,
        quantity: Decimal,
        price: Decimal,
        currency: Currency,
    ) -> tuple[bool, str]:
        cost = self.calculate_order_cost(quantity, price, currency)
        free = self.balance_free(currency)
        if free is None or free.amount < cost:
            return False, f"Insufficient balance: need {cost:.2f} {currency}, have {free}"
        return True, ""


class MarginAccount(Account):
    """
    Margin account — supports leverage via initial margin requirements.

    Tracks margin per-instrument separately from cash balance.
    """

    def __init__(
        self,
        account_id: AccountId,
        base_currency: Optional[Currency] = None,
        leverage: Decimal = Decimal("1"),
        default_margin_init: Decimal = Decimal("0.05"),
        default_margin_maint: Decimal = Decimal("0.025"),
    ) -> None:
        super().__init__(account_id, AccountType.MARGIN, base_currency)
        self.leverage = leverage
        self.default_margin_init = default_margin_init
        self.default_margin_maint = default_margin_maint
        # instrument_id_str -> (initial_margin, maintenance_margin)
        self._margin_locked: dict[str, Decimal] = {}

    def update_margin(self, instrument_id: str, initial: Decimal, maintenance: Decimal) -> None:
        self._margin_locked[instrument_id] = initial

    def total_margin_locked(self, currency: Currency) -> Decimal:
        return sum(self._margin_locked.values())

    def calculate_initial_margin(
        self,
        instrument,
        quantity: Decimal,
        price: Decimal,
    ) -> Decimal:
        notional = quantity * price
        return notional * instrument.margin_init / self.leverage

    def can_submit_order(
        self,
        quantity: Decimal,
        price: Decimal,
        currency: Currency,
        instrument=None,
    ) -> tuple[bool, str]:
        if instrument:
            required_margin = self.calculate_initial_margin(instrument, quantity, price)
        else:
            required_margin = quantity * price * self.default_margin_init / self.leverage
        free = self.balance_free(currency)
        if free is None or free.amount < required_margin:
            return False, f"Insufficient margin: need {required_margin:.2f}, have {free}"
        return True, ""
