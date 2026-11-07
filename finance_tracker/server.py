"""The MCP server: tools that understand William's budget.

Seven read-only tools, plus add_transaction, the only one that changes anything
(it adds one row; it never edits or deletes).

Claude Desktop starts it like this and talks to it over stdin/stdout:
    python -m finance_tracker.server

Each tool:
1. loads the tracker fresh (so it always sees the latest edits to the sheet),
2. checks its arguments and turns problems into a clear ToolError,
3. hands off to reports.py, which does the actual work.

The docstrings matter: they are the tool descriptions Claude reads when
deciding which tool to call, so they say WHEN to use each tool, not just what
it does. Parameter descriptions (the Field(...) text) end up in each tool's
input schema.

Nothing here may print to stdout -- stdout carries the MCP messages.
"""

from datetime import date
from typing import Annotated, Literal

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import Field

from . import reports, writer
from .google_sheets import SetupError
from .sources import WritesNotAllowed, open_source
from .tracker import Month, Tracker, load_tracker

INSTRUCTIONS = """\
Tools for William's personal finance tracker (a Google Sheet with Income, Expenses and Budget tabs).
- Months are written YYYY-MM (e.g. 2026-10). Leaving the month out means the current month.
- Amounts are US dollars. "Transfer" means moving money between his own accounts and never counts
  as income or spending.
- Budgets are one monthly target per expense category.
- Tithing is 10% of income (except transfers); the Income tab records whether each entry's tithing is paid.
Prefer these tools over reading the spreadsheet cell by cell: they apply the tracker's rules for you.
add_transaction is the only tool that changes anything. Use it only when the user asks to record a
transaction, and confirm unclear details with them first."""

server = MCPServer(name="finance-tracker", instructions=INSTRUCTIONS)

# The read tools only read. Clients can use this hint to call them without extra confirmation.
READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False)
# add_transaction changes the sheet, but only by adding a row -- it never edits or deletes.
ADDS_A_ROW = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False)

# Reusable parameter types. The description text is what Claude sees for each argument.
MonthArg = Annotated[str | None, Field(description='Month as YYYY-MM, e.g. "2026-10". Leave empty for the current month.')]
LimitArg = Annotated[int, Field(description="How many to return (1-50).", ge=1, le=50)]


def today() -> date:
    """Today's date. A function (not date.today() inline) so tests can pin "this month"."""
    return date.today()


def get_tracker() -> Tracker:
    try:
        return load_tracker()
    except (SetupError, FileNotFoundError) as error:
        raise ToolError(str(error)) from error


def pick_month(text: str | None) -> Month:
    if text is None or not text.strip():
        return Month.of(today())
    try:
        return Month.parse(text)
    except ValueError as error:
        raise ToolError(str(error)) from error


def pick_name(value: str | None, choices: list[str], what: str) -> str | None:
    """Match a category/account name ignoring case, or explain the valid choices."""
    if value is None or not value.strip():
        return None
    for choice in choices:
        if choice.lower() == value.strip().lower():
            return choice
    raise ToolError(f"Unknown {what} {value!r}. Valid {what} names: {', '.join(choices)}")


@server.tool(annotations=READ_ONLY)
def month_summary(month: MonthArg = None) -> dict:
    """Overview of one month: total income, total spending, net cash flow, savings rate, and whether
    spending is unusually high compared with the 3 months before.

    Use for big-picture questions like "How did I do in October?" or "Did I save money this month?".
    For where the money went, use spending_by_category; for budgets, use budget_status.
    """
    return reports.month_summary(get_tracker(), pick_month(month))


@server.tool(annotations=READ_ONLY)
def budget_status(month: MonthArg = None) -> dict:
    """Budget vs. actual for every expense category in a month: budget, spent, remaining, percent used,
    and status (OVER, Watch = 80%+ used, On track, or Set budget when no budget is entered).

    Use for "How much budget do I have left?", "Am I over budget on anything?", or
    "Can I afford to eat out again this month?". The result lists over-budget and close-to-budget
    categories separately so they are easy to call out.
    """
    return reports.budget_status(get_tracker(), pick_month(month))


@server.tool(annotations=READ_ONLY)
def spending_by_category(month: MonthArg = None) -> dict:
    """Where the money went in a month: total spent per category (largest first), each category's share,
    its average over the 3 months before, and whether it is unusually high.

    Use for "Where did my money go?", "What am I spending the most on?", or
    "Is any category higher than normal?".
    """
    return reports.spending_by_category(get_tracker(), pick_month(month))


@server.tool(annotations=READ_ONLY)
def compare_months(
    month: MonthArg = None,
    compare_to: Annotated[str | None, Field(
        description='Month to compare against, as YYYY-MM. Leave empty for the month before `month`.')] = None,
) -> dict:
    """Compare two months: income, spending and net for each, plus the change in every spending category
    (biggest changes first).

    Use for "Am I spending more than last month?" or "How does October compare to September?".
    With no arguments it compares this month to last month. Note the current month may be incomplete.
    """
    first = pick_month(month)
    second = pick_month(compare_to) if compare_to else first.previous()
    return reports.compare_months(get_tracker(), first, second)


