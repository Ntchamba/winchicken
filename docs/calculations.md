# Backend calculations

Every formula below is transcribed from the real source (file:function references point at
`backend/apps/...`), not from the spec documents. Where the coded formula differs from
`winchicken-spec-implementation-detaillee.docx` section 5, that is called out explicitly.
None of these figures are stored pre-aggregated anywhere except `BatchClosingReport`
(a deliberate snapshot, written once at batch closing) — everything else is computed
at request time from `DailyLog`/`StockMovement`/`Expense`/`Sale`/`PurchaseOrder` rows.

## apps/batches/calculations.py — livestock KPIs

Reference constants used throughout this module:

```python
FCR_REFERENCE_RANGE = (2.10, 2.30)        # favorable .. unfavorable
MORTALITY_REFERENCE_RANGE = (3, 5)        # % favorable .. unfavorable
```

### `mortality_pct(batch)` — `apps/batches/calculations.py:mortality_pct`

```python
total_mortality = sum(log.mortality for log in batch.daily_logs.all())
return round(total_mortality / batch.initial_count * 100, 2)   # 0.0 if initial_count is 0
```

Cumulative mortality since batch start, as a percentage of `PoultryBatch.initial_count`
(not `current_count`). Matches the spec formula exactly. Returns `0.0`, not an error or
`None`, when `initial_count` is falsy.

### `feed_conversion_ratio(batch, up_to_date=None)` — `apps/batches/calculations.py:feed_conversion_ratio`

```python
logs = batch.daily_logs.all()
if up_to_date:
    logs = [log for log in logs if log.log_date <= up_to_date]
total_feed = sum(log.feed_consumed_kg for log in logs)
latest_weight = last non-null avg_sample_weight among `logs`, sorted by log_date ascending
if not latest_weight or not batch.current_count:
    return None
return round(total_feed / (batch.current_count * latest_weight), 2)
```

Total feed consumed (in the `logs` window) divided by an *estimated* live weight, computed
as `current_count * latest_weight` — the batch's live bird count *right now* (not at
`up_to_date`) times the most recent sample weight *as of* `up_to_date`. This mixes a
point-in-time `current_count` into a formula otherwise restricted to `up_to_date`, which
matters for `weekly_kpi`'s per-week FCR (see below): every week's FCR uses the batch's
*current* `current_count`, not that week's actual live count — so early-week FCR numbers
will drift if the batch has since lost birds to mortality. Not called out anywhere in the
spec, but implied by the formula's literal wording (`PoultryBatch.currentCount`) — this
is a documented reading of an ambiguous spec formula, not obviously a bug. Returns `None`
(never a fabricated `0`) if there's no sample weight yet or `current_count` is `0`.

### `week_number(batch, log_date)` — `apps/batches/calculations.py:week_number`

```python
return (log_date - batch.start_date).days // 7 + 1
```

1-indexed: days 1–7 relative to `start_date` = week 1.

### `weekly_kpi(batch)` — `apps/batches/calculations.py:weekly_kpi`

Backs `GET /api/batches/{batchCode}/kpi/weekly/`. Groups `DailyLog` rows by `week_number`,
then per week:

```python
mortalityPct       = round(week_mortality / batch.initial_count * 100, 2)  # week_mortality = SUM(mortality) that week
feedConversionRatio = feed_conversion_ratio(batch, up_to_date=<last log_date in that week>)
avgWeightKg         = the week's most recent non-null avg_sample_weight (or null)
```

Output shape matches implementation-detail spec section 11.1 exactly (`batchCode`, `weeks[]`,
`referenceRange`), including the two static reference bands
(`FCR_REFERENCE_RANGE`, `MORTALITY_REFERENCE_RANGE`) echoed back in every response rather
than computed per batch.

### `build_closing_report(batch)` — `apps/batches/calculations.py:build_closing_report`

Backs `PATCH /api/batches/{batchCode}/close/`. Persists a `BatchClosingReport` via
`update_or_create` (so re-running it, e.g. from a retry, recomputes rather than duplicates —
though the view itself already blocks closing an already-closed batch with a 400).

```python
variable_categories = ['FEED', 'VETERINARY', 'MISC']
fixed_categories     = ['DEPRECIATION', 'LABOR']

total_variable_cost   = SUM(Expense.amount WHERE batch=X AND category IN variable_categories)
allocated_fixed_cost  = SUM(Expense.amount WHERE batch=X AND category IN fixed_categories)
revenue                = SUM(Sale.total_amount WHERE batch=X)
unit_cost_price        = total_variable_cost / batch.current_count   (None if current_count == 0)
gross_margin            = revenue - total_variable_cost
net_margin              = gross_margin - allocated_fixed_cost         # persisted as total_margin

BatchClosingReport.total_mortality_pct    = mortality_pct(batch)
BatchClosingReport.feed_conversion_ratio  = feed_conversion_ratio(batch)   # no up_to_date -> uses all logs
```

