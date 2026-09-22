"""Finance calculations — implementation-detail spec sections 5.3 / 5.4.

roiForecastPct stays null ("not available") whenever no investment has been
recorded yet — never a fabricated zero (implementation-detail 11.2).
"""
from collections import OrderedDict
from datetime import date

from dateutil.relativedelta import relativedelta

from apps.finance.models import Expense, ExpenseCategory, OrderStatus, PurchaseOrder, Sale
from apps.stock.models import ItemCategory


def _month_range(range_param):
    """List of month-start `date`s for the requested window: 6 months for '6m' (default,
    anything other than '1y'), 12 months for '1y' — always ending with the current month."""
    months_count = 12 if range_param == '1y' else 6
    today = date.today()
    start_month = today.replace(day=1) - relativedelta(months=months_count - 1)
    return [start_month + relativedelta(months=i) for i in range(months_count)]


def monthly_summary(farm, range_param='6m'):
    """Per-month revenue (Sale.total_amount) vs expenses (Expense.amount) series for the finance
    trend chart — one entry per calendar month in the window, zero-filled if no rows exist."""
    months = _month_range(range_param)
    result = []
    for month_start in months:
        month_end = month_start + relativedelta(months=1)
        revenue = sum(
            s.total_amount for s in Sale.objects.filter(farm=farm, sale_date__gte=month_start, sale_date__lt=month_end)
        )
        expenses = sum(
            e.amount for e in Expense.objects.filter(farm=farm, expense_date__gte=month_start, expense_date__lt=month_end)
        )
        result.append({'month': month_start.strftime('%Y-%m'), 'revenue': float(revenue), 'expenses': float(expenses)})
    return result


def cash_on_hand(farm):
    """`cash_on_hand = cumulative(Sale.totalAmount) - cumulative(Expense.amount) -
    cumulative(PurchaseOrder.amount WHERE status=RECEIVED)` (implementation-detail spec 5.4).
    Computed over the farm's *entire* history, not scoped to any date range."""
    total_sales = sum(s.total_amount for s in Sale.objects.filter(farm=farm))
    total_expenses = sum(e.amount for e in Expense.objects.filter(farm=farm))
    total_received_orders = sum(
        o.amount for o in PurchaseOrder.objects.filter(farm=farm, status=OrderStatus.RECEIVED)
    )
    return float(total_sales - total_expenses - total_received_orders)


def pending_payables(farm):
    """Sum of PurchaseOrder.amount still PENDING (not yet received/paid) for the farm — all-time,
    not scoped to any date range."""
    return float(
        sum(o.amount for o in PurchaseOrder.objects.filter(farm=farm, status=OrderStatus.PENDING))
    )


def roi_forecast_pct(farm, range_param='6m'):
    """`roi_forecast_pct = (projected_margin / total_investment) * 100` over the window
    (implementation-detail spec 5.4), where `total_investment` is the sum of RECEIVED
    PurchaseOrder rows whose item is category EQUIPMENT during the period — the schema has no
    dedicated "investment" categorization or manual-entry fallback, so equipment purchases are
    used as the closest proxy (deviation from the spec, which also allows an administrator to
    enter total_investment manually when none is recorded). Returns None ("not available"),
    never a fabricated 0, when total_investment is 0 for the period."""
    months = _month_range(range_param)
    period_start = months[0]
    total_investment = sum(
        o.amount for o in PurchaseOrder.objects.filter(
            farm=farm, item__category=ItemCategory.EQUIPMENT, status=OrderStatus.RECEIVED, order_date__gte=period_start
        )
    )
    if not total_investment:
        return None
    total_revenue = sum(s.total_amount for s in Sale.objects.filter(farm=farm, sale_date__gte=period_start))
    total_expenses = sum(e.amount for e in Expense.objects.filter(farm=farm, expense_date__gte=period_start))
    projected_margin = total_revenue - total_expenses
    return round(float(projected_margin / total_investment) * 100, 2)


def finance_summary(farm, range_param='6m'):
    """Response payload for GET /api/finance/summary/?range=6m|1y (implementation-detail spec
    11.2): monthly revenue/expenses series plus cash-on-hand, pending payables and ROI forecast."""
    return {
        'range': range_param,
        'months': monthly_summary(farm, range_param),
        'cash_on_hand': cash_on_hand(farm),
        'pending_payables': pending_payables(farm),
        'roi_forecast_pct': roi_forecast_pct(farm, range_param),
    }


