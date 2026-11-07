"""Generate a FAKE sample finance tracker.

It has the same tabs, header rows, columns, dropdowns and formulas as the real
Google Sheet, but every account, transaction and balance is made up. Budgets are
round numbers. Descriptions come only from the lists in this file.

Run it from the project folder:
    python -m finance_tracker.sample_tracker              -> sample_data/sample_finance_tracker.xlsx
    python -m finance_tracker.sample_tracker other.xlsx   -> a new file somewhere else

The data covers the 6 months up to "now". Re-run it whenever you want "this
month" to be the current month again.

What the data is set up to show:
- Shopping goes over budget this month (a big purchase), so budget_status and
  the 3-month-average check have something to flag.
- Income from earlier months has its tithing paid (and a matching "Tithing"
  expense under Giving); this month's income is still unpaid.
- Transfers appear in both Income and Expenses, to prove they're left out of totals.
- Like the real sheet: imported expenses carry a time of day, manual ones don't,
  and the Income tab has empty rows that hold only an unchecked checkbox.
"""

import calendar
import random
import sys
from datetime import date, datetime, time, timedelta
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation

from . import layout
from .config import DEFAULT_SAMPLE_PATH
from .layout import ACCOUNTS, BUDGET, CATEGORIES, EXPENSES, INCOME, NET_WORTH_HISTORY, NET_WORTH_SNAPSHOTS, RECURRING, TRANSFER

# ---------------------------------------------------------------------------
# Fake settings and data
# ---------------------------------------------------------------------------

TITHING_RATE = 0.10
SPENDING_MULTIPLIER = 1.25  # warn when a month is above 125% of its 3-month average
MONTHS_OF_HISTORY = 6

CHECKING = "Demo Checking"
CREDIT_CARD = "Demo Credit Card"

# (name, type, balance, sign). The sheet's formulas expect liabilities to be
# typed as NEGATIVE numbers with sign "Negative".
FAKE_ACCOUNTS = [
    (CHECKING, "Checking", 1850.00, "Positive"),
    ("Demo Savings", "Savings", 4200.00, "Positive"),
    ("Index Fund", "Stock Market", 2500.00, "Positive"),
    ("Cash", "Cash", 60.00, "Positive"),
    (CREDIT_CARD, "Credit card", -340.00, "Negative"),
]

FAKE_BUDGETS = {  # monthly targets, round numbers. School has none set (0), like real trackers often do.
    "Housing": 500, "Food": 300, "Transportation": 120, "School": 0, "Entertainment": 60,
    "Subscriptions": 25, "Shopping": 100, "Giving": 150, "Other": 75,
}

# Bills on a fixed day each month: (day, category, description, amount)
FIXED_BILLS = [
    (1, "Housing", "Rent", 475.00),
    (5, "Subscriptions", "Streaming service", 15.99),
    (12, "Subscriptions", "Cloud storage", 2.99),
    (15, TRANSFER, "Transfer to savings", 200.00),
]

# Everyday spending: (category, description, lowest, highest, times per month)
EVERYDAY_SPENDING = [
    ("Food", "Grocery store", 35, 80, 4),
    ("Food", "Pizza place", 8, 25, 2),
    ("Transportation", "Gas station", 25, 45, 2),
    ("Entertainment", "Movie theater", 10, 20, 1),
    ("Shopping", "Online store", 15, 45, 1),
    ("Other", "Laundromat", 5, 15, 2),
]

TEXTBOOKS = ("School", "Campus bookstore - textbooks", 140.00)  # August and January
BIG_PURCHASE = ("Shopping", "New headphones", 129.99)  # this month, to go over budget
TITHING_EXPENSE = ("Giving", "Tithing")

PAYCHECK = ("Job", "Campus job paycheck")
OTHER_INCOME = [  # (month number or None for "any month", category, description, amount)
    (8, "Scholarship", "Semester scholarship", 1500.00),
    (None, "Gift", "Birthday gift", 50.00),
    (None, "Refund", "Bookstore refund", 25.00),
    (None, TRANSFER, "Transfer from savings", 300.00),
]
SIDE_INCOME = ("Side Income", "Tutoring")

