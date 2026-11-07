"""Tests for the fake sample tracker generator."""

from datetime import date, datetime

import openpyxl
import pytest

from finance_tracker import layout
from finance_tracker.layout import TRANSFER
from finance_tracker.sample_tracker import (
    ALL_DESCRIPTIONS, FAKE_ACCOUNTS, FAKE_BUDGETS, SPENDING_MULTIPLIER, TITHING_RATE, build_sample_tracker,
)

# A fixed "now" so these tests give the same answer every day: Friday 20 Nov 2026, 2:00 PM.
NOW = datetime(2026, 11, 20, 14, 0)
THIS_MONTH = date(2026, 11, 1)


@pytest.fixture(scope="module")
def workbook(tmp_path_factory):
    """Build the sample once for this whole file (it takes a moment)."""
    path = build_sample_tracker(tmp_path_factory.mktemp("sample") / "tracker.xlsx", now=NOW)
    return openpyxl.load_workbook(path)


def read_rows(wb, table: layout.Table) -> list[dict]:
    """Rows that hold a real record: a date or an amount (a lone checkbox doesn't count)."""
    ws = wb[table.sheet]
    rows = []
    for r in range(table.first_data_row, ws.max_row + 1):
        row = {field: ws[f"{table.col(field)}{r}"].value for field in table.fields}
        if row.get("date") is not None or row.get("amount") is not None:
            rows.append(row)
    return rows


def month_of(value) -> date:
    return date(value.year, value.month, 1)


# --- Same structure as the real sheet ----------------------------------------

def test_tabs_are_in_sheet_order(workbook):
    assert workbook.sheetnames == layout.SHEET_ORDER


@pytest.mark.parametrize("table", [
    layout.INCOME, layout.EXPENSES, layout.ACCOUNTS, layout.BUDGET, layout.CATEGORIES,
    layout.RECURRING, layout.NET_WORTH_SNAPSHOTS, layout.NET_WORTH_HISTORY,
], ids=lambda t: f"{t.sheet} row {t.header_row}")
def test_headers_match_layout(workbook, table):
    ws = workbook[table.sheet]
    assert [ws[f"{letter}{table.header_row}"].value for letter, _h, _f in table.columns] == \
           [header for _l, header, _f in table.columns]


def test_category_lists_and_settings(workbook):
    ws = workbook[layout.CATEGORIES_SHEET]
    column = lambda letter, n: [ws[f"{letter}{r}"].value for r in range(4, 4 + n)]
    assert column("A", len(layout.INCOME_CATEGORIES)) == layout.INCOME_CATEGORIES
    assert column("B", len(layout.EXPENSE_CATEGORIES)) == layout.EXPENSE_CATEGORIES
    assert column("C", len(layout.ACCOUNT_TYPES)) == layout.ACCOUNT_TYPES
    assert ws[layout.TITHING_RATE_CELL].value == TITHING_RATE
    assert workbook[layout.SETTINGS_SHEET][layout.MULTIPLIER_CELL].value == SPENDING_MULTIPLIER


def test_formula_columns_are_left_for_the_sheet(workbook):
    assert workbook[layout.INCOME_SHEET]["E3"].value.startswith("=IF(")
    assert workbook[layout.EXPENSES_SHEET]["G3"].value.startswith("=IF(")
    assert workbook[layout.BUDGET_SHEET]["C5"].value.startswith("=SUMIFS(")


def test_every_budget_category_has_a_round_number_budget(workbook):
    ws = workbook[layout.BUDGET_SHEET]
    rows = {ws[f"A{r}"].value: ws[f"B{r}"].value for r in range(5, 5 + len(layout.BUDGET_CATEGORIES))}
    assert list(rows) == layout.BUDGET_CATEGORIES
    assert all(isinstance(v, int) and v % 5 == 0 for v in rows.values())
    assert ws[f"A{5 + len(layout.BUDGET_CATEGORIES)}"].value == "TOTAL"


# --- The data is fake and well-formed ------------------------------------------

def test_only_fake_descriptions_and_accounts(workbook):
    rows = read_rows(workbook, layout.INCOME) + read_rows(workbook, layout.EXPENSES)
    assert {r["description"] for r in rows} <= ALL_DESCRIPTIONS
    fake_names = {name for name, *_ in FAKE_ACCOUNTS}
    assert {r["account"] for r in read_rows(workbook, layout.EXPENSES)} <= fake_names


def test_categories_are_valid(workbook):
    assert {r["category"] for r in read_rows(workbook, layout.INCOME)} <= set(layout.INCOME_CATEGORIES)
    assert {r["category"] for r in read_rows(workbook, layout.EXPENSES)} <= set(layout.EXPENSE_CATEGORIES)


