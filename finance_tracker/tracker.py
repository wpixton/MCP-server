"""Turn the tracker's raw cells into clean Python objects, and apply its rules.

    tracker = load_tracker()           # fake sample, or the real sheet if FINANCE_SHEET_ID is set
    tracker.budget_lines(Month.parse("2026-11"))

The rules below are the same ones the sheet's formulas use, worked out in
Python from the typed-in columns only (the sheet's own formula results are
never trusted, because an .xlsx written by Python has no calculated values):

- "Transfer" is moving money between your own accounts: never income or spending.
- A month runs from the 1st up to (not including) the 1st of the next month.
- Budget status: "Set budget" if the budget is 0, "OVER" above budget,
  "Watch" at 80% or more, otherwise "On track".
- Tithing owed = amount x tithing rate, for every income row except Transfers.
- "Unusually high" = more than (average of the 3 months before) x multiplier.

Money is Decimal, not float: floats can't store cents exactly (0.1 + 0.2 is
0.30000000000000004), and money totals should never be off by a cent.
"""

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from . import layout
from .layout import ACCOUNTS, BUDGET, CATEGORIES, EXPENSES, INCOME, TRANSFER
from .sources import open_source

CENT = Decimal("0.01")
WATCH_AT = Decimal("0.8")  # budget status turns "Watch" at 80% used, same as the sheet
DEFAULT_TITHING_RATE = Decimal("0.10")  # used only if Categories!D4 is blank
DEFAULT_MULTIPLIER = Decimal("1.25")  # used only if Settings!D8 is blank
EXCEL_EPOCH = date(1899, 12, 30)  # "day 0" for Excel and Google Sheets date numbers


# ---------------------------------------------------------------------------
# Converting raw cells
# ---------------------------------------------------------------------------

def is_blank(value) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def to_date(value) -> date | None:
    """A cell -> a date (time of day dropped), or None if it isn't one."""
    if isinstance(value, datetime):  # check datetime first: a datetime is also a date
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, bool):  # True is also an int in Python; it's not a date
        return None
    if isinstance(value, (int, float)):  # Google sends dates as day counts, e.g. 46333.5
        return EXCEL_EPOCH + timedelta(days=int(value))
    if isinstance(value, str):
        for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%b %d, %Y"):
            try:
                return datetime.strptime(value.strip(), fmt).date()
            except ValueError:
                pass
    return None


def to_number(value) -> Decimal | None:
    """A cell -> a Decimal, or None. Accepts 12.5, "12.5" and "$1,234.50"."""
    if isinstance(value, bool) or is_blank(value):
        return None
    if isinstance(value, (int, float, Decimal)):
        return Decimal(str(value))  # str() first, so 12.33 stays exactly 12.33
    if isinstance(value, str):
        try:
            return Decimal(value.strip().replace("$", "").replace(",", ""))
        except InvalidOperation:
            return None
    return None


def cents(amount: Decimal) -> Decimal:
    """Round to the cent, the way people round money (0.005 -> 0.01)."""
    return amount.quantize(CENT, rounding=ROUND_HALF_UP)


def to_money(value) -> Decimal | None:
    number = to_number(value)
    return None if number is None else cents(number)


def to_bool(value) -> bool:
    if isinstance(value, str):
        return value.strip().upper() in ("TRUE", "YES")
    return value is True


def to_text(value) -> str:
    return "" if value is None else str(value).strip()


# ---------------------------------------------------------------------------
# Data objects
# ---------------------------------------------------------------------------

@dataclass(frozen=True, order=True)
class Month:
    """A calendar month. Tools take months as text like "2026-11"."""

    year: int
    month: int

    @classmethod
    def parse(cls, text: str) -> "Month":
        try:
            year, month = (int(part) for part in text.strip().split("-"))
        except ValueError:
            raise ValueError(f"Month must look like 2026-11, got {text!r}") from None
        if not 1 <= month <= 12:
            raise ValueError(f"Month number must be 1-12, got {text!r}")
        return cls(year, month)

    @classmethod
    def of(cls, day: date) -> "Month":
        return cls(day.year, day.month)

    def previous(self) -> "Month":
        return Month(self.year, self.month - 1) if self.month > 1 else Month(self.year - 1, 12)

    def next(self) -> "Month":
        return Month(self.year, self.month + 1) if self.month < 12 else Month(self.year + 1, 1)

    def contains(self, day: date) -> bool:
        return Month.of(day) == self

    @property
    def name(self) -> str:
        return f"{layout.MONTH_NAMES[self.month - 1]} {self.year}"

    def __str__(self) -> str:
        return f"{self.year}-{self.month:02d}"


