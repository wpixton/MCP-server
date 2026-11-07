"""Tests for reports.py: each tool's output, checked against the data layer."""

import json
from datetime import date, datetime

import pytest

from finance_tracker import reports
from finance_tracker.sample_tracker import build_sample_tracker
from finance_tracker.sources import XlsxSource
from finance_tracker.tracker import Month, load_tracker

NOW = datetime(2026, 11, 20, 14, 0)
NOV, OCT = Month(2026, 11), Month(2026, 10)


@pytest.fixture(scope="module")
def tracker(tmp_path_factory):
    path = build_sample_tracker(tmp_path_factory.mktemp("sample") / "tracker.xlsx", now=NOW)
    return load_tracker(XlsxSource(path))


def test_month_summary_adds_up(tracker):
    s = reports.month_summary(tracker, NOV)
    assert s["income"] == float(tracker.total_income(NOV))
    assert s["spending"] == float(tracker.total_spending(NOV))
    assert s["net"] == pytest.approx(s["income"] - s["spending"])
    assert s["savings_rate_percent"] == round((s["income"] - s["spending"]) / s["income"] * 100)


def test_budget_status_calls_out_problem_categories(tracker):
    b = reports.budget_status(tracker, NOV)
    assert len(b["categories"]) == 9
    assert "Shopping" in b["over_budget"]
    assert "Housing" in b["close_to_budget"]
    assert b["total_spent"] == pytest.approx(sum(c["spent"] for c in b["categories"]))


def test_spending_by_category_is_largest_first(tracker):
    s = reports.spending_by_category(tracker, NOV)
    spent = [c["spent"] for c in s["categories"]]
    assert spent == sorted(spent, reverse=True)
    assert sum(spent) == pytest.approx(s["total_spending"])
    assert "Transfer" not in [c["category"] for c in s["categories"]]
    shopping = next(c for c in s["categories"] if c["category"] == "Shopping")
    assert shopping["unusually_high"] is True


def test_compare_months_change_is_the_difference(tracker):
    c = reports.compare_months(tracker, NOV, OCT)
    assert (c["month"], c["compare_to"]) == ("2026-11", "2026-10")
    for row in c["spending_by_category"] + [c["income"], c["spending"], c["net"]]:
        assert row["change"] == pytest.approx(row["month"] - row["compare_to"])
    changes = [abs(row["change"]) for row in c["spending_by_category"]]
    assert changes == sorted(changes, reverse=True)


def test_biggest_expenses_are_largest_first_and_limited(tracker):
    b = reports.biggest_expenses(tracker, NOV, limit=3)
    amounts = [e["amount"] for e in b["expenses"]]
    assert len(amounts) == 3 and amounts == sorted(amounts, reverse=True)
    assert all(e["category"] != "Transfer" for e in b["expenses"])


def test_recent_transactions_newest_first_with_filters(tracker):
    everything = reports.recent_transactions(tracker, limit=50)
    dates = [t["date"] for t in everything["transactions"]]
    assert dates == sorted(dates, reverse=True)

    food = reports.recent_transactions(tracker, limit=50, kind="expense", category="Food")
    assert food["transactions"] and all(t["category"] == "Food" and t["type"] == "expense"
                                        for t in food["transactions"])
    pay = reports.recent_transactions(tracker, limit=5, kind="income")
    assert all(t["type"] == "income" for t in pay["transactions"])


def test_tithing_status_owed_is_paid_plus_unpaid(tracker):
    t = reports.tithing_status(tracker, 2026)
    assert t["tithing_owed"] == pytest.approx(t["tithing_paid"] + t["tithing_unpaid"])
    assert t["tithing_rate_percent"] == 10.0
    # In the sample only November's income is still unpaid.
    assert t["unpaid_entries"]
    assert all(date.fromisoformat(e["date"]).month == 11 for e in t["unpaid_entries"])


def test_every_report_turns_into_json(tracker):
    for report in (reports.month_summary(tracker, NOV), reports.budget_status(tracker, NOV),
                   reports.spending_by_category(tracker, NOV), reports.compare_months(tracker, NOV, OCT),
                   reports.biggest_expenses(tracker, NOV, 5), reports.recent_transactions(tracker, 10),
                   reports.tithing_status(tracker, 2026)):
        json.dumps(report)  # raises if anything (like a Decimal or date) slipped through
