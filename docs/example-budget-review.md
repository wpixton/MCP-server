# Example: the monthly budget review skill on sample data

> **All numbers here are fictional.** They come from the generated sample tracker (`sample_data/`), not a real account.

**Prompt:** *"can you do my monthly budget review for october 2026?"*

**Tool calls the skill made** (all read-only):
`month_summary(2026-10)` · `budget_status(2026-10)` · `spending_by_category(2026-10)` · `compare_months(2026-10)` · `biggest_expenses(2026-10, 5)` · `tithing_status(2026)`

**Claude's review:**

---

## October 2026 budget review

**Bottom line:** You earned $1,229.82, spent $1,028.34, and kept $201.48, a 16% savings rate. Nothing went over budget, but Housing, Food and Giving have each used more than 80% of their budgets.

### Budget
| Category | Budget | Spent | Left | Status |
|---|---|---|---|---|
| Housing | $500.00 | $475.00 | $25.00 | Watch |
| Food | $300.00 | $256.93 | $43.07 | Watch |
| Giving | $150.00 | $126.11 | $23.89 | Watch |
| Transportation | $120.00 | $78.76 | $41.24 | On track |
| Subscriptions | $25.00 | $18.98 | $6.02 | On track |
| Shopping | $100.00 | $41.71 | $58.29 | On track |
| Other | $75.00 | $20.17 | $54.83 | On track |
| Entertainment | $60.00 | $10.68 | $49.32 | On track |

### Needs attention
- **Housing (95% used):** this is the $475.00 rent on Oct 1, a fixed bill, so there's nothing to fix.
- **Food ($43.07 left):** three grocery trips ($70.28, $67.87 and $53.29) were the largest Food costs.
- **Giving ($23.89 left):** this is the $126.11 tithing payment on Oct 4.
- **School has no budget set**, but it had no spending this month, so there's no unbudgeted spending.
- Shopping shows as higher than its 3-month average ($41.71 vs $31.58), but it's about the same as September ($41.23), so it isn't a new spike.

### Compared with September
- Spending fell by $158.14 (from $1,186.48), almost all of it in Giving ($126.11 vs $280.83).
- Income dipped by $31.24, and net cash flow rose by $126.90 to $201.48.
- Food rose by $11.86; every other category moved by less than $7.

### Biggest expenses
1. Oct 1 · Rent · Housing · $475.00
2. Oct 4 · Tithing · Giving · $126.11
3. Oct 13 · Grocery store · Food · $70.28
4. Oct 15 · Grocery store · Food · $67.87
5. Oct 30 · Grocery store · Food · $53.29

### Tithing (2026)
Owed $910.26 · paid $848.20 · unpaid $62.06. October is fully paid. The one unpaid entry is the Nov 6 campus job paycheck ($62.06 of tithing).

### Suggestions
- Pay the $62.06 of tithing on the Nov 6 paycheck to stay caught up.
- Subscriptions has only $6.02 of room left, so any new subscription would put it over its $25 budget.
- Keep an eye on Food. At $256.93 it's up $11.86 from September and above its $242.06 three-month average, with $43.07 of room left.

---

**How this lines up with the skill's test case** (`evals/full-review-of-a-complete-month`):

| Check | Result |
|---|---|
| Called all six read tools for October 2026 (tithing for 2026) | ✅ |
| Has every section of the template | ✅ |
| Every dollar figure comes from, or is computed from, a tool result | ✅ |
| "Set budget" (School) described as having no budget, not as over budget | ✅ |
| Did not call `add_transaction` | ✅ |