@dataclass(frozen=True)
class Transaction:
    """One row from the Income or Expenses tab."""

    kind: str  # "income" or "expense"
    date: date
    description: str
    category: str
    amount: Decimal
    row: int  # the sheet row it came from, so problems can point to it
    account: str = ""  # expenses only
    notes: str = ""
    tithing_paid: bool = False  # income only
    tithing_paid_date: date | None = None  # income only

    @property
    def is_transfer(self) -> bool:
        return self.category == TRANSFER


def budget_status(budget: Decimal, actual: Decimal) -> str:
    """Same rule as the Budget tab's Status column."""
    if budget == 0:
        return "Set budget"
    if actual > budget:
        return "OVER"
    if actual >= budget * WATCH_AT:
        return "Watch"
    return "On track"


@dataclass(frozen=True)
class BudgetLine:
    """One category on the Budget tab, for one month."""

    category: str
    budget: Decimal
    actual: Decimal

    @property
    def remaining(self) -> Decimal:
        return self.budget - self.actual  # negative when over budget

    @property
    def percent_used(self) -> Decimal | None:
        return None if self.budget == 0 else (self.actual / self.budget * 100).quantize(Decimal("1"))

    @property
    def status(self) -> str:
        return budget_status(self.budget, self.actual)


@dataclass
class Tracker:
    """Everything the tools need from the sheet, already cleaned up."""

    income: list[Transaction]
    expenses: list[Transaction]
    budgets: dict[str, Decimal]  # category -> monthly target, in Budget-tab order
    income_categories: list[str]
    expense_categories: list[str]
    account_names: list[str]  # names only; balances are never loaded
    tithing_rate: Decimal
    spending_multiplier: Decimal
    source: str = ""
    skipped_rows: list[str] = field(default_factory=list)  # rows that couldn't be read, and why

    # --- Filtering ---

    def income_in(self, month: Month, include_transfers: bool = False) -> list[Transaction]:
        return [t for t in self.income if month.contains(t.date) and (include_transfers or not t.is_transfer)]

    def expenses_in(self, month: Month, include_transfers: bool = False) -> list[Transaction]:
        return [t for t in self.expenses if month.contains(t.date) and (include_transfers or not t.is_transfer)]

    # --- Totals (Transfers never count) ---

    def total_income(self, month: Month) -> Decimal:
        return sum((t.amount for t in self.income_in(month)), Decimal(0))

    def total_spending(self, month: Month, category: str | None = None) -> Decimal:
        """Spending in a month: all categories, or just one."""
        total = Decimal(0)
        for t in self.expenses_in(month):
            if category is None or t.category == category:
                total += t.amount
        return total

    def spending_by_category(self, month: Month) -> dict[str, Decimal]:
        """Total spent per category this month, for categories with any spending."""
        totals: dict[str, Decimal] = {}
        for t in self.expenses_in(month):
            totals[t.category] = totals.get(t.category, Decimal(0)) + t.amount
        return totals

    # --- "Is this unusual?" ---

    def three_month_average(self, month: Month, category: str | None = None) -> Decimal:
        """Average monthly spending over the 3 months BEFORE `month` (all categories, or one)."""
        earlier = [month.previous(), month.previous().previous(), month.previous().previous().previous()]
        return cents(sum((self.total_spending(m, category) for m in earlier), Decimal(0)) / 3)

    def is_unusually_high(self, month: Month, category: str | None = None) -> bool:
        """More than (3-month average x multiplier). No history means nothing to compare, so False."""
        average = self.three_month_average(month, category)
        return average > 0 and self.total_spending(month, category) > average * self.spending_multiplier

    # --- Budget and tithing ---

    def budget_lines(self, month: Month) -> list[BudgetLine]:
        return [BudgetLine(category, budget, self.total_spending(month, category))
                for category, budget in self.budgets.items()]

    def tithing_owed(self, income: Transaction) -> Decimal:
        if income.kind != "income" or income.is_transfer:
            return Decimal("0.00")
        return cents(income.amount * self.tithing_rate)


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