# Every description the generator can produce -- a test checks nothing else appears.
ALL_DESCRIPTIONS = (
    {d for _day, _cat, d, _amt in FIXED_BILLS}
    | {d for _cat, d, _lo, _hi, _n in EVERYDAY_SPENDING}
    | {TEXTBOOKS[1], BIG_PURCHASE[1], TITHING_EXPENSE[1], PAYCHECK[1], SIDE_INCOME[1]}
    | {d for _m, _cat, d, _amt in OTHER_INCOME}
)


# ---------------------------------------------------------------------------
# Building the fake transactions
# ---------------------------------------------------------------------------

def month_starts(now: datetime, count: int) -> list[date]:
    """The first day of each of the last `count` months, oldest first, ending with this month."""
    year, month = now.year, now.month
    starts = []
    for _ in range(count):
        starts.append(date(year, month, 1))
        year, month = (year, month - 1) if month > 1 else (year - 1, 12)
    return list(reversed(starts))


def next_month(day: date) -> date:
    return date(day.year + (day.month == 12), day.month % 12 + 1, 1)


def first_sunday(month_start: date) -> date:
    return month_start + timedelta(days=(6 - month_start.weekday()) % 7)


def random_day(rng: random.Random, month_start: date) -> date:
    days_in_month = calendar.monthrange(month_start.year, month_start.month)[1]
    return month_start.replace(day=rng.randint(1, days_in_month))


def money(rng: random.Random, low: float, high: float) -> float:
    return round(rng.uniform(low, high), 2)


def make_income(now: datetime, rng: random.Random) -> list[dict]:
    """Fake Income rows (layout.INCOME field names), oldest first. Tithing is filled in later."""
    months = month_starts(now, MONTHS_OF_HISTORY)
    rows = []

    # Paycheck every other Friday.
    payday = months[0] + timedelta(days=(4 - months[0].weekday()) % 7)  # first Friday
    while payday <= now.date():
        rows.append({"date": payday, "description": PAYCHECK[1], "category": PAYCHECK[0],
                     "amount": money(rng, 560, 680)})
        payday += timedelta(days=14)

    gift_month, refund_month, transfer_month = rng.sample(months[:-1], 3)
    any_month_picks = {"Gift": gift_month, "Refund": refund_month, TRANSFER: transfer_month}
    for month_start in months:
        # Tutoring in about half the months.
        if rng.random() < 0.5:
            rows.append({"date": random_day(rng, month_start), "description": SIDE_INCOME[1],
                         "category": SIDE_INCOME[0], "amount": float(rng.choice([40, 60, 80, 120]))})
        for month_number, category, description, amount in OTHER_INCOME:
            if month_start.month == month_number or any_month_picks.get(category) == month_start:
                rows.append({"date": random_day(rng, month_start), "description": description,
                             "category": category, "amount": amount})

    rows = [r for r in rows if r["date"] <= now.date()]
    rows.sort(key=lambda r: r["date"])
    return rows


def pay_tithing(income: list[dict], now: datetime) -> list[dict]:
    """Mark earlier months' tithing as paid on the first Sunday of the next month.

    Returns the matching "Tithing" expense rows. This month's income stays unpaid.
    """
    owed_by_month = {}
    for row in income:
        if row["category"] != TRANSFER:  # same rule as the sheet's Tithing Owed formula
            month_start = row["date"].replace(day=1)
            owed_by_month[month_start] = owed_by_month.get(month_start, 0) + row["amount"] * TITHING_RATE

    expenses = []
    for month_start, owed in sorted(owed_by_month.items()):
        paid_on = first_sunday(next_month(month_start))
        if paid_on > now.date():
            continue  # not paid yet
        for row in income:
            if row["date"].replace(day=1) == month_start:
                row["tithing_paid"] = True
                row["tithing_paid_date"] = paid_on
        expenses.append({"date": paid_on, "description": TITHING_EXPENSE[1], "category": TITHING_EXPENSE[0],
                         "amount": round(owed, 2), "account": CHECKING})
    for row in income:
        row.setdefault("tithing_paid", False)
    return expenses


