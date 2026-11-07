"""The tracker's layout: tab names, header rows, columns, and category lists.

This is the single source of truth for "where things live" in the finance
tracker. The sample generator, the data layer and the write tools all import
from here, so if the real sheet ever moves a column there's one place to fix.

It describes STRUCTURE only. No real amounts, balances or payees belong here.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Table:
    """A block of rows on one tab: a header row, then one record per row below it."""

    sheet: str
    header_row: int
    columns: tuple  # (column letter, header text exactly as in the sheet, field name)

    @property
    def first_data_row(self) -> int:
        return self.header_row + 1

    def col(self, field: str) -> str:
        """Column letter for a field name, e.g. EXPENSES.col("amount") -> "D"."""
        for letter, _header, name in self.columns:
            if name == field:
                return letter
        raise KeyError(f"{self.sheet} has no field {field!r}")

    @property
    def fields(self) -> list[str]:
        return [name for _letter, _header, name in self.columns]

    @property
    def last_column(self) -> str:
        return self.columns[-1][0]


# --- Tabs, in the order they appear in the sheet ---
DASHBOARD = "Dashboard"
INCOME_SHEET = "Income"
EXPENSES_SHEET = "Expenses"
ACCOUNTS_SHEET = "Accounts"
CATEGORIES_SHEET = "Categories"
SETTINGS_SHEET = "Settings"
INSTRUCTIONS = "Instructions"
BUDGET_SHEET = "Budget"
RECURRING_SHEET = "Recurring"
NET_WORTH_SHEET = "Net Worth"

SHEET_ORDER = [
    DASHBOARD, INCOME_SHEET, EXPENSES_SHEET, ACCOUNTS_SHEET, CATEGORIES_SHEET,
    SETTINGS_SHEET, INSTRUCTIONS, BUDGET_SHEET, RECURRING_SHEET, NET_WORTH_SHEET,
]

# The sheet's own formulas stop at row 4999, so nothing below that is ever counted.
LAST_ROW = 4999

# --- Tables ---
# Columns marked "formula" are calculated by the sheet. The data layer ignores
# them and works the numbers out in Python from the typed-in columns.

INCOME = Table(INCOME_SHEET, header_row=2, columns=(
    ("A", "Date", "date"),
    ("B", "Source / Description", "description"),
    ("C", "Category", "category"),  # dropdown: Categories column A
    ("D", "Amount", "amount"),
    ("E", "Tithing Owed", "tithing_owed"),  # formula: Amount x tithing rate (not for Transfer)
    ("F", "Tithing Paid?", "tithing_paid"),  # checkbox
    ("G", "Tithing Paid Date", "tithing_paid_date"),
    ("H", "Notes", "notes"),
))

EXPENSES = Table(EXPENSES_SHEET, header_row=2, columns=(
    ("A", "Date", "date"),  # imported rows also carry a time of day
    ("B", "Description", "description"),
    ("C", "Category", "category"),  # dropdown: Categories column B
    ("D", "Amount", "amount"),  # always positive
    ("E", "Account", "account"),  # dropdown: Accounts column A
    ("F", "Notes", "notes"),
    ("G", "Month", "month"),  # formula: "yyyy-mm"
))

ACCOUNTS = Table(ACCOUNTS_SHEET, header_row=3, columns=(
    ("A", "Account", "name"),
    ("B", "Type", "type"),  # dropdown: Categories column C
    ("C", "Current Balance", "balance"),
    ("D", "Last Updated", "last_updated"),
    ("E", "Notes", "notes"),
    ("F", "Include in Net Worth?", "include_in_net_worth"),  # Yes / No
    ("G", "Balance Sign", "balance_sign"),  # Positive / Negative
))
ACCOUNTS_LAST_ROW = 20  # other tabs' formulas look at Accounts rows 4-20

BUDGET = Table(BUDGET_SHEET, header_row=4, columns=(
    ("A", "Category", "category"),
    ("B", "Budget", "budget"),  # the monthly target you type in
    ("C", "Actual", "actual"),  # formula
    ("D", "Variance", "variance"),  # formula
    ("E", "% Used", "pct_used"),  # formula
    ("F", "Status", "status"),  # formula: Set budget / OVER / Watch / On track
))
BUDGET_YEAR_CELL = "B2"  # which month the Budget tab is showing
BUDGET_MONTH_CELL = "D2"

CATEGORIES = Table(CATEGORIES_SHEET, header_row=3, columns=(
    ("A", "Income Categories", "income"),
    ("B", "Expense Categories", "expense"),
    ("C", "Account Types", "account_type"),
    ("D", "Tithing Rate", "tithing_rate"),  # only D4 is used
))
TITHING_RATE_CELL = "D4"

RECURRING = Table(RECURRING_SHEET, header_row=3, columns=(
    ("A", "Type", "type"),  # Income / Expense
    ("B", "Description", "description"),
    ("C", "Category", "category"),
    ("D", "Amount", "amount"),
    ("E", "Frequency", "frequency"),
    ("F", "Next Due", "next_due"),
    ("G", "Account", "account"),
    ("H", "Active?", "active"),  # checkbox
    ("I", "Notes", "notes"),
    ("J", "Monthly Equivalent", "monthly_equivalent"),  # formula
))

NET_WORTH_SNAPSHOTS = Table(NET_WORTH_SHEET, header_row=5, columns=(
    ("A", "Snapshot Date", "date"),
    ("B", "Total Assets", "assets"),
    ("C", "Total Liabilities", "liabilities"),
    ("D", "Net Worth", "net_worth"),
    ("E", "Notes", "notes"),
))

NET_WORTH_HISTORY = Table(NET_WORTH_SHEET, header_row=9, columns=(
    ("A", "Date", "date"),
    ("B", "Assets", "assets"),
    ("C", "Liabilities", "liabilities"),
    ("D", "Net Worth", "net_worth"),
))

# Formulas a new row needs, copied from the real sheet. {r} is the row number.
INCOME_TITHING_FORMULA = '=IF(OR(D{r}="",C{r}="Transfer"),"",D{r}*Categories!$D$4)'
EXPENSES_MONTH_FORMULA = '=IF(A{r}="","",TEXT(A{r},"yyyy-mm"))'

# Cell formats used by the sheet.
DATE_FORMAT = "mmm d, yyyy"
MONEY_FORMAT = '"$"#,##0.00'

# --- Settings tab ---
SETTINGS_HEADER_ROW = 7
SETTINGS_FIRST_ROW = 8
MULTIPLIER_CELL = "D8"  # "Spending Warning Multiplier", e.g. 1.25 = warn above 125%

# --- Lists (category names are structure, not financial data) ---
TRANSFER = "Transfer"  # moving money between your own accounts; never counts as income or spending

INCOME_CATEGORIES = ["Job", "Scholarship", "Side Income", "Gift", "Refund", "Other", TRANSFER]
EXPENSE_CATEGORIES = [
    "Housing", "Food", "Transportation", "School", "Entertainment",
    "Subscriptions", "Shopping", "Giving", "Other", TRANSFER,
]
BUDGET_CATEGORIES = [c for c in EXPENSE_CATEGORIES if c != TRANSFER]  # the 9 rows on the Budget tab
ACCOUNT_TYPES = ["Checking", "Savings", "Stock Market", "Cash", "Other", "Liability", "Credit card"]
RECURRING_CATEGORIES = [  # Settings column C, in the sheet's order
    "Job", "Scholarship", "Side Income", "Gift", "Refund", "Other",
    "Housing", "Food", "Transportation", "School", "Entertainment",
    "Subscriptions", "Shopping", "Giving",
]
FREQUENCIES = ["Weekly", "Biweekly", "Monthly", "Quarterly", "Yearly"]
MONTH_NAMES = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]
YEAR_OPTIONS = list(range(2020, 2037))
