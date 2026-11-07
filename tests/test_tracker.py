"""Tests for tracker.py: parsing raw cells and the sheet's rules.

Uses an in-memory FakeSource whose cells look like what the Google Sheets API
returns (dates as day numbers, "TRUE", "$1,234.50", short rows). No files, no network.
"""

from datetime import date, datetime
from decimal import Decimal

import pytest

from finance_tracker import tracker
from finance_tracker.tracker import BudgetLine, Month, budget_status, load_tracker

NOV_3 = 46329  # Google/Excel day number for 2026-11-03


class FakeSource:
    """Hands back whatever rows a test gives it, one list per range."""

    NAMES = {tracker.INCOME_RANGE: "income", tracker.EXPENSES_RANGE: "expenses",
             tracker.BUDGET_RANGE: "budget", tracker.CATEGORIES_RANGE: "categories",
             tracker.MULTIPLIER_RANGE: "multiplier", tracker.ACCOUNTS_RANGE: "accounts"}

    def __init__(self, **rows):
        self.rows = rows

    def describe(self):
        return "fake source"

    def read(self, ranges):
        return [self.rows.get(self.NAMES[r], []) for r in ranges]


def expense(day: date, category: str, amount: str, row: int = 3) -> tracker.Transaction:
    return tracker.Transaction("expense", day, "test", category, Decimal(amount), row)


def make_tracker(expenses=(), income=(), budgets=None) -> tracker.Tracker:
    return tracker.Tracker(
        income=list(income), expenses=list(expenses), budgets=budgets or {},
        income_categories=[], expense_categories=[], account_names=[],
        tithing_rate=Decimal("0.10"), spending_multiplier=Decimal("1.25"),
    )


# --- Parsing ------------------------------------------------------------------

def test_empty_and_checkbox_only_rows_are_ignored():
    source = FakeSource(income=[
        [],                                                  # empty
        ["", "", "", "", "", False],                         # only an unchecked box
        [NOV_3, "Paycheck", "Job", 600, "", True, NOV_3 + 5],  # a real row
    ])
    t = load_tracker(source)
    assert len(t.income) == 1
    assert t.skipped_rows == []


def test_google_style_cells_are_understood():
    source = FakeSource(income=[[NOV_3 + 0.75, "Paycheck", "Job", "$1,234.50", "", "TRUE", NOV_3 + 4]])
    (paycheck,) = load_tracker(source).income
    assert paycheck.date == date(2026, 11, 3)  # time of day (0.75 = 6 PM) dropped
    assert paycheck.amount == Decimal("1234.50")
    assert paycheck.tithing_paid is True
    assert paycheck.tithing_paid_date == date(2026, 11, 7)


def test_short_rows_are_fine():
    # Google leaves out empty cells at the end of a row.
    source = FakeSource(expenses=[[NOV_3, "Groceries", "Food", 42.1]])
    (groceries,) = load_tracker(source).expenses
    assert groceries.account == "" and groceries.notes == ""


def test_incomplete_rows_are_reported_not_guessed():
    source = FakeSource(expenses=[
        [NOV_3, "Groceries", "Food", 42.10],
        [NOV_3, "Forgot the amount", "Food"],
        ["not a date", "Bad date", "Food", 5],
    ])
    t = load_tracker(source)
    assert len(t.expenses) == 1
    assert t.skipped_rows == [
        "Expenses row 4: needs a valid date and amount",
        "Expenses row 5: needs a valid date and amount",
    ]


def test_settings_and_lists_are_read_from_the_sheet():
    source = FakeSource(
        categories=[["Job", "Housing", "Checking", 0.1], ["Gift", "Food", "Savings"]],
        multiplier=[[1.5]],
        accounts=[["My Checking"], [None], ["My Savings"]],
    )
    t = load_tracker(source)
    assert t.income_categories == ["Job", "Gift"]
    assert t.expense_categories == ["Housing", "Food"]
    assert t.account_names == ["My Checking", "My Savings"]
    assert t.tithing_rate == Decimal("0.1")
    assert t.spending_multiplier == Decimal("1.5")


def test_blank_settings_fall_back_to_defaults():
    t = load_tracker(FakeSource())
    assert t.tithing_rate == Decimal("0.10")
    assert t.spending_multiplier == Decimal("1.25")


def test_budgets_stop_at_total_and_blank_means_zero():
    source = FakeSource(budget=[["Housing", 500], ["Food", None], ["TOTAL", "=SUM(B5:B6)"], ["Ignored", 1]])
    assert load_tracker(source).budgets == {"Housing": Decimal("500.00"), "Food": Decimal("0.00")}