def make_expenses(now: datetime, rng: random.Random) -> list[dict]:
    """Fake Expenses rows (layout.EXPENSES field names). Not sorted yet."""
    rows = []
    for month_start in month_starts(now, MONTHS_OF_HISTORY):
        # Bills you type in yourself: date only, no notes.
        for day, category, description, amount in FIXED_BILLS:
            rows.append({"date": month_start.replace(day=day), "description": description,
                         "category": category, "amount": amount, "account": CHECKING})
        if month_start.month in (1, 8):
            category, description, amount = TEXTBOOKS
            rows.append({"date": month_start.replace(day=20), "description": description,
                         "category": category, "amount": amount, "account": CHECKING})

        # Card purchases imported from the bank: they carry a time of day.
        for category, description, low, high, times in EVERYDAY_SPENDING:
            for _ in range(times):
                when = datetime.combine(random_day(rng, month_start), time(rng.randint(8, 21), rng.randint(0, 59)))
                account = CREDIT_CARD if rng.random() < 0.4 else CHECKING
                rows.append({"date": when, "description": description, "category": category,
                             "amount": money(rng, low, high), "account": account, "notes": "Auto-Import"})

    # This month's big purchase pushes Shopping over budget.
    category, description, amount = BIG_PURCHASE
    when = datetime.combine(now.date().replace(day=1), time(12, 0))
    rows.append({"date": when, "description": description, "category": category,
                 "amount": amount, "account": CREDIT_CARD, "notes": "Auto-Import"})

    return [r for r in rows if as_datetime(r["date"]) <= now]


def as_datetime(value) -> datetime:
    """Dates and datetimes both appear in the Date column; compare them as datetimes."""
    return value if isinstance(value, datetime) else datetime.combine(value, time())


def make_net_worth_history(now: datetime) -> list[dict]:
    """Ten weekly snapshots ending last Saturday, slowly trending up. Typed values, not formulas."""
    last_saturday = now.date() - timedelta(days=(now.weekday() - 5) % 7)
    rows = []
    for weeks_ago in range(9, -1, -1):
        assets = 8000 + 50 * (9 - weeks_ago)
        liabilities = 300 + 10 * (weeks_ago % 3)
        rows.append({"date": last_saturday - timedelta(weeks=weeks_ago),
                     "assets": float(assets), "liabilities": float(liabilities), "net_worth": float(assets - liabilities)})
    return rows


# ---------------------------------------------------------------------------
# Styling and small helpers
# ---------------------------------------------------------------------------

TITLE_FONT = Font(bold=True, size=14)
HEADER_FONT = Font(bold=True, color="FFFFFF")
HEADER_FILL = PatternFill("solid", fgColor="1F3864")
WRAP = Alignment(wrap_text=True, vertical="top")
DATE_FORMAT = layout.DATE_FORMAT
MONEY_FORMAT = layout.MONEY_FORMAT
SIGNED_MONEY_FORMAT = '"$"#,##0.00;[Red]"-$"#,##0.00'
PERCENT_FORMAT = "0%"

# Formula ranges copied from the real sheet.
CATEGORY_RANGE = {"income": "=Categories!$A$4:$A$100", "expense": "=Categories!$B$4:$B$100",
                  "account_type": "=Categories!$C$4:$C$100"}
ACCOUNT_RANGE = "=Accounts!$A$4:$A$20"
SELECTED_MONTH_START = "DATE($B$2,MATCH($D$2,Settings!$B$8:$B$19,0),1)"


def write_title(ws, text: str) -> None:
    ws["A1"] = text
    ws["A1"].font = TITLE_FONT


