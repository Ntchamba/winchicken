"""Finance calculations — implementation-detail spec sections 5.3 / 5.4.

roiForecastPct stays null ("not available") whenever no investment has been
recorded yet — never a fabricated zero (implementation-detail 11.2).
"""
from collections import OrderedDict
from datetime import date, timedelta

from dateutil.relativedelta import relativedelta
from django.utils import timezone

from apps.finance.models import Expense, ExpenseCategory, OrderStatus, ProductType, PurchaseOrder, Sale
from apps.stock.models import ItemCategory


def _month_range(range_param):
    """List of month-start `date`s for the requested window: 6 months for '6m' (default,
    anything other than '1y'), 12 months for '1y' — always ending with the current month."""
    months_count = 12 if range_param == '1y' else 6
    today = timezone.localdate()
    start_month = today.replace(day=1) - relativedelta(months=months_count - 1)
    return [start_month + relativedelta(months=i) for i in range(months_count)]


# Ventes/Achats evolution charts (2026-08-27, Finances restructure) — a distinct "period" concept
# (Semaine/Mois/Année buckets) from the existing `range_param` ('6m'/'1y', always monthly
# buckets) used by monthly_summary/finance_summary above; kept separate rather than unified,
# since the two screens ask for genuinely different bucketing, not just a different window size.
def _bucket_starts(period):
    """`([bucket_start_date, ...], unit)` for the requested period — 8 weeks, 12 months (default)
    or 5 years, always ending with the current bucket."""
    today = timezone.localdate()
    if period == 'week':
        this_week_start = today - timedelta(days=today.weekday())
        start = this_week_start - timedelta(weeks=7)
        return [start + timedelta(weeks=i) for i in range(8)], 'week'
    if period == 'year':
        start_year = today.year - 4
        return [date(start_year + i, 1, 1) for i in range(5)], 'year'
    start_month = today.replace(day=1) - relativedelta(months=11)
    return [start_month + relativedelta(months=i) for i in range(12)], 'month'


def _bucket_end(start, unit):
    if unit == 'week':
        return start + timedelta(weeks=1)
    if unit == 'year':
        return date(start.year + 1, 1, 1)
    return start + relativedelta(months=1)


def _bucket_label(start, unit):
    if unit == 'week':
        # %G (ISO year), not %Y: the week starting Monday 2024-12-30 is 2025-W01. With %Y it was
        # labelled "2024-W01", sorted first on the chart and shared a label with a real week.
        return start.strftime('%G-W%V')
    if unit == 'year':
        return str(start.year)
    return start.strftime('%Y-%m')


def sales_evolution(farm, period='month'):
    """Response payload for the "Ventes" section: a `bucket`-labeled revenue series (week/month/
    year, per `period`) plus period totals — total revenue, sale count, and a by-`ProductType`
    breakdown, all over the same window the series covers (its first bucket's start to today)."""
    starts, unit = _bucket_starts(period)
    series = []
    for start in starts:
        end = _bucket_end(start, unit)
        total = sum(s.total_amount for s in Sale.objects.filter(farm=farm, sale_date__gte=start, sale_date__lt=end))
        series.append({'bucket': _bucket_label(start, unit), 'total': float(total)})

    period_start = starts[0]
    period_sales = list(Sale.objects.filter(farm=farm, sale_date__gte=period_start))
    total_revenue = sum(s.total_amount for s in period_sales)
    by_product = OrderedDict((p.value, 0) for p in ProductType)
    for s in period_sales:
        by_product[s.product_type] += s.total_amount
    breakdown = [{'productType': p, 'amount': float(a)} for p, a in by_product.items() if a]

    return {
        'period': period, 'series': series,
        'totalRevenue': float(total_revenue), 'salesCount': len(period_sales),
        'breakdown': breakdown,
    }


# PurchaseOrder.item.category uses Stock's ItemCategory (FEED/VETERINARY/EQUIPMENT/BEDDING) —
# a different enum from Expense's own ExpenseCategory (FEED/VETERINARY/MISC/DEPRECIATION/LABOR).
# The task's own Achats breakdown list ("Aliment/Vétérinaire/Divers/Amortissement" — Main-d'œuvre
# once Salaires generates LABOR expenses) matches ExpenseCategory's labels, not ItemCategory's,
# so received purchase orders are folded into that same axis for one unified breakdown: FEED/
# VETERINARY map 1:1 (identical concept, different enum); EQUIPMENT -> DEPRECIATION (capital
# equipment purchases are exactly what `roi_forecast_pct` above already treats as "investment" —
# the closest existing precedent in this codebase for how to classify them); BEDDING -> MISC (no
# direct ExpenseCategory equivalent). A disclosed judgment call, not an arbitrary one.
_ITEM_CATEGORY_TO_EXPENSE_CATEGORY = {
    ItemCategory.FEED: ExpenseCategory.FEED,
    ItemCategory.VETERINARY: ExpenseCategory.VETERINARY,
    ItemCategory.EQUIPMENT: ExpenseCategory.DEPRECIATION,
    ItemCategory.BEDDING: ExpenseCategory.MISC,
}


