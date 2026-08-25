"""Backend calculation formulas — implementation-detail spec section 5.

Every figure shown on the dashboard is computed here from real DailyLog /
Expense / Sale rows; nothing is stored pre-aggregated or computed client-side.
"""
from collections import defaultdict

FCR_REFERENCE_RANGE = (2.10, 2.30)
MORTALITY_REFERENCE_RANGE = (3, 5)


def mortality_pct(batch):
    """Cumulative mortality since batch start, as a percentage of the initial flock size.

    `mortality_pct = SUM(DailyLog.mortality) / PoultryBatch.initial_count * 100`
    (implementation-detail spec 5.1). Reference range 3% (favorable) to 5% (unfavorable) by
    cycle end — see MORTALITY_REFERENCE_RANGE. Returns 0.0, not an error, if initial_count is 0.
    """
    total_mortality = sum(log.mortality for log in batch.daily_logs.all())
    if not batch.initial_count:
        return 0.0
    return round(total_mortality / batch.initial_count * 100, 2)


def feed_conversion_ratio(batch, up_to_date=None):
    """Feed conversion ratio (FCR): total feed consumed divided by estimated live weight produced.

    `feed_conversion_ratio = SUM(DailyLog.feed_consumed_kg) / (PoultryBatch.current_count *
    latest(DailyLog.avg_sample_weight))` (implementation-detail spec 5.1) — live weight is
    estimated as *current* flock size times the most recent sample weight, not a per-bird sum.
    `up_to_date` restricts both the feed sum and the "latest sample weight" search to logs on or
    before that date (used by `weekly_kpi` to compute a running FCR per week). Returns None
    (never a fabricated 0) if there is no sample weight yet or current_count is 0.
    Reference range 2.10 (favorable) to 2.30 (unfavorable) — see FCR_REFERENCE_RANGE.
    """
    logs = batch.daily_logs.all()
    if up_to_date:
        logs = [log for log in logs if log.log_date <= up_to_date]
    total_feed = sum(log.feed_consumed_kg for log in logs)
    latest_weight = None
    for log in sorted(logs, key=lambda entry: entry.log_date):
        if log.avg_sample_weight:
            latest_weight = log.avg_sample_weight
    if not latest_weight or not batch.current_count:
        return None
    return round(total_feed / (batch.current_count * latest_weight), 2)


def week_number(batch, log_date):
    """1-indexed week number of `log_date` relative to `batch.start_date` (days 1-7 = week 1)."""
    return (log_date - batch.start_date).days // 7 + 1


def weekly_kpi(batch):
    """GET /api/batches/{batchCode}/kpi/weekly/ payload (implementation-detail 11.1)."""
    logs_by_week = defaultdict(list)
    for log in batch.daily_logs.all():
        logs_by_week[week_number(batch, log.log_date)].append(log)

    weeks = []
    for week in sorted(logs_by_week):
        week_logs = logs_by_week[week]
        week_mortality = sum(log.mortality for log in week_logs)
        last_date_in_week = max(log.log_date for log in week_logs)
        weeks.append({
            'week': week,
            'mortalityPct': round(week_mortality / batch.initial_count * 100, 2) if batch.initial_count else 0.0,
            'feedConversionRatio': feed_conversion_ratio(batch, up_to_date=last_date_in_week),
            'avgWeightKg': next(
                (log.avg_sample_weight for log in sorted(week_logs, key=lambda entry: entry.log_date, reverse=True)
                 if log.avg_sample_weight),
                None,
            ),
        })

    return {
        'batchCode': batch.batch_code,
        'weeks': weeks,
        'referenceRange': {
            'feedConversionRatio': list(FCR_REFERENCE_RANGE),
            'mortalityPct': list(MORTALITY_REFERENCE_RANGE),
        },
    }


def build_closing_report(batch):
    """Computes and persists BatchClosingReport at batch closing (section 5.3 / 11.4).

    Profit is never entered manually — it is always derived from Expense/Sale rows.
    """
    from apps.batches.models import BatchClosingReport
    from apps.finance.models import Expense, Sale

    variable_categories = ['FEED', 'VETERINARY', 'MISC']
    fixed_categories = ['DEPRECIATION', 'LABOR']

    expenses = Expense.objects.filter(batch=batch)
    total_variable_cost = sum(e.amount for e in expenses.filter(category__in=variable_categories))
    allocated_fixed_cost = sum(e.amount for e in expenses.filter(category__in=fixed_categories))
    revenue = sum(s.total_amount for s in Sale.objects.filter(batch=batch))
    unit_cost_price = (total_variable_cost / batch.current_count) if batch.current_count else None
    gross_margin = revenue - total_variable_cost
    net_margin = gross_margin - allocated_fixed_cost

    report, _ = BatchClosingReport.objects.update_or_create(
        batch=batch,
        defaults={
            'total_mortality_pct': mortality_pct(batch),
            'feed_conversion_ratio': feed_conversion_ratio(batch),
            'revenue': revenue,
            'total_variable_cost': total_variable_cost,
            'unit_cost_price': unit_cost_price,
            'total_margin': net_margin,
        },
    )
    return report


def bfr_estimate(batch, as_of_date):
    """Working capital requirement estimate — positive means cash need not yet covered by sales."""
    from apps.finance.models import Expense, Sale

    cumulative_expense = sum(
        e.amount for e in Expense.objects.filter(batch=batch, expense_date__lte=as_of_date)
    )
    cumulative_sales = sum(
        s.total_amount for s in Sale.objects.filter(batch=batch, sale_date__lte=as_of_date)
    )
    return cumulative_expense - cumulative_sales