def test_amounts_are_positive_with_at_most_cents(workbook):
    for row in read_rows(workbook, layout.INCOME) + read_rows(workbook, layout.EXPENSES):
        assert row["amount"] > 0
        assert round(row["amount"], 2) == row["amount"]


def test_six_months_of_history_and_nothing_in_the_future(workbook):
    rows = read_rows(workbook, layout.EXPENSES)
    assert all(r["date"] <= NOW for r in rows)
    assert {month_of(r["date"]) for r in rows} == {date(2026, m, 1) for m in range(6, 12)}


def test_expenses_are_in_date_order(workbook):
    dates = [r["date"] for r in read_rows(workbook, layout.EXPENSES)]
    assert dates == sorted(dates)


# --- Edge cases copied from the real sheet ----------------------------------------

def test_imported_expenses_have_a_time_and_manual_ones_dont(workbook):
    rows = read_rows(workbook, layout.EXPENSES)
    with_time = [r for r in rows if r["date"].time() != datetime.min.time()]
    assert with_time and all(r["notes"] == "Auto-Import" for r in with_time)
    assert any(r["description"] == "Rent" and r["date"].time() == datetime.min.time() for r in rows)


def test_income_tab_has_rows_with_only_an_unchecked_box(workbook):
    ws = workbook[layout.INCOME_SHEET]
    after_data = layout.INCOME.first_data_row + len(read_rows(workbook, layout.INCOME))
    assert ws[f"A{after_data}"].value is None and ws[f"D{after_data}"].value is None
    assert ws[f"F{after_data}"].value is False


def test_transfers_appear_in_income_and_expenses(workbook):
    assert any(r["category"] == TRANSFER for r in read_rows(workbook, layout.INCOME))
    assert any(r["category"] == TRANSFER for r in read_rows(workbook, layout.EXPENSES))


def test_liabilities_are_typed_as_negative_numbers(workbook):
    # The sheet's net worth formulas only add up if liabilities are negative numbers.
    ws = workbook[layout.ACCOUNTS_SHEET]
    accounts = [(ws[f"C{r}"].value, ws[f"G{r}"].value) for r in range(4, 4 + len(FAKE_ACCOUNTS))]
    assert all((balance < 0) == (sign == "Negative") for balance, sign in accounts)


# --- The story the tools will find --------------------------------------------------

def test_shopping_is_over_budget_this_month(workbook):
    spent = sum(r["amount"] for r in read_rows(workbook, layout.EXPENSES)
                if r["category"] == "Shopping" and month_of(r["date"]) == THIS_MONTH)
    assert spent > FAKE_BUDGETS["Shopping"]


def test_tithing_paid_for_past_months_but_not_this_month(workbook):
    for row in read_rows(workbook, layout.INCOME):
        if month_of(row["date"]) < THIS_MONTH:
            assert row["tithing_paid"] is True and row["tithing_paid_date"] is not None
        else:
            assert row["tithing_paid"] is False and row["tithing_paid_date"] is None


def test_tithing_payments_match_what_was_owed(workbook):
    income = read_rows(workbook, layout.INCOME)
    payments = [r for r in read_rows(workbook, layout.EXPENSES) if r["description"] == "Tithing"]
    assert payments
    for payment in payments:
        paid_on = payment["date"].date()
        owed = sum(r["amount"] * TITHING_RATE for r in income
                   if r["category"] != TRANSFER and r["tithing_paid_date"]
                   and r["tithing_paid_date"].date() == paid_on)
        assert payment["amount"] == pytest.approx(owed, abs=0.01)


# --- Repeatable and safe ---------------------------------------------------------------

def test_same_seed_gives_same_data(tmp_path):
    a = openpyxl.load_workbook(build_sample_tracker(tmp_path / "a.xlsx", now=NOW, seed=7))
    b = openpyxl.load_workbook(build_sample_tracker(tmp_path / "b.xlsx", now=NOW, seed=7))
    c = openpyxl.load_workbook(build_sample_tracker(tmp_path / "c.xlsx", now=NOW, seed=8))
    assert read_rows(a, layout.EXPENSES) == read_rows(b, layout.EXPENSES)
    assert read_rows(a, layout.EXPENSES) != read_rows(c, layout.EXPENSES)


def test_refuses_to_overwrite_an_existing_file(tmp_path):
    existing = tmp_path / "real_export.xlsx"
    existing.write_bytes(b"pretend this is a real export")
    with pytest.raises(FileExistsError):
        build_sample_tracker(existing, now=NOW)
    assert existing.read_bytes() == b"pretend this is a real export"