def write_headers(ws, table: layout.Table) -> None:
    for letter, header, _field in table.columns:
        cell = ws[f"{letter}{table.header_row}"]
        cell.value = header
        cell.font, cell.fill = HEADER_FONT, HEADER_FILL
        ws.column_dimensions[letter].width = max(12, len(header) + 4)
    ws.freeze_panes = f"A{table.first_data_row}"


def write_rows(ws, table: layout.Table, rows: list[dict]) -> int:
    """Write dicts keyed by field name, starting at the table's first data row. Returns the next free row."""
    r = table.first_data_row
    for row in rows:
        for field, value in row.items():
            ws[f"{table.col(field)}{r}"] = value
        r += 1
    return r


def dropdown(ws, cell_range: str, source: str) -> None:
    """source is either a range like "=Categories!$A$4:$A$100" or a list like '"Yes,No"'."""
    dv = DataValidation(type="list", formula1=source, allow_blank=True)
    ws.add_data_validation(dv)
    dv.add(cell_range)


def quoted_list(items) -> str:
    return '"' + ",".join(items) + '"'


def set_format(ws, columns: str, first_row: int, last_row: int, number_format: str) -> None:
    for letter in columns:
        for r in range(first_row, last_row + 1):
            ws[f"{letter}{r}"].number_format = number_format


# ---------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------

def add_dashboard(wb: Workbook, now: datetime) -> None:
    ws = wb.create_sheet(layout.DASHBOARD)
    write_title(ws, "💰 PERSONAL FINANCE DASHBOARD")
    for letter, target in zip("ACEGIK", ["Dashboard", "Income", "Expenses", "Accounts", "Budget", "Net Worth"]):
        ws[f"{letter}2"] = f"=HYPERLINK(\"#'{target}'!A1\",\"{target}\")"
    ws["A4"], ws["B4"], ws["C4"], ws["D4"] = "YEAR", now.year, "MONTH", layout.MONTH_NAMES[now.month - 1]
    ws["F4"], ws["G4"] = "CURRENT MONTH", '=TEXT(TODAY(),"mmmm yyyy")'
    ws["A6"] = ("Sample workbook: the real Dashboard is all formulas. The MCP server works out the same "
                "numbers in Python from the Income, Expenses and Budget tabs, so they are not repeated here.")
    ws["A6"].alignment = WRAP
    ws.freeze_panes = "A5"


def add_income(wb: Workbook, income: list[dict]) -> None:
    ws = wb.create_sheet(layout.INCOME_SHEET)
    write_title(ws, "Income & Tithing")
    write_headers(ws, INCOME)
    next_row = write_rows(ws, INCOME, income)
    # Like the real sheet: rows below the data hold only an unchecked checkbox.
    last_row = next_row + 40
    for r in range(INCOME.first_data_row, last_row + 1):
        if r >= next_row:
            ws[f"F{r}"] = False
        ws[f"E{r}"] = layout.INCOME_TITHING_FORMULA.format(r=r)
    set_format(ws, "AG", INCOME.first_data_row, last_row, DATE_FORMAT)
    set_format(ws, "DE", INCOME.first_data_row, last_row, MONEY_FORMAT)
    dropdown(ws, f"C3:C{layout.LAST_ROW}", CATEGORY_RANGE["income"])


def add_expenses(wb: Workbook, expenses: list[dict]) -> None:
    ws = wb.create_sheet(layout.EXPENSES_SHEET)
    write_title(ws, "Expenses (Optional)")
    write_headers(ws, EXPENSES)
    next_row = write_rows(ws, EXPENSES, expenses)
    for r in range(EXPENSES.first_data_row, next_row):
        ws[f"G{r}"] = layout.EXPENSES_MONTH_FORMULA.format(r=r)
    set_format(ws, "A", EXPENSES.first_data_row, next_row, DATE_FORMAT)
    set_format(ws, "D", EXPENSES.first_data_row, next_row, MONEY_FORMAT)
    dropdown(ws, f"C3:C{layout.LAST_ROW}", CATEGORY_RANGE["expense"])
    dropdown(ws, f"E3:E{layout.LAST_ROW}", ACCOUNT_RANGE)