def test_money_adds_up_exactly():
    source = FakeSource(expenses=[[NOV_3, "a", "Food", 0.1], [NOV_3, "b", "Food", 0.2]])
    assert load_tracker(source).total_spending(Month(2026, 11)) == Decimal("0.30")  # not 0.30000000000000004


# --- Months -----------------------------------------------------------------------

def test_month_parsing_and_neighbors():
    assert Month.parse("2026-11") == Month(2026, 11)
    assert str(Month(2026, 3)) == "2026-03"
    assert Month(2026, 1).previous() == Month(2025, 12)
    assert Month(2026, 12).next() == Month(2027, 1)
    assert Month(2026, 11).name == "November 2026"


@pytest.mark.parametrize("bad", ["November", "2026-13", "2026/11", ""])
def test_bad_months_are_rejected(bad):
    with pytest.raises(ValueError):
        Month.parse(bad)


def test_month_includes_the_last_minute_of_the_month():
    t = load_tracker(FakeSource(expenses=[[datetime(2026, 11, 30, 23, 59), "late", "Food", 1]]))
    assert t.total_spending(Month(2026, 11)) == Decimal("1.00")
    assert t.total_spending(Month(2026, 12)) == Decimal("0")


# --- Rules ------------------------------------------------------------------------

@pytest.mark.parametrize("budget, actual, status", [
    ("0", "10", "Set budget"),
    ("100", "100.01", "OVER"),
    ("100", "100", "Watch"),  # exactly on budget is not over
    ("100", "80", "Watch"),   # 80% is the line
    ("100", "79.99", "On track"),
])
def test_budget_status_matches_the_sheet(budget, actual, status):
    assert budget_status(Decimal(budget), Decimal(actual)) == status


def test_budget_line_remaining_and_percent():
    line = BudgetLine("Shopping", Decimal("100"), Decimal("166.52"))
    assert line.remaining == Decimal("-66.52")
    assert line.percent_used == Decimal("167")
    assert BudgetLine("Other", Decimal("0"), Decimal("5")).percent_used is None


def test_transfers_never_count():
    nov = date(2026, 11, 5)
    t = make_tracker(expenses=[expense(nov, "Food", "50"), expense(nov, "Transfer", "200")])
    assert t.total_spending(Month(2026, 11)) == Decimal("50")
    assert t.spending_by_category(Month(2026, 11)) == {"Food": Decimal("50")}
    assert len(t.expenses_in(Month(2026, 11), include_transfers=True)) == 2


def test_budget_lines_use_this_months_spending():
    t = make_tracker(
        expenses=[expense(date(2026, 11, 2), "Food", "250"), expense(date(2026, 10, 2), "Food", "999")],
        budgets={"Food": Decimal("300"), "Shopping": Decimal("100")},
    )
    food, shopping = t.budget_lines(Month(2026, 11))
    assert (food.actual, food.status) == (Decimal("250"), "Watch")
    assert (shopping.actual, shopping.status) == (Decimal("0"), "On track")


def history(nov_amount: str) -> tracker.Tracker:
    """$100 of Food in each of Aug, Sep, Oct, then `nov_amount` in November."""
    months = [date(2026, 8, 10), date(2026, 9, 10), date(2026, 10, 10)]
    return make_tracker(expenses=[expense(d, "Food", "100") for d in months] + [expense(date(2026, 11, 10), "Food", nov_amount)])


def test_three_month_average_uses_the_months_before():
    assert history("500").three_month_average(Month(2026, 11)) == Decimal("100.00")


@pytest.mark.parametrize("nov_amount, high", [("125.01", True), ("125", False), ("60", False)])
def test_unusually_high_means_above_average_times_multiplier(nov_amount, high):
    assert history(nov_amount).is_unusually_high(Month(2026, 11), "Food") is high


def test_no_history_is_never_unusually_high():
    t = make_tracker(expenses=[expense(date(2026, 11, 10), "Food", "500")])
    assert t.is_unusually_high(Month(2026, 11)) is False


def test_tithing_owed_rounds_to_the_cent_and_skips_transfers():
    t = make_tracker()
    pay = tracker.Transaction("income", date(2026, 11, 6), "Paycheck", "Job", Decimal("123.45"), 3)
    move = tracker.Transaction("income", date(2026, 11, 6), "From savings", "Transfer", Decimal("300"), 4)
    assert t.tithing_owed(pay) == Decimal("12.35")  # 12.345 rounds up
    assert t.tithing_owed(move) == Decimal("0.00")