Matches the spec's variable/fixed cost category split and formulas (section 5.3) exactly,
including `unit_cost_price` being divided by `current_count` (the *closing* count, per the
spec's "à la clôture" note) rather than `initial_count`.

### `bfr_estimate(batch, as_of_date)` — `apps/batches/calculations.py:bfr_estimate`

```python
cumulative_expense = SUM(Expense.amount WHERE batch=X AND expense_date <= as_of_date)
cumulative_sales    = SUM(Sale.total_amount WHERE batch=X AND sale_date <= as_of_date)
return cumulative_expense - cumulative_sales
```

Working-capital-requirement estimate (a positive value = cash need not yet covered by
sales at that date). Implemented per spec section 5.3 formula exactly, but **not called
from any view, serializer, or URL anywhere in the codebase** — there is no
`bfr`/`workingCapital` endpoint or field exposing it. Dead code as far as the API surface
goes; see `docs/deviations.md`.

## apps/stock/calculations.py — inventory

### `current_quantity(item)` — `apps/stock/calculations.py:current_quantity`

```python
stock_in  = SUM(StockMovement.quantity WHERE item=X AND movement_type='IN')
stock_out = SUM(StockMovement.quantity WHERE item=X AND movement_type='OUT')
return stock_in - stock_out
```

Matches spec section 5.2 exactly. Computed by aggregation at read time on every call
(`StockItemSerializer.get_current_quantity`, `apps.alerts.services.check_low_stock`) — the
spec explicitly allows either computing on the fly or caching on `StockItem`; this codebase
chose "compute on the fly", so `StockItem` itself never stores a quantity field. Crossing
below `StockItem.alert_threshold` is what fires a `LOW_STOCK` `Alert` (see
`apps.alerts.services.check_low_stock`, triggered by `StockMovement`'s `post_save` signal in
`apps/alerts/signals.py`) — that comparison itself lives in the alerts app, not here.

### `stock_evolution(farm)` — `apps/stock/calculations.py:stock_evolution`

Per-item series for the `/dashboard/stock` charts (2026-08-28). For each `StockItem`, walks
its `StockMovement` rows ordered by `movement_date` (then id), running `+quantity` for `IN` /
`-quantity` for `OUT`, and emits one `{date, quantity}` point per distinct movement date
(calendar date, **not** day-of-cycle — stock is farm-scoped). Also echoes `alertThreshold`
so the frontend can draw a reference line. Items with no movements get `points: []`.

### `coverage_for(item, quantity_per_day, days)` — `apps/stock/calculations.py:coverage_for`

Planning heuristic behind the protocol form's inline "stock insuffisant" warning (2026-08-28).
`dailyRate` = `quantity_per_day` for the row being edited **plus** the sum of
`quantity_per_day` over every *other* `ProtocolTemplate` row across the farm linked to the
same item (a forward-looking figure — it does not test whether those rows' ranges overlap).
`daysRemaining = current_quantity(item) / dailyRate`; `sufficient = daysRemaining >= days`.
Non-blocking — the caller only shows a warning, never rejects a save.

## apps/finance/calculations.py — farm-wide finance

### `_month_range(range_param)` — `apps/finance/calculations.py:_month_range`

```python
months_count = 12 if range_param == '1y' else 6      # anything other than '1y' -> 6 months
today = date.today()
start_month = today.replace(day=1) - relativedelta(months=months_count - 1)
return [start_month + relativedelta(months=i) for i in range(months_count)]
```

List of month-start dates for the window, always ending with the current month.

### `monthly_summary(farm, range_param='6m')` — `apps/finance/calculations.py:monthly_summary`

```python
for month_start in months:
    month_end = month_start + relativedelta(months=1)
    revenue  = SUM(Sale.total_amount WHERE farm=X AND sale_date IN [month_start, month_end))
    expenses = SUM(Expense.amount WHERE farm=X AND expense_date IN [month_start, month_end))
```

One `{month, revenue, expenses}` entry per calendar month, farm-wide (not per batch).
Zero-filled months (no rows) are still included with `revenue`/`expenses` of `0`.

### `cash_on_hand(farm)` — `apps/finance/calculations.py:cash_on_hand`

```python
cash_on_hand = SUM(Sale.total_amount) - SUM(Expense.amount) - SUM(PurchaseOrder.amount WHERE status='RECEIVED')
```

Matches spec section 5.4 exactly. Computed over the farm's **entire history** — not scoped
to the `range` query parameter at all (unlike `monthly_summary`/`roi_forecast_pct`), even
though it's returned as part of the same `GET /api/finance/summary/?range=` response.

### `pending_payables(farm)` — `apps/finance/calculations.py:pending_payables`

```python
pending_payables = SUM(PurchaseOrder.amount WHERE status='PENDING')
```

Matches spec section 5.4 exactly. Also all-time, not range-scoped.

### `roi_forecast_pct(farm, range_param='6m')` — `apps/finance/calculations.py:roi_forecast_pct`

```python
period_start = months[0]  # first month of the _month_range window
total_investment = SUM(PurchaseOrder.amount
                        WHERE farm=X AND item.category='EQUIPMENT'
                          AND status='RECEIVED' AND order_date >= period_start)
if not total_investment:
    return None
total_revenue  = SUM(Sale.total_amount WHERE farm=X AND sale_date >= period_start)
total_expenses = SUM(Expense.amount WHERE farm=X AND expense_date >= period_start)
projected_margin = total_revenue - total_expenses
return round(projected_margin / total_investment * 100, 2)
```

**Diverges from spec section 5.4**: the spec's `total_investment` is "the sum of
`PurchaseOrder` of category équipement/bâtiment over the period, **or a value entered
manually by the administrator if no investment is yet recorded**". The implementation only
does the first half — `RECEIVED` `PurchaseOrder` rows in the `EQUIPMENT` `StockItem`
category — since the schema has no dedicated investment/capex table or field to hold a
manual entry. Returns `None` ("not available"), never a fabricated `0`, whenever
`total_investment` is `0` for the period — this part matches the spec's explicit
requirement.

### `finance_summary(farm, range_param='6m')` — `apps/finance/calculations.py:finance_summary`

Backs `GET /api/finance/summary/?range=6m|1y` (implementation-detail spec 11.2). Combines
the four functions above:

```python
{
  "range": range_param,
  "months": monthly_summary(farm, range_param),
  "cashOnHand": cash_on_hand(farm),
  "pendingPayables": pending_payables(farm),
  "roiForecastPct": roi_forecast_pct(farm, range_param),
}
```

### `expense_category_breakdown(farm, range_param='6m')` — `apps/finance/calculations.py:expense_category_breakdown`

Backs `GET /api/finance/expense-categories/?range=6m|1y` (implementation-detail spec 11.3).

```python
period_start = months[0]
expenses = Expense.objects.filter(farm=farm, expense_date__gte=period_start)
total = SUM(expenses.amount) or 1          # guards divide-by-zero, not a real fallback total
totals_by_category = {category: SUM(amount) for category in ExpenseCategory}
categories = [
    {"category": c, "amountPct": round(amount / total * 100, 1)}
    for c, amount in totals_by_category.items() if amount     # zero-amount categories omitted
]
```

Categories with no expenses in the window are dropped from the response entirely rather
than returned with `amountPct: 0`.

### `break_even_quantity(allocated_fixed_cost, unit_sale_price, unit_variable_cost)` — `apps/finance/calculations.py:break_even_quantity`

```python
denominator = unit_sale_price - unit_variable_cost
if not denominator:
    return None
return allocated_fixed_cost / denominator
```

Matches spec section 5.3's `break_even_quantity` formula exactly, but **the caller must
compute all three inputs themselves** — this function does not query `Expense`/`Sale` at
all. **Not called from any view or serializer anywhere in the codebase** — implemented per
spec but not wired to an endpoint; see `docs/deviations.md`.

### `safety_margin_pct(actual_quantity_sold, break_even_qty)` — `apps/finance/calculations.py:safety_margin_pct`

```python
if not actual_quantity_sold or break_even_qty is None:
    return None
return round((actual_quantity_sold - break_even_qty) / actual_quantity_sold * 100, 2)
```

Same status as `break_even_quantity`: implemented, matches no explicit spec formula by name
(it's a natural extension of the break-even calculation) but **not called from anywhere** in
the codebase.

## Formulas mentioned in the spec but not implemented anywhere

- **`debt_ratio` (spec section 5.4)** — explicitly described in the spec as "not calculable
  while no liability/loan table exists in the schema"; there is indeed no such table
  (`Expense`/`PurchaseOrder` are the only liability-adjacent models), and no `debt_ratio`
  function exists in this codebase. Matches the spec's own caveat, not a gap.
- **`feed_per_bird_day` and `water_feed_ratio` (spec section 5.1)** — `water_feed_ratio` (as
  `water_consumed_l / feed_consumed_kg`) is computed inline in
  `apps/alerts/services.py:check_consumption_deviation` (not in `apps/batches/calculations.py`)
  purely to decide whether to fire a `CONSUMPTION_DEVIATION` alert (outside the 1.6–2.2
  range) — the ratio itself is never persisted or returned by any endpoint.
  `feed_per_bird_day` (`feed_consumed_kg / current_count`) has no implementation anywhere;
  no endpoint or chart currently needs it.
