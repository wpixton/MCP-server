"""Tests for add_transaction: the writer module, both sources' write(), and the MCP tool.

Every test gets its own fresh copy of the fake sample, because these tests change it.
"""

import json
from datetime import date, datetime
from decimal import Decimal

import anyio
import openpyxl
import pytest
from mcp.client.client import Client

from finance_tracker import config, layout, server, writer
from finance_tracker.sample_tracker import build_sample_tracker
from finance_tracker.sources import GoogleSheetSource, WritesNotAllowed, XlsxSource
from finance_tracker.tracker import Month, load_tracker

TODAY = date(2026, 11, 20)


@pytest.fixture
def sample(monkeypatch, tmp_path):
    """A fresh fake tracker for this test; the server uses it and "today" is 20 Nov 2026."""
    path = build_sample_tracker(tmp_path / "tracker.xlsx", now=datetime(2026, 11, 20, 14, 0))
    monkeypatch.setenv(config.SAMPLE_PATH_VAR, str(path))
    monkeypatch.setattr(server, "today", lambda: TODAY)
    return path


def add(**arguments):
    """Call the add_transaction tool through a real MCP client (in memory)."""
    async def run():
        async with Client(server.server) as client:
            return await client.call_tool("add_transaction", arguments)
    return anyio.run(run)


def ok(result) -> dict:
    assert not result.is_error, result.content
    return json.loads(result.content[0].text)


def error_text(result) -> str:
    assert result.is_error
    return result.content[0].text


GROCERIES = {"kind": "expense", "description": "Grocery store", "amount": 23.45, "category": "Food"}


# --- Happy paths -----------------------------------------------------------------

def test_expense_goes_in_the_first_empty_row(sample):
    before = load_tracker(XlsxSource(sample))
    result = ok(add(**GROCERIES, account="Demo Credit Card"))

    expected_row = layout.EXPENSES.first_data_row + len(before.expenses)
    assert (result["tab"], result["row"], result["verified"]) == ("Expenses", expected_row, True)
    after = load_tracker(XlsxSource(sample))
    (new,) = [t for t in after.expenses if t.row == expected_row]
    assert (new.date, new.amount, new.category, new.account) == (TODAY, Decimal("23.45"), "Food", "Demo Credit Card")
    # The row's formula column is filled in, like a row typed by hand.
    assert openpyxl.load_workbook(sample)["Expenses"][f"G{expected_row}"].value.startswith("=IF(")


def test_expense_reports_the_budget_afterwards(sample):
    result = ok(add(**GROCERIES))
    budget = result["budget_this_month"]
    tracker = load_tracker(XlsxSource(sample))
    assert budget["category"] == "Food"
    assert budget["spent"] == float(tracker.total_spending(Month(2026, 11), "Food"))


def test_income_fills_the_first_checkbox_only_row(sample):
    before = load_tracker(XlsxSource(sample))
    result = ok(add(kind="income", description="Tutoring", amount=60, category="Side Income", date="2026-11-18"))

    # Right after the last real row -- NOT below the 40 checkbox-only rows.
    expected_row = layout.INCOME.first_data_row + len(before.income)
    assert result["row"] == expected_row
    ws = openpyxl.load_workbook(sample)["Income"]
    assert ws[f"F{expected_row}"].value is False  # tithing starts unpaid
    assert ws[f"E{expected_row}"].value.startswith("=IF(")  # tithing formula in place


def test_existing_rows_are_untouched(sample):
    before = load_tracker(XlsxSource(sample))
    ok(add(**GROCERIES))
    after = load_tracker(XlsxSource(sample))
    # Every row that existed before is identical afterwards, row for row.
    before_rows = {t.row: t for t in before.expenses}
    after_rows = {t.row: t for t in after.expenses}
    assert {row: after_rows[row] for row in before_rows} == before_rows
    assert len(after_rows) == len(before_rows) + 1
    assert after.income == before.income


def test_date_defaults_to_today_and_names_ignore_case(sample):
    result = ok(add(kind="expense", description="Pizza", amount=12, category="food", account="demo checking"))
    assert result["added"]["date"] == "2026-11-20"
    assert (result["added"]["category"], result["added"]["account"]) == ("Food", "Demo Checking")


# --- Refusals: clear message, nothing written ------------------------------------------