def add_accounts(wb: Workbook, now: datetime) -> None:
    ws = wb.create_sheet(layout.ACCOUNTS_SHEET)
    write_title(ws, "Accounts & Balances")
    write_headers(ws, ACCOUNTS)
    rows = [{"name": name, "type": kind, "balance": balance, "last_updated": now.date(),
             "include_in_net_worth": "Yes", "balance_sign": sign}
            for name, kind, balance, sign in FAKE_ACCOUNTS]
    write_rows(ws, ACCOUNTS, rows)
    set_format(ws, "C", 4, layout.ACCOUNTS_LAST_ROW, SIGNED_MONEY_FORMAT)
    set_format(ws, "D", 4, layout.ACCOUNTS_LAST_ROW, DATE_FORMAT)
    dropdown(ws, "B4:B20", CATEGORY_RANGE["account_type"])
    dropdown(ws, "F4:F20", quoted_list(["Yes", "No"]))
    dropdown(ws, "G4:G20", quoted_list(["Positive", "Negative"]))


def add_categories(wb: Workbook) -> None:
    ws = wb.create_sheet(layout.CATEGORIES_SHEET)
    write_title(ws, "Categories & Lists")
    write_headers(ws, CATEGORIES)
    for column, names in (("A", layout.INCOME_CATEGORIES), ("B", layout.EXPENSE_CATEGORIES), ("C", layout.ACCOUNT_TYPES)):
        for r, name in enumerate(names, start=CATEGORIES.first_data_row):
            ws[f"{column}{r}"] = name
    ws[layout.TITHING_RATE_CELL] = TITHING_RATE
    ws[layout.TITHING_RATE_CELL].number_format = PERCENT_FORMAT


def add_settings(wb: Workbook) -> None:
    ws = wb.create_sheet(layout.SETTINGS_SHEET)
    write_title(ws, "Settings")
    ws["A3"], ws["B3"] = "Tithing Rate", "=Categories!D4"
    ws["B3"].number_format = PERCENT_FORMAT
    ws["A5"] = "Change the rate in Categories!D4 if needed."
    headers = ["Dashboard Year Options", "Month Options", "Recurring Categories", "Spending Warning Multiplier"]
    for letter, header in zip("ABCD", headers):
        ws[f"{letter}{layout.SETTINGS_HEADER_ROW}"] = header
        ws[f"{letter}{layout.SETTINGS_HEADER_ROW}"].font = Font(bold=True)
    for column, values in (("A", layout.YEAR_OPTIONS), ("B", layout.MONTH_NAMES), ("C", layout.RECURRING_CATEGORIES)):
        for r, value in enumerate(values, start=layout.SETTINGS_FIRST_ROW):
            ws[f"{column}{r}"] = value
    ws[layout.MULTIPLIER_CELL] = SPENDING_MULTIPLIER
    ws["D9"] = "Warn when a category/month is >125% of its comparison average."
    ws.freeze_panes = "A2"


def add_instructions(wb: Workbook) -> None:
    ws = wb.create_sheet(layout.INSTRUCTIONS)
    write_title(ws, "How to Use This Finance Tracker")
    steps = [
        ("1. Dashboard", "Pick a Year and Month for a detailed view."),
        ("2. Budget", "Set a monthly budget for each expense category. Actuals update for the selected month."),
        ("3. Spending warnings", "Spending above the recent normal range is flagged. Change the multiplier on Settings."),
        ("4. Recurring", "Add repeating income/expenses with a frequency; monthly equivalents are calculated."),
        ("5. Net Worth", "Keep balances current on Accounts. Liabilities are typed as negative numbers."),
        ("6. Sample data", "Every account, transaction and balance in this workbook is fictional."),
    ]
    for r, (label, text) in enumerate(steps, start=3):
        ws[f"A{r}"], ws[f"B{r}"] = label, text
        ws[f"A{r}"].font = Font(bold=True)
    ws.column_dimensions["A"].width = 22
    ws.column_dimensions["B"].width = 100
    ws.freeze_panes = "A2"