@server.tool(annotations=READ_ONLY)
def biggest_expenses(month: MonthArg = None, limit: LimitArg = 5) -> dict:
    """The largest individual expenses in a month, biggest first, with date, description, category,
    amount and account. Transfers are left out.

    Use for "What were my biggest purchases this month?" or "What made Shopping so high?".
    """
    return reports.biggest_expenses(get_tracker(), pick_month(month), limit)


@server.tool(annotations=READ_ONLY)
def recent_transactions(
    limit: LimitArg = 10,
    kind: Annotated[Literal["all", "income", "expense"], Field(
        description='"income", "expense", or "all" (default).')] = "all",
    category: Annotated[str | None, Field(
        description='Only this category, e.g. "Food". Leave empty for all categories.')] = None,
    account: Annotated[str | None, Field(
        description='Only expenses from this account. Leave empty for all accounts.')] = None,
) -> dict:
    """The most recent transactions, newest first, optionally filtered by type, category or account.

    Use for "What did I spend on Food recently?", "Show my last 10 transactions", or
    "When did I last get paid?". Unlike the other tools, this list includes transfers.
    """
    tracker = get_tracker()
    all_categories = list(dict.fromkeys(tracker.income_categories + tracker.expense_categories))  # no repeats
    category = pick_name(category, all_categories, "category")
    account = pick_name(account, tracker.account_names, "account")
    return reports.recent_transactions(tracker, limit, kind, category, account)


@server.tool(annotations=READ_ONLY)
def tithing_status(
    year: Annotated[int | None, Field(description="Calendar year, e.g. 2026. Leave empty for this year.")] = None,
) -> dict:
    """Tithing for a year: income counted, tithing owed (10% of income except transfers), how much is
    marked paid, how much is still unpaid, and the specific income entries not yet paid.

    Use for "Am I caught up on tithing?" or "How much tithing do I still owe?".
    """
    return reports.tithing_status(get_tracker(), year or today().year)


@server.tool(annotations=ADDS_A_ROW)
def add_transaction(
    kind: Annotated[Literal["expense", "income"], Field(
        description='"expense" for money spent, "income" for money received.')],
    description: Annotated[str, Field(description='What it was, e.g. "Grocery store" or "Campus job paycheck".')],
    amount: Annotated[float, Field(description="Dollar amount, always positive (kind says which direction), e.g. 12.50.")],
    category: Annotated[str, Field(
        description='A category from the tracker, e.g. "Food" for expenses or "Job" for income. '
                    "An invalid one returns the list of valid categories.")],
    date: Annotated[str | None, Field(description="Date as YYYY-MM-DD. Leave empty for today. Can't be in the future.")] = None,
    account: Annotated[str | None, Field(
        description="Expenses only: which account paid, as named on the Accounts tab. Optional.")] = None,
    notes: Annotated[str | None, Field(description="Optional note.")] = None,
    allow_duplicate: Annotated[bool, Field(
        description="Set true only if the user confirms they really want a second identical entry.")] = False,
) -> dict:
    """Add ONE income or expense entry to the tracker (a new row on the Income or Expenses tab).

    Only call this when the user clearly asks to add or record a transaction. If the amount, category or
    date is unclear, ask the user first instead of guessing. It refuses invalid categories, non-positive
    amounts, future dates, and an exact duplicate of an existing entry (same date, amount and description)
    unless allow_duplicate is true. After writing, it reads the row back to confirm, and for expenses it
    reports where that category's budget stands this month.

    Use for "Add a $12 Food expense from today" or "Record my $600 paycheck from Friday".
    It writes to the fake sample workbook unless writing to the real Google Sheet has been switched on.
    """
    try:
        source = open_source(for_writing=True)  # refuses the real sheet unless writes are allowed
        tracker = load_tracker(source)
        entry = writer.validate(tracker, kind, description, amount, category, date, account, notes, today())
        duplicate = writer.find_duplicate(tracker, entry)
        if duplicate and not allow_duplicate:
            raise writer.InvalidTransaction(
                f"This looks like a duplicate of {duplicate.kind} row {duplicate.row} "
                f"({duplicate.date}, {duplicate.description}, ${duplicate.amount}). "
                "Nothing was added. Call again with allow_duplicate=true only if the user confirms.")
        saved = writer.write_transaction(source, entry)
        reloaded = load_tracker(source)  # one read-back, used to verify and for the budget summary
        verified = writer.verify(reloaded, saved)
    except (writer.InvalidTransaction, WritesNotAllowed, SetupError, FileNotFoundError) as error:
        raise ToolError(str(error)) from error
    except PermissionError as error:
        raise ToolError("Couldn't save: the workbook is open in Excel (or another program). "
                        "Close it and try again. Nothing was added.") from error

    result = {
        "added": reports.transaction_dict(saved),
        "tab": "Income" if saved.kind == "income" else "Expenses",
        "row": saved.row,
        "written_to": source.describe(),
        "verified": verified,
    }
    if saved.kind == "expense" and saved.category in reloaded.budgets:
        lines = reloaded.budget_lines(Month.of(saved.date))
        line = next(budget_line for budget_line in lines if budget_line.category == saved.category)
        result["budget_this_month"] = {
            "category": line.category, "budget": float(line.budget), "spent": float(line.actual),
            "remaining": float(line.remaining), "status": line.status,
        }
    return result


def main() -> None:
    server.run()  # stdio by default: what Claude Desktop uses


if __name__ == "__main__":
    main()
