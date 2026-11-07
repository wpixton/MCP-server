"""Tests for the fake sample workbook generator and the workbook-path config."""

from datetime import datetime
from pathlib import Path

import openpyxl
import pytest

from key_checkout import config, layout
from key_checkout.sample_workbook import build_sample_workbook

# A fixed "now" so these tests give the same answer every day: Wednesday, 2:00 PM.
NOW = datetime(2026, 11, 4, 14, 0)


@pytest.fixture
def workbook(tmp_path):
    path = build_sample_workbook(tmp_path / "sample.xlsx", now=NOW)
    return openpyxl.load_workbook(path)


def used_log_rows(wb) -> list[dict]:
    """The Log rows that have something in them, as {field name: value}."""
    ws = wb[layout.LOG_SHEET]
    rows = []
    for r in range(layout.FIRST_DATA_ROW, layout.LOG_LAST_ROW + 1):
        row = {field: ws[f"{letter}{r}"].value for letter, _header, field in layout.LOG_COLUMNS}
        if row["scan_id"] or row["building"]:
            rows.append(row)
    return rows


def people_rows(wb) -> list[dict]:
    ws = wb[layout.PEOPLE_SHEET]
    rows = []
    for r in range(layout.FIRST_DATA_ROW, layout.PEOPLE_LAST_ROW + 1):
        row = {field: ws[f"{letter}{r}"].value for letter, _header, field in layout.PEOPLE_COLUMNS}
        if row["scan_id"]:
            rows.append(row)
    return rows


# --- Layout matches the template -------------------------------------------

def test_sheets_are_in_template_order(workbook):
    assert workbook.sheetnames == ["Key Board", "Log", "People", "Keys", "How To"]


@pytest.mark.parametrize("sheet, columns", [
    (layout.LOG_SHEET, layout.LOG_COLUMNS),
    (layout.PEOPLE_SHEET, layout.PEOPLE_COLUMNS),
    (layout.KEYS_SHEET, layout.KEYS_COLUMNS),
])
def test_headers_match_layout(workbook, sheet, columns):
    ws = workbook[sheet]
    assert [ws[f"{letter}1"].value for letter, _h, _f in columns] == [h for _l, h, _f in columns]


def test_keys_sheet_has_all_27_keys(workbook):
    ws = workbook[layout.KEYS_SHEET]
    keys = [ws[f"A{r}"].value for r in range(2, 29)]
    assert keys == layout.ALL_KEYS
    assert ws["C2"].value == "Hinckley"
    assert ws["C28"].value == "Building 9"


def test_formula_columns_are_left_for_excel(workbook):
    ws = workbook[layout.LOG_SHEET]
    # Formulas are pre-filled on every row, including the very last one...
    for r in (layout.FIRST_DATA_ROW, layout.LOG_LAST_ROW):
        assert ws[f"B{r}"].value.startswith("=IF(")
        assert "OVERDUE" in ws[f"R{r}"].value
    # ...and openpyxl only stores the formula text, not a calculated answer.
    # This is exactly why the read layer has to do the lookups in Python.


# --- The data is fake ---------------------------------------------------------

def test_people_are_obviously_fake(workbook):
    people = people_rows(workbook)
    assert len(people) == 12
    for person in people:
        assert person["phone"].startswith("801-555-01")  # 555-01xx is reserved for fiction
        assert person["byu_id"].startswith("99") and len(person["byu_id"]) == 9
    assert len({p["scan_id"] for p in people}) == len(people)  # no duplicate cards
    assert len({p["byu_id"] for p in people}) == len(people)


def test_every_log_row_matches_a_person(workbook):
    people = people_rows(workbook)
    card_ids = {p["scan_id"] for p in people}
    byu_ids = {p["byu_id"] for p in people}
    rows = used_log_rows(workbook)
    for row in rows:
        assert row["scan_id"] in card_ids | byu_ids
    # At least one person "forgot their card", so the BYU ID fallback gets exercised.
    assert any(row["scan_id"] in byu_ids for row in rows)


# --- The story makes sense ------------------------------------------------------

def test_log_has_returned_out_and_overdue_keys(workbook):
    rows = used_log_rows(workbook)
    returned = [r for r in rows if r["date_returned"] is not None]
    not_returned = [r for r in rows if r["date_returned"] is None]
    out_today = [r for r in not_returned if r["date_out"].date() == NOW.date()]
    overdue = [r for r in not_returned if r["date_out"].date() < NOW.date()]

    assert len(returned) >= 20
    assert len(out_today) == 2  # still before 5 PM, so these are just "Out"
    assert len(overdue) == 3  # went out on an earlier day and never came back


def test_no_key_is_out_twice(workbook):
    out_keys = [f'{r["building"]}{r["set_number"]}' for r in used_log_rows(workbook) if r["date_returned"] is None]
    assert len(out_keys) == len(set(out_keys))


def test_keys_come_back_after_they_go_out(workbook):
    for row in used_log_rows(workbook):
        if row["date_returned"] is not None:
            went_out = datetime.combine(row["date_out"].date(), row["time_out"])
            came_back = datetime.combine(row["date_returned"].date(), row["time_returned"])
            assert came_back > went_out
            assert came_back <= NOW


def test_log_is_in_time_order(workbook):
    times = [datetime.combine(r["date_out"].date(), r["time_out"]) for r in used_log_rows(workbook)]
    assert times == sorted(times)


def test_same_seed_gives_same_workbook(tmp_path):
    a = openpyxl.load_workbook(build_sample_workbook(tmp_path / "a.xlsx", now=NOW, seed=7))
    b = openpyxl.load_workbook(build_sample_workbook(tmp_path / "b.xlsx", now=NOW, seed=7))
    assert used_log_rows(a) == used_log_rows(b)


# --- Safety ---------------------------------------------------------------------

def test_refuses_to_overwrite_an_existing_file(tmp_path):
    existing = tmp_path / "real_log.xlsx"
    existing.write_bytes(b"pretend this is the real key log")
    with pytest.raises(FileExistsError):
        build_sample_workbook(existing, now=NOW)
    assert existing.read_bytes() == b"pretend this is the real key log"


# --- Config ---------------------------------------------------------------------

def test_default_workbook_is_the_sample(monkeypatch):
    monkeypatch.delenv(config.ENV_VAR, raising=False)
    assert config.get_workbook_path() == config.SAMPLE_WORKBOOK


def test_env_var_overrides_workbook_path(monkeypatch):
    monkeypatch.setenv(config.ENV_VAR, r'"C:\Desk\Helaman_Key_Checkout.xlsx"')  # quotes get stripped
    assert config.get_workbook_path() == Path(r"C:\Desk\Helaman_Key_Checkout.xlsx")