def purchases_evolution(farm, period='month'):
    """Response payload for the "Achats" section: read-only aggregation of RECEIVED
    `PurchaseOrder` rows and `Expense` rows (no data entered here — per this task's own Part C,
    both sources come from Stock/Caisse). Same `bucket`-series shape as `sales_evolution`, plus a
    period total and a single unified by-category breakdown (see `_ITEM_CATEGORY_TO_EXPENSE_CATEGORY`
    for how a PurchaseOrder's item category folds into the same axis Expense.category already uses).
    """
    starts, unit = _bucket_starts(period)
    series = []
    for start in starts:
        end = _bucket_end(start, unit)
        po_total = sum(
            o.amount for o in PurchaseOrder.objects.filter(
                farm=farm, status=OrderStatus.RECEIVED, order_date__gte=start, order_date__lt=end,
            )
        )
        exp_total = sum(e.amount for e in Expense.objects.filter(farm=farm, expense_date__gte=start, expense_date__lt=end))
        series.append({'bucket': _bucket_label(start, unit), 'total': float(po_total + exp_total)})

    period_start = starts[0]
    period_orders = list(
        PurchaseOrder.objects.filter(farm=farm, status=OrderStatus.RECEIVED, order_date__gte=period_start).select_related('item')
    )
    period_expenses = list(Expense.objects.filter(farm=farm, expense_date__gte=period_start))
    total_po = sum(o.amount for o in period_orders)
    total_exp = sum(e.amount for e in period_expenses)

    by_category = OrderedDict((c.value, 0) for c in ExpenseCategory)
    for e in period_expenses:
        by_category[e.category] += e.amount
    for o in period_orders:
        mapped = _ITEM_CATEGORY_TO_EXPENSE_CATEGORY.get(o.item.category.kind, ExpenseCategory.MISC)
        by_category[mapped] += o.amount
    breakdown = [{'category': c, 'amount': float(a)} for c, a in by_category.items() if a]

    return {
        'period': period, 'series': series,
        'totalSpent': float(total_po + total_exp),
        'breakdown': breakdown,
    }


def monthly_summary(farm, range_param='6m'):
    """Per-month revenue (Sale.total_amount) vs expenses series for the finance trend chart —
    one entry per calendar month in the window, zero-filled if no rows exist.

    "expenses" = `Expense.amount` (which now includes the Expense a cost-tracked "Ajouter du
    stock" writes) **plus** the `amount` of RECEIVED `PurchaseOrder` rows in that month (by
    `order_date`) — the two are disjoint (a RECEIVED PurchaseOrder never also writes an
    Expense), and this is the same combination the Achats section's `purchases_evolution`
    already uses (2026-08-31 — before this, a received PurchaseOrder showed in Achats but not in
    Globale's trend or category donut)."""
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
        received_orders = sum(
            o.amount for o in PurchaseOrder.objects.filter(
                farm=farm, status=OrderStatus.RECEIVED, order_date__gte=month_start, order_date__lt=month_end,
            )
        )
        result.append({
            'month': month_start.strftime('%Y-%m'),
            'revenue': float(revenue),
            'expenses': float(expenses + received_orders),
        })
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
            farm=farm, item__category__kind=ItemCategory.EQUIPMENT, status=OrderStatus.RECEIVED, order_date__gte=period_start
        )
    )
    if not total_investment:
        return None
    total_revenue = sum(s.total_amount for s in Sale.objects.filter(farm=farm, sale_date__gte=period_start))
    total_expenses = sum(e.amount for e in Expense.objects.filter(farm=farm, expense_date__gte=period_start))
    # Received supply orders are expenses everywhere else (monthly_summary, Achats, the category
    # breakdown); leaving them out overstated the margin. Equipment orders stay out: they are the
    # investment this margin is divided by, not a running cost.
    total_supply_orders = sum(
        o.amount for o in PurchaseOrder.objects.filter(
            farm=farm, status=OrderStatus.RECEIVED, order_date__gte=period_start,
        ).exclude(item__category__kind=ItemCategory.EQUIPMENT)
    )
    projected_margin = total_revenue - total_expenses - total_supply_orders
    return round(float(projected_margin / total_investment) * 100, 2)