def add_budget(wb: Workbook, now: datetime) -> None:
    ws = wb.create_sheet(layout.BUDGET_SHEET)
    write_title(ws, "📊 Budget vs. Actual")
    ws["A2"], ws[layout.BUDGET_YEAR_CELL] = "Year", now.year
    ws["C2"], ws[layout.BUDGET_MONTH_CELL] = "Month", layout.MONTH_NAMES[now.month - 1]
    ws["F2"] = "Enter target monthly budgets in column B."
    dropdown(ws, layout.BUDGET_YEAR_CELL, "=Settings!$A$8:$A$24")
    dropdown(ws, layout.BUDGET_MONTH_CELL, "=Settings!$B$8:$B$19")
    write_headers(ws, BUDGET)

    first = BUDGET.first_data_row
    for r, category in enumerate(layout.BUDGET_CATEGORIES, start=first):
        ws[f"A{r}"] = category
        ws[f"B{r}"] = FAKE_BUDGETS[category]
        ws[f"C{r}"] = (f'=SUMIFS(Expenses!$D$3:$D$4999,Expenses!$C$3:$C$4999,$A{r},'
                       f'Expenses!$A$3:$A$4999,">="&{SELECTED_MONTH_START},'
                       f'Expenses!$A$3:$A$4999,"<"&EDATE({SELECTED_MONTH_START},1))')
        ws[f"D{r}"] = f"=B{r}-C{r}"
        ws[f"E{r}"] = f"=IFERROR(C{r}/B{r},0)"
        ws[f"F{r}"] = f'=IF(B{r}=0,"Set budget",IF(C{r}>B{r},"OVER",IF(C{r}>=B{r}*0.8,"Watch","On track")))'
    last = first + len(layout.BUDGET_CATEGORIES) - 1
    total = last + 1
    ws[f"A{total}"] = "TOTAL"
    ws[f"B{total}"], ws[f"C{total}"] = f"=SUM(B{first}:B{last})", f"=SUM(C{first}:C{last})"
    ws[f"D{total}"], ws[f"E{total}"] = f"=B{total}-C{total}", f"=IFERROR(C{total}/B{total},0)"
    ws[f"A{total}"].font = Font(bold=True)
    set_format(ws, "BCD", first, total, SIGNED_MONEY_FORMAT)
    set_format(ws, "E", first, total, PERCENT_FORMAT)


def add_recurring(wb: Workbook) -> None:
    """Empty, like the real tab, but with its checkboxes, formulas and dropdowns ready."""
    ws = wb.create_sheet(layout.RECURRING_SHEET)
    write_title(ws, "🔁 Recurring Income & Expenses")
    write_headers(ws, RECURRING)
    for r in range(RECURRING.first_data_row, 21):
        ws[f"H{r}"] = False
        # _xlfn. is how .xlsx files spell newer Excel functions like SWITCH.
        ws[f"J{r}"] = (f'=IFERROR(D{r}*_xlfn.SWITCH(E{r},"Weekly",52/12,"Biweekly",26/12,'
                       f'"Monthly",1,"Quarterly",1/3,"Yearly",1/12),0)')
    set_format(ws, "DJ", RECURRING.first_data_row, 20, MONEY_FORMAT)
    set_format(ws, "F", RECURRING.first_data_row, 20, DATE_FORMAT)
    dropdown(ws, "A4:A500", quoted_list(["Income", "Expense"]))
    dropdown(ws, "C4:C500", "=Settings!$C$8:$C$30")
    dropdown(ws, "E4:E500", quoted_list(layout.FREQUENCIES))
    dropdown(ws, "G4:G500", ACCOUNT_RANGE)


