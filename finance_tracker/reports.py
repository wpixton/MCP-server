"""What each tool reports, as plain dictionaries.

No MCP here: every function takes a Tracker (plus a month or other options)
and returns a dict that's easy to read as JSON. server.py wraps these as MCP
tools. Keeping them separate means the logic is tested without any MCP setup.

Money goes out as plain numbers (e.g. 166.52). Inside, everything is Decimal
and already rounded to the cent; float() is only the last step, for JSON.
"""

from decimal import Decimal

from .tracker import Month, Tracker, Transaction

TRANSFER_NOTE = "Transfers between your own accounts are not counted as income or spending."


def money(amount: Decimal) -> float:
    return float(amount)


def percent(part: Decimal, whole: Decimal) -> float | None:
    """part as a whole-number percent of whole, or None when whole is 0."""
    return None if whole == 0 else float(round(part / whole * 100))


def transaction_dict(t: Transaction) -> dict:
    result = {
        "date": t.date.isoformat(),
        "type": t.kind,
        "description": t.description,
        "category": t.category,
        "amount": money(t.amount),
    }
    if t.account:
        result["account"] = t.account
    if t.notes:
        result["notes"] = t.notes
    return result


def month_summary(tracker: Tracker, month: Month) -> dict:
    income = tracker.total_income(month)
    spending = tracker.total_spending(month)
    return {
        "month": str(month),
        "month_name": month.name,
        "income": money(income),
        "spending": money(spending),
        "net": money(income - spending),
        "savings_rate_percent": percent(income - spending, income),
        "spending_3_month_average": money(tracker.three_month_average(month)),
        "spending_unusually_high": tracker.is_unusually_high(month),
        "income_transactions": len(tracker.income_in(month)),
        "expense_transactions": len(tracker.expenses_in(month)),
        "note": TRANSFER_NOTE,
    }


def budget_status(tracker: Tracker, month: Month) -> dict:
    lines = tracker.budget_lines(month)
    total_budget = sum((line.budget for line in lines), Decimal(0))
    total_spent = sum((line.actual for line in lines), Decimal(0))
    return {
        "month": str(month),
        "month_name": month.name,
        "categories": [
            {
                "category": line.category,
                "budget": money(line.budget),
                "spent": money(line.actual),
                "remaining": money(line.remaining),
                "percent_used": None if line.percent_used is None else float(line.percent_used),
                "status": line.status,
            }
            for line in lines
        ],
        "total_budget": money(total_budget),
        "total_spent": money(total_spent),
        "total_remaining": money(total_budget - total_spent),
        "over_budget": [line.category for line in lines if line.status == "OVER"],
        "close_to_budget": [line.category for line in lines if line.status == "Watch"],
        "note": "Status rules: OVER = above budget, Watch = 80% or more used, Set budget = no budget entered. "
                + TRANSFER_NOTE,
    }


def spending_by_category(tracker: Tracker, month: Month) -> dict:
    totals = tracker.spending_by_category(month)
    total = sum(totals.values(), Decimal(0))
    categories = []
    for category, spent in sorted(totals.items(), key=lambda item: item[1], reverse=True):
        categories.append({
            "category": category,
            "spent": money(spent),
            "share_of_spending_percent": percent(spent, total),
            "three_month_average": money(tracker.three_month_average(month, category)),
            "unusually_high": tracker.is_unusually_high(month, category),
        })
    return {
        "month": str(month),
        "month_name": month.name,
        "total_spending": money(total),
        "categories": categories,
        "note": (f"unusually_high means more than {tracker.spending_multiplier}x the average of the 3 months "
                 f"before. {TRANSFER_NOTE}"),
    }


def compare_months(tracker: Tracker, month: Month, compare_to: Month) -> dict:
    def change(now: Decimal, before: Decimal) -> dict:
        return {"month": money(now), "compare_to": money(before), "change": money(now - before)}

    now_totals, before_totals = tracker.spending_by_category(month), tracker.spending_by_category(compare_to)
    categories = []
    for category in set(now_totals) | set(before_totals):
        row = change(now_totals.get(category, Decimal(0)), before_totals.get(category, Decimal(0)))
        categories.append({"category": category, **row})
    categories.sort(key=lambda row: (-abs(row["change"]), row["category"]))  # biggest swings first, ties A-Z

    income_now, income_before = tracker.total_income(month), tracker.total_income(compare_to)
    spent_now, spent_before = tracker.total_spending(month), tracker.total_spending(compare_to)
    return {
        "month": str(month),
        "compare_to": str(compare_to),
        "income": change(income_now, income_before),
        "spending": change(spent_now, spent_before),
        "net": change(income_now - spent_now, income_before - spent_before),
        "spending_by_category": categories,
        "note": "change = month minus compare_to; positive spending change means you spent more. " + TRANSFER_NOTE,
    }


def biggest_expenses(tracker: Tracker, month: Month, limit: int) -> dict:
    expenses = sorted(tracker.expenses_in(month), key=lambda t: t.amount, reverse=True)
    return {
        "month": str(month),
        "month_name": month.name,
        "expenses": [transaction_dict(t) for t in expenses[:limit]],
        "expenses_in_month": len(expenses),
        "note": TRANSFER_NOTE,
    }


def recent_transactions(tracker: Tracker, limit: int, kind: str = "all",
                        category: str | None = None, account: str | None = None) -> dict:
    pool = []
    if kind in ("all", "income"):
        pool += tracker.income
    if kind in ("all", "expense"):
        pool += tracker.expenses
    if category:
        pool = [t for t in pool if t.category == category]
    if account:
        pool = [t for t in pool if t.account == account]
    pool.sort(key=lambda t: (t.date, t.row), reverse=True)  # newest first
    return {
        "transactions": [transaction_dict(t) for t in pool[:limit]],
        "matching_transactions": len(pool),
        "filters": {"type": kind, "category": category, "account": account},
        "note": "Includes transfers (category Transfer) so the list matches the sheet.",
    }


def tithing_status(tracker: Tracker, year: int) -> dict:
    income = [t for t in tracker.income if t.date.year == year and not t.is_transfer]
    paid = [t for t in income if t.tithing_paid]
    unpaid = [t for t in income if not t.tithing_paid]
    owed_total = sum((tracker.tithing_owed(t) for t in income), Decimal(0))
    paid_total = sum((tracker.tithing_owed(t) for t in paid), Decimal(0))
    return {
        "year": year,
        "tithing_rate_percent": float(tracker.tithing_rate * 100),
        "income_counted": money(sum((t.amount for t in income), Decimal(0))),
        "tithing_owed": money(owed_total),
        "tithing_paid": money(paid_total),
        "tithing_unpaid": money(owed_total - paid_total),
        "unpaid_entries": [{**transaction_dict(t), "tithing_owed": money(tracker.tithing_owed(t))} for t in unpaid],
        "note": "Paid/unpaid comes from the Tithing Paid? checkbox on the Income tab. Transfers are not tithed.",
    }