def farm_wide_indicators(farm, range_param='6m'):
    """Farm-wide operational + stock figures for Globale's stat cards (2026-08-31) — a genuine
    "état de la ferme" alongside the pure revenue/expense chart.

      stockValue      — total value of stock on hand: Σ current_quantity(item) × unit_price
                        over every StockItem (uses the existing IN-minus-OUT calculation).
      mortalityCount  — Σ DailyLog.mortality on this farm's batches over the window (an
                        operational loss indicator, explicitly *not* a monetary figure).
      incidentsCount  — reported UnusualCase + EquipmentFault on this farm over the window.
      salesTotal      — Σ Sale.total_amount over the window (compact echo of the Ventes section,
                        not a second chart).
      eggsCount       — Σ DailyLog.eggs_collected over the window (nullable field → treated 0).
    """
    from django.db.models import Sum

    from apps.batches.models import DailyLog
    from apps.maintenance.models import EquipmentFault, UnusualCase
    from apps.stock.calculations import current_quantity, with_current_quantity
    from apps.stock.models import StockItem

    period_start = _month_range(range_param)[0]

    stock_value = sum(
        current_quantity(item) * float(item.unit_price)
        for item in with_current_quantity(StockItem.objects.filter(farm=farm))
    )
    logs = DailyLog.objects.filter(batch__house__farm=farm, log_date__gte=period_start)
    mortality = logs.aggregate(n=Sum('mortality'))['n'] or 0
    eggs = logs.aggregate(n=Sum('eggs_collected'))['n'] or 0
    incidents = (
        UnusualCase.objects.filter(batch__house__farm=farm, case_date__gte=period_start).count()
        + EquipmentFault.objects.filter(house__farm=farm, reported_date__gte=period_start).count()
    )
    sales_total = Sale.objects.filter(farm=farm, sale_date__gte=period_start).aggregate(
        n=Sum('total_amount'))['n'] or 0

    return {
        'stockValue': round(float(stock_value), 2),
        'mortalityCount': int(mortality),
        'incidentsCount': int(incidents),
        'salesTotal': float(sales_total),
        'eggsCount': int(eggs),
    }


def finance_summary(farm, range_param='6m'):
    """Response payload for GET /api/finance/summary/?range=6m|1y (implementation-detail spec
    11.2): monthly revenue/expenses series plus cash-on-hand, pending payables, ROI forecast,
    and (2026-08-31) the farm-wide stock/loss/sales/egg indicators for Globale's stat cards."""
    return {
        'range': range_param,
        'months': monthly_summary(farm, range_param),
        'cashOnHand': cash_on_hand(farm),
        'pendingPayables': pending_payables(farm),
        'roiForecastPct': roi_forecast_pct(farm, range_param),
        **farm_wide_indicators(farm, range_param),
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

    return {'revenueTrend': direction('revenue'), 'expenseTrend': direction('expenses')}


def expense_category_breakdown(farm, range_param='6m'):
    """Response payload for GET /api/finance/expense-categories/?range=6m|1y
    (implementation-detail spec 11.3): each ExpenseCategory's share of total expenses over the
    window, as a rounded percentage. Categories with 0 expenses in the window are omitted from
    the response rather than returned with amountPct: 0."""
    months = _month_range(range_param)
    period_start = months[0]
    totals = OrderedDict((category.value, 0) for category in ExpenseCategory)

    for expense in Expense.objects.filter(farm=farm, expense_date__gte=period_start):
        totals[expense.category] += expense.amount
    # RECEIVED PurchaseOrders folded onto the same axis (2026-08-31), each mapped from its
    # item's stock-category kind — the same mapping/combination the Achats section uses.
    for order in PurchaseOrder.objects.filter(
        farm=farm, status=OrderStatus.RECEIVED, order_date__gte=period_start,
    ).select_related('item', 'item__category'):
        mapped = _ITEM_CATEGORY_TO_EXPENSE_CATEGORY.get(order.item.category.kind, ExpenseCategory.MISC)
        totals[mapped] += order.amount

    total = sum(totals.values()) or 1
    categories = [
        {'category': category, 'amountPct': round(float(amount) / float(total) * 100, 1)}
        for category, amount in totals.items() if amount
    ]
    return {'range': range_param, 'categories': categories}


def break_even_quantity(allocated_fixed_cost, unit_sale_price, unit_variable_cost):
    """`break_even_quantity = allocated_fixed_cost / (unit_sale_price - unit_variable_cost)`
    (implementation-detail spec 5.3). Returns None if sale price equals variable cost (division
    by zero), and when the price is *below* the variable cost (every sale loses money, so no
    quantity ever breaks even) — never a fabricated value.

    NOT currently called from any view or serializer — implemented per the spec formula but not
    wired to an API endpoint or exposed figure (see docs/deviations.md). Callers must compute
    the three inputs themselves from Expense/Sale rows; this module does not do so for them.
    """
    denominator = unit_sale_price - unit_variable_cost
    if denominator <= 0:
        return None
    return allocated_fixed_cost / denominator


def safety_margin_pct(actual_quantity_sold, break_even_qty):
    """How far actual sales exceed the break-even quantity, as a percentage of actual sales.
    Returns None if there were no sales or break_even_qty is unavailable.

    NOT currently called from any view or serializer — same status as break_even_quantity above.
    """
    if not actual_quantity_sold or break_even_qty is None:
        return None
    return round((actual_quantity_sold - break_even_qty) / actual_quantity_sold * 100, 2)


def series_trend(series):
    """'up'/'down'/'flat' comparing the last two buckets of a `sales_evolution`/
    `purchases_evolution` series — the Ventes/Achats restricted-role payload (same access split
    as `finance_trend_direction` above: direction only, no amounts). 'flat' also covers the
    fewer-than-2-buckets edge case, same reasoning as `finance_trend_direction`'s own single-month
    case."""
    if len(series) < 2:
        return 'flat'
    previous, latest = series[-2]['total'], series[-1]['total']
    if latest > previous:
        return 'up'
    if latest < previous:
        return 'down'
    return 'flat'