@pytest.mark.parametrize("changes, message", [
    ({"category": "Groceries"}, "Unknown expense category"),
    ({"kind": "income", "category": "Food"}, "is an expense category"),
    ({"amount": 0}, "positive"),
    ({"amount": -5}, "positive"),
    ({"amount": 12.345}, "fractions of a cent"),
    ({"amount": 250000}, "typo"),
    ({"date": "2026-11-21"}, "future"),
    ({"date": "11/20/2026"}, "2026-11-20"),
    ({"description": "   "}, "required"),
    ({"description": '=IMPORTXML("http://example.com")'}, "formula"),
    ({"notes": "+1 extra"}, "formula"),
    ({"account": "Bank of Nowhere"}, "Unknown account"),
    ({"kind": "income", "category": "Job", "account": "Demo Checking"}, "don't have an account"),
])
def test_bad_requests_are_refused_and_nothing_is_written(sample, changes, message):
    before = sample.read_bytes()
    assert message in error_text(add(**{**GROCERIES, **changes}))
    assert sample.read_bytes() == before


def test_duplicates_are_refused_unless_confirmed(sample):
    ok(add(**GROCERIES))
    assert "duplicate" in error_text(add(**GROCERIES))
    assert ok(add(**GROCERIES, allow_duplicate=True))["verified"] is True


def test_workbook_open_in_excel_gives_a_clear_message(sample, monkeypatch):
    def locked(self, filename):
        raise PermissionError(13, "The process cannot access the file")  # what Windows says

    monkeypatch.setattr(openpyxl.Workbook, "save", locked)
    before = sample.read_bytes()
    assert "open in Excel" in error_text(add(**GROCERIES))
    assert sample.read_bytes() == before


# --- The real sheet is locked twice ----------------------------------------------------

def test_real_sheet_refused_unless_writes_are_switched_on(sample, monkeypatch):
    monkeypatch.setenv(config.SHEET_ID_VAR, "SOME_SHEET")
    message = error_text(add(**GROCERIES))
    assert config.ALLOW_WRITES_VAR in message  # refused before anything touches Google


def test_switch_alone_is_not_enough_without_a_write_sign_in(sample, monkeypatch):
    monkeypatch.setenv(config.SHEET_ID_VAR, "SOME_SHEET")
    monkeypatch.setenv(config.ALLOW_WRITES_VAR, "yes")
    assert "--allow-writes" in error_text(add(**GROCERIES))


@pytest.mark.parametrize("value, allowed", [("yes", True), ("TRUE", True), ("1", True),
                                            ("no", False), ("ye", False), ("", False)])
def test_only_an_explicit_yes_switches_writes_on(monkeypatch, value, allowed):
    monkeypatch.setenv(config.ALLOW_WRITES_VAR, value)
    assert config.real_writes_allowed() is allowed


# --- Google write, with a stand-in service (no network) ------------------------------------

class StandInService:
    def __init__(self):
        self.body = None

    def spreadsheets(self):
        return self

    def values(self):
        return self

    def batchUpdate(self, spreadsheetId, body):
        self.body = body
        return self

    def execute(self):
        return {}


def test_google_write_sends_one_request_typed_like_a_person():
    service = StandInService()
    GoogleSheetSource("SHEET", service=service, write=True).write(
        "Expenses", 57, {"A": date(2026, 11, 20), "D": Decimal("23.45"), "G": "=IF(A57=\"\",\"\",1)", "F": None})
    assert service.body["valueInputOption"] == "USER_ENTERED"
    assert service.body["data"] == [
        {"range": "'Expenses'!A57", "values": [["2026-11-20"]]},
        {"range": "'Expenses'!D57", "values": [[23.45]]},
        {"range": "'Expenses'!G57", "values": [['=IF(A57="","",1)']]},
        {"range": "'Expenses'!F57", "values": [[""]]},
    ]


def test_google_source_opened_read_only_refuses_to_write():
    with pytest.raises(WritesNotAllowed):
        GoogleSheetSource("SHEET", service=StandInService()).write("Expenses", 57, {"A": 1})


# --- Finding the empty row with Google-shaped data -------------------------------------------

class RowsSource:
    def __init__(self, rows):
        self.rows = rows

    def read(self, ranges):
        return [self.rows]


def test_first_empty_row_skips_partial_rows_and_ignores_checkboxes():
    rows = [
        [46329, "Paycheck", "Job", 600],
        ["", "Half-typed row", "", ""],  # has a description: not empty
        [],  # empty
    ]
    assert writer.first_empty_row(RowsSource(rows), layout.INCOME) == 5


def test_first_empty_row_after_trimmed_rows():
    # Google leaves trailing empty rows out entirely.
    assert writer.first_empty_row(RowsSource([[46329, "Paycheck", "Job", 600]]), layout.INCOME) == 4
