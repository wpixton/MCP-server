---
name: monthly-budget-review
description: Produces a monthly budget review of the user's personal finance tracker using the finance-tracker MCP tools. It covers spending vs. budget for every category, what is over or close to budget, unusual spending, changes from the previous month, the biggest expenses, and tithing status, and ends with a few concrete suggestions. Use this skill whenever the user asks how a month went financially, wants a budget review, an end-of-month or month-to-date check-in, a spending recap, or asks things like "am I on budget?", "how did I do in October?", or "review my spending", even if they don't say "review" or name the tools.
---

# Monthly budget review

The finance-tracker tools return accurate numbers, but a pile of JSON isn't a review. Your job is to turn
those numbers into a short, honest report that separates real problems from noise, where every figure can be
traced back to a tool result.

## 1. Pick the month

- If the user names a month, use it (tools take `YYYY-MM`, e.g. `2026-10`).
- If they say "this month" or "so far", review the current month and call it **month to date**.
- If they don't say: during the first 7 days of a month, review the **previous** month (it's complete);
  otherwise review the current month to date.

State the month you chose in the first line so the user can redirect you. Reviewing a month that's only
a few days old makes everything look under budget, which is why the default leans toward complete months.

## 2. Gather the data

Call all six. They are read-only, so call them in parallel if you can:

| Tool | Arguments | What you get |
|---|---|---|
| `month_summary` | `month` | income, spending, net, savings rate, overall "unusually high" flag |
| `budget_status` | `month` | each category's budget, spent, remaining, status; `over_budget`, `close_to_budget` lists |
| `spending_by_category` | `month` | spending per category with its 3-month average and `unusually_high` flag |
| `compare_months` | `month` (it compares to the month before) | changes in income, spending and each category |
| `biggest_expenses` | `month`, `limit: 5` | the five largest purchases |
| `tithing_status` | `year` of the reviewed month | tithing owed, paid, unpaid, and unpaid entries |

If a tool returns an error (for example, the Google sign-in expired), stop and pass the error's fix on to
the user. A review missing half its data, presented as complete, is worse than no review.

## 3. Interpret carefully

These are the places where a quick reading of the numbers goes wrong:

- **Status meanings.** `OVER` = spent more than the budget. `Watch` = 80% or more used. `On track` = under 80%.
  `Set budget` = the budget is 0, meaning **no budget has been set**.
- **"Set budget" is not "over budget."** Spending in a category with no budget is *unbudgeted*, not
  overspending. If `total_spent` is higher than `total_budget`, check how much of that is unbudgeted
  spending before telling the user they overspent overall.
- **False alarms on fixed bills.** `unusually_high` compares this month to the average of the 3 months
  before. A fixed bill (rent, a subscription) that started partway through that window gets flagged even
  though nothing changed. If a flagged category is about the same as last month (`compare_months` change
  near zero), treat it as a regular bill, not a spike, and mention it briefly at most.
- **Month to date.** For the current month, compare spending with how much of the month has passed
  (day 10 of 30 ≈ 33%) before calling anything "on track", and remember that fixed bills like rent arrive
  early in the month. Say plainly that the month isn't over.
- **Transfers** between the user's own accounts are already excluded by every tool. Don't add them back.
- **Savings rate** can be negative (spent more than earned) or empty (no income that month). Say so plainly.
- **Only use numbers from the tool results.** If the user asks about something the tools don't cover
  (account balances, net worth, recurring bills), say that the review doesn't include it rather than estimating.

## 4. Write the review

Use this structure. It's meant to be read in under a minute, so keep each section short.

```markdown
## {Month name} budget review{ — month to date, if the month isn't over}

**Bottom line:** {1-2 sentences: income, spending, net and savings rate, plus the single most important takeaway.}

### Budget
| Category | Budget | Spent | Left | Status |
|---|---|---|---|---|
{every category that HAS a budget: OVER rows first, then Watch, then On track}

### Needs attention
- {each OVER or Watch category: how far over / how much is left, and the purchase(s) behind it from biggest_expenses}
- {unbudgeted spending in one line: categories and amounts, if any}
{If nothing needs attention, say so. That's the good news the user is hoping for.}

### Compared with {previous month name}
- {2-3 biggest changes from compare_months, with direction and size}

### Biggest expenses
1. {date} · {description} · {category} · {amount}

### Tithing ({year})
{owed / paid / unpaid. If anything is unpaid, list those entries with the tithing owed on each.
If nothing is unpaid, one line saying the user is caught up.}

### Suggestions
- {at most 3, each tied to a specific number above}
```

Show dollars with cents in the tables (`$1,234.56`). Whole dollars are fine in sentences. Suggestions
should come from the data: "Set a budget for Giving, which had $68 of spending and no budget" helps;
"try to spend less on food" doesn't.

## 5. Don't change anything

A review only reads. Don't call `add_transaction` during a review, even if you notice a transaction seems
to be missing. Point it out and let the user decide whether to add it, because writing to someone's
financial records should always be their call.
