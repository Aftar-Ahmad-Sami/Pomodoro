import datetime as dt

import pytest

from pomodoro.bank import TimeBank

DAY = dt.date(2026, 10, 26)


def test_deposit_and_withdraw() -> None:
    bank = TimeBank(interest_date=DAY)
    bank.deposit(100)
    assert bank.withdraw(30) == 30
    assert bank.withdraw(500) == 70
    assert bank.balance == 0


def test_negative_amounts_are_ignored() -> None:
    bank = TimeBank(balance=10, interest_date=DAY)
    bank.deposit(-5)
    assert bank.withdraw(-5) == 0
    assert bank.balance == 10


def test_no_interest_on_the_same_day() -> None:
    bank = TimeBank(balance=600, interest_date=DAY)
    assert bank.accrue(DAY) == 0
    assert bank.balance == 600


def test_interest_compounds_daily() -> None:
    bank = TimeBank(balance=600, interest_date=DAY, daily_interest=0.10)
    gained = bank.accrue(DAY + dt.timedelta(days=2))
    assert bank.balance == pytest.approx(600 * 1.1 * 1.1)
    assert gained == pytest.approx(bank.balance - 600)
    assert bank.interest_date == DAY + dt.timedelta(days=2)
    assert bank.accrue(DAY + dt.timedelta(days=2)) == 0  # not applied twice


def test_interest_stops_at_cap() -> None:
    bank = TimeBank(balance=200, interest_date=DAY, daily_interest=0.10, interest_cap=210)
    bank.accrue(DAY + dt.timedelta(days=5))
    assert bank.balance == 210


def test_deposits_above_cap_are_kept_but_earn_nothing() -> None:
    bank = TimeBank(balance=300, interest_date=DAY, interest_cap=240)
    assert bank.accrue(DAY + dt.timedelta(days=3)) == 0
    assert bank.balance == 300


def test_clock_moving_backwards_changes_nothing() -> None:
    bank = TimeBank(balance=600, interest_date=DAY)
    assert bank.accrue(DAY - dt.timedelta(days=1)) == 0
    assert bank.interest_date == DAY