def add_net_worth(wb: Workbook, history: list[dict]) -> None:
    ws = wb.create_sheet(layout.NET_WORTH_SHEET)
    write_title(ws, "📈 Net Worth Tracker")
    ws["A3"], ws["B3"] = "Current Net Worth", '=SUMIFS(Accounts!$C$4:$C$20,Accounts!$F$4:$F$20,"Yes")'
    ws["D3"], ws["E3"] = "Assets / Positive", ('=SUMIFS(Accounts!$C$4:$C$20,Accounts!$F$4:$F$20,"Yes",'
                                              'Accounts!$G$4:$G$20,"Positive")')
    ws["G3"], ws["H3"] = "Liabilities / Negative", ('=-SUMIFS(Accounts!$C$4:$C$20,Accounts!$F$4:$F$20,"Yes",'
                                                   'Accounts!$G$4:$G$20,"Negative")')
    set_format(ws, "BEH", 3, 3, MONEY_FORMAT)

    write_headers(ws, NET_WORTH_SNAPSHOTS)
    first = history[0]
    write_rows(ws, NET_WORTH_SNAPSHOTS, [{"date": first["date"], "assets": first["assets"],
                                          "liabilities": first["liabilities"]}])
    ws["D6"] = "=B6-C6"  # safe: B6 and C6 are typed numbers, not live formulas
    ws["G5"] = "How to use"
    ws["G6"] = "1. Keep balances current on Accounts."
    ws["G7"] = "2. Mark accounts included in net worth."
    ws["G8"] = ("3. To add a snapshot, type the date plus the Assets and Liabilities shown in row 3 into the "
                "next empty row of the Date table. Type the numbers instead of formulas so the snapshot stays fixed.")

    write_headers(ws, NET_WORTH_HISTORY)
    end = write_rows(ws, NET_WORTH_HISTORY, history)
    set_format(ws, "A", 6, end, DATE_FORMAT)
    set_format(ws, "BCD", 6, end, MONEY_FORMAT)
    ws.freeze_panes = "A4"


# ---------------------------------------------------------------------------
# Putting it together
# ---------------------------------------------------------------------------

def make_data(now: datetime, seed: int) -> tuple[list[dict], list[dict], list[dict]]:
    """All the fake rows: (income, expenses, net worth history)."""
    rng = random.Random(seed)
    income = make_income(now, rng)
    expenses = make_expenses(now, rng) + pay_tithing(income, now)
    expenses.sort(key=lambda r: as_datetime(r["date"]))  # a real log is in date order
    return income, expenses, make_net_worth_history(now)


def build_sample_tracker(path: Path = DEFAULT_SAMPLE_PATH, now: datetime | None = None, seed: int = 42) -> Path:
    """Write a fake tracker to `path` and return the path.

    `now` and `seed` make the output repeatable, which is what the tests rely on.
    As a safety net it refuses to overwrite any existing file except this repo's
    own sample, so it can never clobber a real export by accident.
    """
    path = Path(path)
    if path.exists() and path.resolve() != DEFAULT_SAMPLE_PATH.resolve():
        raise FileExistsError(f"Refusing to overwrite existing file: {path}")

    now = now or datetime.now()
    income, expenses, history = make_data(now, seed)

    wb = Workbook()
    wb.remove(wb.active)  # drop the default empty "Sheet"
    add_dashboard(wb, now)
    add_income(wb, income)
    add_expenses(wb, expenses)
    add_accounts(wb, now)
    add_categories(wb)
    add_settings(wb)
    add_instructions(wb)
    add_budget(wb, now)
    add_recurring(wb)
    add_net_worth(wb, history)
    wb.active = 0
    wb.calculation.fullCalcOnLoad = True  # openpyxl can't calculate; ask Excel to on open

    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
    return path


def main() -> None:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_SAMPLE_PATH
    print(f"Wrote fake sample tracker to {build_sample_tracker(out)}")


if __name__ == "__main__":
    main()