# Every range the tracker reads, all fetched in one go.
INCOME_RANGE = (INCOME.sheet, f"A{INCOME.first_data_row}:{INCOME.last_column}{layout.LAST_ROW}")
EXPENSES_RANGE = (EXPENSES.sheet, f"A{EXPENSES.first_data_row}:{EXPENSES.last_column}{layout.LAST_ROW}")
BUDGET_RANGE = (BUDGET.sheet, f"A{BUDGET.first_data_row}:B{BUDGET.first_data_row + 30}")
CATEGORIES_RANGE = (CATEGORIES.sheet, f"A{CATEGORIES.first_data_row}:D100")
MULTIPLIER_RANGE = (layout.SETTINGS_SHEET, f"{layout.MULTIPLIER_CELL}:{layout.MULTIPLIER_CELL}")
ACCOUNTS_RANGE = (ACCOUNTS.sheet, f"A{ACCOUNTS.first_data_row}:A{layout.ACCOUNTS_LAST_ROW}")
ALL_RANGES = [INCOME_RANGE, EXPENSES_RANGE, BUDGET_RANGE, CATEGORIES_RANGE, MULTIPLIER_RANGE, ACCOUNTS_RANGE]


def cell(row: list, letter: str):
    """The value in column `letter` of a row read from column A. Rows can be short (Google trims them)."""
    index = ord(letter) - ord("A")
    return row[index] if index < len(row) else None


def first_value(rows: list[list]):
    """The single value of a one-cell range, or None if it's empty."""
    return rows[0][0] if rows and rows[0] else None


def column(rows: list[list], letter: str) -> list[str]:
    """The non-blank text values in one column."""
    return [to_text(cell(row, letter)) for row in rows if not is_blank(cell(row, letter))]


def parse_transactions(rows: list[list], table: layout.Table, kind: str, skipped: list[str]) -> list[Transaction]:
    transactions = []
    for offset, row in enumerate(rows):
        row_number = table.first_data_row + offset
        raw_date, raw_amount = cell(row, table.col("date")), cell(row, table.col("amount"))

        # An empty row, or one holding only an unchecked "Tithing Paid?" box, isn't a record.
        if is_blank(raw_date) and is_blank(raw_amount):
            continue
        day, amount = to_date(raw_date), to_money(raw_amount)
        if day is None or amount is None:
            skipped.append(f"{table.sheet} row {row_number}: needs a valid date and amount")
            continue

        details = {}
        if kind == "income":
            details["tithing_paid"] = to_bool(cell(row, table.col("tithing_paid")))
            details["tithing_paid_date"] = to_date(cell(row, table.col("tithing_paid_date")))
        else:
            details["account"] = to_text(cell(row, table.col("account")))
        transactions.append(Transaction(
            kind=kind, date=day, amount=amount, row=row_number,
            description=to_text(cell(row, table.col("description"))),
            category=to_text(cell(row, table.col("category"))),
            notes=to_text(cell(row, table.col("notes"))),
            **details,
        ))
    return sorted(transactions, key=lambda t: (t.date, t.row))


def parse_budgets(rows: list[list]) -> dict[str, Decimal]:
    """Budget tab rows, top to bottom, stopping at the TOTAL row."""
    budgets = {}
    for row in rows:
        category = to_text(cell(row, "A"))
        if not category or category.upper() == "TOTAL":
            break
        budgets[category] = to_money(cell(row, "B")) or Decimal("0.00")
    return budgets


def load_tracker(source=None) -> Tracker:
    """Read the tracker. With no source given, uses config: real sheet if set, else the fake sample."""
    if source is None:
        source = open_source()

    income_rows, expense_rows, budget_rows, category_rows, multiplier_rows, account_rows = source.read(ALL_RANGES)
    skipped: list[str] = []

    tithing_rate = to_number(cell(category_rows[0], "D")) if category_rows else None  # Categories!D4
    multiplier = to_number(first_value(multiplier_rows))  # Settings!D8

    return Tracker(
        income=parse_transactions(income_rows, INCOME, "income", skipped),
        expenses=parse_transactions(expense_rows, EXPENSES, "expense", skipped),
        budgets=parse_budgets(budget_rows),
        income_categories=column(category_rows, "A"),
        expense_categories=column(category_rows, "B"),
        account_names=column(account_rows, "A"),
        tithing_rate=tithing_rate if tithing_rate is not None else DEFAULT_TITHING_RATE,
        spending_multiplier=multiplier if multiplier is not None else DEFAULT_MULTIPLIER,
        source=source.describe(),
        skipped_rows=skipped,
    )
