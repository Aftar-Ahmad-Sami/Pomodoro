"""Time bank: a balance of guilt-free minutes earned by finishing focus sessions early."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field


@dataclass
class TimeBank:
    """Banked seconds, growing with daily compound interest up to a cap."""

    balance: float = 0.0
    interest_date: dt.date = field(default_factory=dt.date.today)  # last day interest was applied
    daily_interest: float = 0.10
    interest_cap: float = 240 * 60

    def deposit(self, seconds: float) -> None:
        self.balance += max(0.0, seconds)

    def withdraw(self, seconds: float) -> float:
        """Takes up to ``seconds`` out of the bank. Returns the amount actually taken."""
        taken = min(self.balance, max(0.0, seconds))
        self.balance -= taken
        return taken

    def accrue(self, today: dt.date) -> float:
        """Applies interest for every day since the last accrual. Returns the seconds gained.

        Interest never lifts the balance past the cap, but deposits above the cap are kept.
        """
        days = (today - self.interest_date).days
        self.interest_date = max(self.interest_date, today)
        if days <= 0 or self.balance >= self.interest_cap:
            return 0.0
        grown = min(self.balance * (1 + self.daily_interest) ** days, self.interest_cap)
        gained = grown - self.balance
        self.balance = grown
        return gained