def finance_trend_direction(farm, range_param='6m'):
    """Restricted-role payload for GET /api/finance/summary/ (Finance access matrix,
    winchicken-spec-implementation-detaillee.docx sections 4.3/8): direction-only trend, no
    exact monetary figures. Compares the two most recent months in the window; "flat"
    when they're equal (also covers the single-month edge case, since a month compared
    to itself is equal)."""
    months = monthly_summary(farm, range_param)
    previous, latest = months[-2], months[-1]

    def direction(key):
        if latest[key] > previous[key]:
            return 'up'
        if latest[key] < previous[key]:
            return 'down'
        return 'flat'

    return {'revenue_trend': direction('revenue'), 'expense_trend': direction('expenses')}


def expense_category_breakdown(farm, range_param='6m'):
    """Response payload for GET /api/finance/expense-categories/?range=6m|1y
    (implementation-detail spec 11.3): each ExpenseCategory's share of total expenses over the
    window, as a rounded percentage. Categories with 0 expenses in the window are omitted from
    the response rather than returned with amountPct: 0."""
    months = _month_range(range_param)
    period_start = months[0]
    expenses = Expense.objects.filter(farm=farm, expense_date__gte=period_start)
    total = sum(e.amount for e in expenses) or 1
    totals = OrderedDict((category.value, 0) for category in ExpenseCategory)
    for expense in expenses:
        totals[expense.category] += expense.amount
    categories = [
        {'category': category, 'amount_pct': round(float(amount) / float(total) * 100, 1)}
        for category, amount in totals.items() if amount
    ]
    return {'range': range_param, 'categories': categories}


def break_even_quantity(allocated_fixed_cost, unit_sale_price, unit_variable_cost):
    """`break_even_quantity = allocated_fixed_cost / (unit_sale_price - unit_variable_cost)`
    (implementation-detail spec 5.3). Returns None if sale price equals variable cost (division
    by zero) — never a fabricated value.

    Takes its three inputs already computed — see `batch_break_even` below for the
    Expense/Sale aggregation `GET /api/finance/break-even/` actually uses.
    """
    denominator = unit_sale_price - unit_variable_cost
    if not denominator:
        return None
    return allocated_fixed_cost / denominator


def safety_margin_pct(actual_quantity_sold, break_even_qty):
    """How far actual sales exceed the break-even quantity, as a percentage of actual sales.
    Returns None if there were no sales or break_even_qty is unavailable."""
    if not actual_quantity_sold or break_even_qty is None:
        return None
    return round((actual_quantity_sold - break_even_qty) / actual_quantity_sold * 100, 2)


def batch_break_even(batch):
    """Response payload for GET /api/finance/break-even/?batch_code= — derives
    `break_even_quantity`'s three inputs from the batch's own Expense/Sale rows (the same
    variable/fixed category split as `apps.batches.calculations.build_closing_report`), then
    combines it with `safety_margin_pct` against the batch's actual quantity sold so far.

    - `unit_variable_cost` = total variable-category Expense (FEED/VETERINARY/MISC) / batch
      current bird count.
    - `unit_sale_price` = average Sale.unit_price recorded for the batch (None if no sales yet).
    - `allocated_fixed_cost` = total fixed-category Expense (DEPRECIATION/LABOR) for the batch.
    """
    from apps.batches.calculations import FIXED_EXPENSE_CATEGORIES, VARIABLE_EXPENSE_CATEGORIES

    variable_cost = sum(
        e.amount for e in Expense.objects.filter(batch=batch, category__in=VARIABLE_EXPENSE_CATEGORIES)
    )
    allocated_fixed_cost = sum(
        e.amount for e in Expense.objects.filter(batch=batch, category__in=FIXED_EXPENSE_CATEGORIES)
    )
    from decimal import Decimal

    sales = list(Sale.objects.filter(batch=batch))
    actual_quantity_sold = sum(s.quantity for s in sales)
    unit_sale_price = (
        float(sum(s.unit_price * Decimal(str(s.quantity)) for s in sales) / Decimal(str(actual_quantity_sold)))
        if actual_quantity_sold else None
    )
    unit_variable_cost = float(variable_cost) / batch.current_count if batch.current_count else None

    break_even_qty = None
    if unit_sale_price is not None and unit_variable_cost is not None:
        break_even_qty = break_even_quantity(float(allocated_fixed_cost), unit_sale_price, unit_variable_cost)

    return {
        'batch_code': batch.batch_code,
        'allocated_fixed_cost': float(allocated_fixed_cost),
        'unit_variable_cost': unit_variable_cost,
        'unit_sale_price': unit_sale_price,
        'break_even_quantity': break_even_qty,
        'actual_quantity_sold': float(actual_quantity_sold),
        'safety_margin_pct': safety_margin_pct(actual_quantity_sold, break_even_qty),
    }
