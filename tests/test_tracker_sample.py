"""Round trip against the fake sample: the generator's own data goes into the
.xlsx, load_tracker reads it back, and the two must match exactly."""

from datetime import date, datetime
from decimal import Decimal

import pytest

from finance_tracker import layout
from finance_tracker.sample_tracker import FAKE_ACCOUNTS, FAKE_BUDGETS, build_sample_tracker, make_data
from finance_tracker.sources import XlsxSource
from finance_tracker.tracker import Month, load_tracker

NOW = datetime(2026, 11, 20, 14, 0)  # same fixed "now" as the generator tests
NOV, OCT = Month(2026, 11), Month(2026, 10)


@pytest.fixture(scope="module")
def generated():
    """What the generator meant to write: (income, expenses)."""
    income, expenses, _history = make_data(NOW, seed=42)
    return income, expenses


@pytest.fixture(scope="module")
def tracker(tmp_path_factory):
    path = build_sample_tracker(tmp_path_factory.mktemp("sample") / "tracker.xlsx", now=NOW)
    return load_tracker(XlsxSource(path))


def as_date(value) -> date:
    return value.date() if isinstance(value, datetime) else value


def test_every_row_is_read_back_exactly(tracker, generated):
    income, expenses = generated
    assert [(t.date, t.description, t.category, t.amount, t.account) for t in tracker.expenses] == \
           [(as_date(e["date"]), e["description"], e["category"], Decimal(str(e["amount"])), e["account"]) for e in expenses]
    assert [(t.date, t.description, t.amount, t.tithing_paid, t.tithing_paid_date) for t in tracker.income] == \
           [(i["date"], i["description"], Decimal(str(i["amount"])), i["tithing_paid"], i.get("tithing_paid_date"))
            for i in income]


def test_nothing_is_skipped(tracker):
    # The sample's 40 checkbox-only Income rows are ignored, not reported as problems.
    assert tracker.skipped_rows == []


def test_lists_and_settings_come_from_the_sheet(tracker):
    assert tracker.income_categories == layout.INCOME_CATEGORIES
    assert tracker.expense_categories == layout.EXPENSE_CATEGORIES
    assert tracker.account_names == [name for name, *_ in FAKE_ACCOUNTS]
    assert tracker.budgets == {c: Decimal(b) for c, b in FAKE_BUDGETS.items()}
    assert tracker.tithing_rate == Decimal("0.1")
    assert tracker.spending_multiplier == Decimal("1.25")


def test_spending_matches_the_generated_data(tracker, generated):
    _income, expenses = generated
    expected = sum(Decimal(str(e["amount"])) for e in expenses
                   if Month.of(as_date(e["date"])) == NOV and e["category"] != layout.TRANSFER)
    assert tracker.total_spending(NOV) == expected


def test_this_months_budget_tells_the_planned_story(tracker):
    status = {line.category: line.status for line in tracker.budget_lines(NOV)}
    assert status["Shopping"] == "OVER"
    assert status["Housing"] == "Watch"  # $475 rent of a $500 budget
    assert set(status.values()) <= {"OVER", "Watch", "On track", "Set budget"}


def test_shopping_is_flagged_as_unusually_high(tracker):
    assert tracker.is_unusually_high(NOV, "Shopping")


def test_tithing_is_unpaid_this_month_and_paid_last_month(tracker):
    assert tracker.income_in(NOV) and all(not t.tithing_paid for t in tracker.income_in(NOV))
    assert tracker.income_in(OCT) and all(t.tithing_paid for t in tracker.income_in(OCT))
