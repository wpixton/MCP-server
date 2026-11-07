"""Adding a transaction: validate it, find the next empty row, write it, check it.

The steps, each its own function so each can be tested and explained alone:

    entry = validate(tracker, ...)             # refuse anything that isn't clearly right
    find_duplicate(tracker, entry)             # did Claude already add this one?
    saved = write_transaction(source, entry)   # first empty row, then the cells
    verify(load_tracker(source), saved)        # read it back from the sheet

Why find the empty row ourselves instead of using Google's "append"? The real
Income tab has hundreds of rows that hold only an unchecked checkbox. Google's
append would treat those as data and add the new row below all of them.
"""

from dataclasses import replace
from datetime import date
from decimal import Decimal

from . import layout
from .layout import EXPENSES, INCOME
from .tracker import Transaction, Tracker, cell, cents, is_blank, to_number

MAX_AMOUNT = Decimal("100000")  # anything bigger is almost certainly a typo
MAX_TEXT = 200
# Text starting with these is treated as a formula by spreadsheets. Refusing them
# stops "formula injection", e.g. a description of =IMPORTXML("http://...").
FORMULA_STARTS = ("=", "+", "-", "@")


class InvalidTransaction(ValueError):
    """The request can't be written as-is. The message says what to fix."""


def match_name(value: str, choices: list[str]) -> str | None:
    """The choice that matches `value` ignoring case and spaces, or None."""
    wanted = value.strip().lower()
    return next((choice for choice in choices if choice.lower() == wanted), None)


def clean_text(value: str | None, field: str, required: bool) -> str:
    text = (value or "").strip()
    if required and not text:
        raise InvalidTransaction(f"{field} is required.")
    if len(text) > MAX_TEXT:
        raise InvalidTransaction(f"{field} is too long ({len(text)} characters; the limit is {MAX_TEXT}).")
    if text.startswith(FORMULA_STARTS):
        raise InvalidTransaction(f"{field} can't start with {text[0]!r} (spreadsheets would treat it as a formula).")
    return text


def validate(tracker: Tracker, kind: str, description: str, amount, category: str,
             day: str | None, account: str | None, notes: str | None, today: date) -> Transaction:
    """Check every field and return a clean Transaction (row 0 = not written yet)."""
    if kind not in ("income", "expense"):
        raise InvalidTransaction(f'kind must be "income" or "expense", not {kind!r}.')

    description = clean_text(description, "description", required=True)
    notes = clean_text(notes, "notes", required=False)

    number = to_number(amount)
    if number is None or number <= 0:
        raise InvalidTransaction(f"amount must be a positive number, got {amount!r}. "
                                 "Use kind to say whether money came in or went out.")
    if cents(number) != number:
        raise InvalidTransaction(f"amount can't have fractions of a cent: {amount!r}.")
    if number > MAX_AMOUNT:
        raise InvalidTransaction(f"amount {number} is over ${MAX_AMOUNT:,}; that looks like a typo.")

    if kind == "income":
        choices, other_kind, other_choices = tracker.income_categories, "expense", tracker.expense_categories
    else:
        choices, other_kind, other_choices = tracker.expense_categories, "income", tracker.income_categories
    matched = match_name(category or "", choices)
    if matched is None:
        message = f"Unknown {kind} category {category!r}."
        if match_name(category or "", other_choices):
            message = f"{category!r} is an {other_kind} category, not an {kind} one."
        raise InvalidTransaction(f"{message} Valid {kind} categories: {', '.join(choices)}")

    if day is None or not str(day).strip():
        when = today
    else:
        try:
            when = date.fromisoformat(str(day).strip())
        except ValueError:
            raise InvalidTransaction(f"date must look like 2026-11-20, got {day!r}.") from None
    if when > today:
        raise InvalidTransaction(f"date {when} is in the future; only past or today's transactions can be added.")

    account_name = ""
    if account and account.strip():
        if kind == "income":
            raise InvalidTransaction("Income entries don't have an account column; leave account empty.")
        account_name = match_name(account, tracker.account_names)
        if account_name is None:
            raise InvalidTransaction(f"Unknown account {account!r}. Valid: {', '.join(tracker.account_names)}")

    return Transaction(kind=kind, date=when, description=description, category=matched,
                       amount=number, row=0, account=account_name, notes=notes)


def find_duplicate(tracker: Tracker, entry: Transaction) -> Transaction | None:
    """An existing transaction with the same kind, date, amount and description, if any."""
    existing = tracker.income if entry.kind == "income" else tracker.expenses
    for t in existing:
        if (t.date, t.amount, t.description.lower()) == (entry.date, entry.amount, entry.description.lower()):
            return t
    return None


def first_empty_row(source, table: layout.Table) -> int:
    """The first row whose Date, Description, Category and Amount are all blank.

    Checkbox and formula columns are ignored, so a row holding only an
    unchecked "Tithing Paid?" box counts as empty.
    """
    first = table.first_data_row
    (rows,) = source.read([(table.sheet, f"A{first}:D{layout.LAST_ROW}")])
    for offset, row in enumerate(rows):
        if all(is_blank(cell(row, letter)) for letter in "ABCD"):
            return first + offset
    next_row = first + len(rows)  # Google leaves trailing empty rows out
    if next_row > layout.LAST_ROW:
        raise InvalidTransaction(f"The {table.sheet} tab is full (row {layout.LAST_ROW} reached).")
    return next_row


def row_values(entry: Transaction, row: int) -> dict:
    """The cells to set on the new row, by column letter. Includes the row's formula column."""
    if entry.kind == "income":
        return {
            "A": entry.date, "B": entry.description, "C": entry.category, "D": entry.amount,
            "E": layout.INCOME_TITHING_FORMULA.format(r=row),
            "F": False,  # Tithing Paid? starts unchecked
            "H": entry.notes,
        }
    return {
        "A": entry.date, "B": entry.description, "C": entry.category, "D": entry.amount,
        "E": entry.account, "F": entry.notes,
        "G": layout.EXPENSES_MONTH_FORMULA.format(r=row),
    }


def write_transaction(source, entry: Transaction) -> Transaction:
    """Write the entry to the first empty row of its tab. Returns it with its row number."""
    table = INCOME if entry.kind == "income" else EXPENSES
    row = first_empty_row(source, table)
    source.write(table.sheet, row, row_values(entry, row))
    return replace(entry, row=row)


def verify(reloaded: Tracker, saved: Transaction) -> bool:
    """Given the tracker re-read after writing, check the new row says what we meant to write."""
    rows = reloaded.income if saved.kind == "income" else reloaded.expenses
    found = next((t for t in rows if t.row == saved.row), None)
    return found is not None and (found.date, found.description, found.category, found.amount) == \
        (saved.date, saved.description, saved.category, saved.amount)
