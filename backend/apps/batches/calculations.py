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
    `up_to_date` restricts the feed sum, the "latest sample weight" search and the flock size to
    logs on or before that date (used by `weekly_kpi` to compute a running FCR per week). Returns None
    (never a fabricated 0) if there is no sample weight yet or current_count is 0.
    Reference range 2.10 (favorable) to 2.30 (unfavorable) — see FCR_REFERENCE_RANGE.
    """
    logs = batch.daily_logs.all()
    if up_to_date:
        logs = [log for log in logs if log.log_date <= up_to_date]
        # A past week's FCR divides by the flock alive *then*: deaths logged in later weeks must
        # not shrink an earlier week's flock after the fact (that inflated early weeks' FCR).
        flock = max(0, batch.initial_count - sum(log.mortality for log in logs))
    else:
        # Read only here: it used to be read unconditionally and then discarded whenever
        # `up_to_date` was given — one wasted aggregate query per week of `weekly_kpi`.
        flock = batch.current_count
    total_feed = sum(log.feed_consumed_kg for log in logs)
    latest_weight = None
    for log in sorted(logs, key=lambda entry: entry.log_date):
        if log.avg_sample_weight:
            latest_weight = log.avg_sample_weight
    # No feed recorded is an unknown FCR, not a perfect 0.00 (no screen writes feed_consumed_kg
    # today, so a real farm's KPIs and closing report all read 0.00).
    if not latest_weight or not flock or total_feed <= 0:
        return None
    return round(total_feed / (flock * latest_weight), 2)


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


def growth_curve(batch):
    """Day-of-cycle series for the growth-curve charts (2026-08-25) — X axis is
    `dayOfCycle = (log_date - batch.start_date).days`, not a calendar date, so batches with
    different start dates overlay meaningfully on the same chart (implementation-detail spec's
    "one line per active batch" requirement).

    One point per DailyLog row that has data: `weightKg` is only present on days a sample
    weighing was recorded (`avg_sample_weight`, sparse — most days have none); `survivalPct` is
    present on every logged day (`current flock size / initial_count * 100`, computed by walking
    daily_logs in order and subtracting each day's mortality — same underlying idea as
    `PoultryBatch.current_count`'s own computed property, but walked day-by-day here so earlier
    points in the series are correct too, not just the final total).
    """
    from apps.batches.services import day_of_cycle

    logs = sorted(batch.daily_logs.all(), key=lambda log: log.log_date)
    running_count = batch.initial_count
    points = []
    for log in logs:
        running_count = max(0, running_count - log.mortality)
        points.append({
            'dayOfCycle': day_of_cycle(batch, log.log_date),
            'weightKg': log.avg_sample_weight,
            'survivalPct': round(running_count / batch.initial_count * 100, 2) if batch.initial_count else None,
        })
    return points


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


def farm_health_score(farm):
    """Single synthesized farm-wide status (2026-08-26, docs/deviations.md Part 16, Part A) —
    `{'tier': 'good'|'watch'|'critical', 'label': str, 'reason': str}`.

    Combines three signals, each reusing an existing threshold/constant rather than inventing a
    new one:

    1. **Mortality trend breach**, per active batch — the *exact* pro-rata formula
       `WeeklyKpiCharts.jsx` already uses to color a week's bar red (`w.mortalityPct > 5 /
       weeks.length`), applied to `weekly_kpi(batch)`'s latest week: `latest_week.mortalityPct >
       MORTALITY_REFERENCE_RANGE[1] / len(weeks)`. Not duplicated as a literal `5` here — it's
       `MORTALITY_REFERENCE_RANGE[1]`, the same module-level constant that chart's own backend
       data already comes from.
    2. **FCR trend breach**, per active batch — latest `feed_conversion_ratio(batch)` above
       `FCR_REFERENCE_RANGE[1]` (2.30, "unfavorable"), the same constant `weekly_kpi`'s own
       `referenceRange.feedConversionRatio` already sends to the frontend.
    3. **Open `Alert` count**, farm-wide — `status` (not `is_read`, which is sidebar-bell
       read-state, a different concept — see `Alert.is_read`'s own docstring) not `RESOLVED`.

    Tier rules (the exact rule set, so this is auditable rather than a black box — see README
    "Farm health score" for the same table):

    - **critical** ("Critique"): 2+ batches have a breach (mortality and/or FCR, counted
      per-batch-per-signal — a single batch breaching both counts as 2), OR any open `Alert`
      has `severity='danger'` (the only two automatically-fired rule types are `LOW_STOCK` and
      `CONSUMPTION_DEVIATION` — `LOW_STOCK` always fires at `severity='danger'`, so this
      condition is really "any stock-out alert is still open").
    - **watch** ("À surveiller"): exactly 1 batch has a breach, OR at least 1 `Alert` is open at
      all (even `severity='warning'`). "Open" is `apps.alerts.services.open_problem_alerts`:
      task reminders (PROTOCOL_TASK / WEIGHING_REMINDER) are notifications, not problems.
    - **good** ("Bonne"): none of the above — no breaches, no open alerts.

    Note on this feature's original task premise: it named `MORTALITY_SPIKE`/`WEIGHT_DEVIATION`
    as alert types to check for — neither exists in `AlertRuleType` (checked before writing
    anything; the real, automatically-fired types are only `LOW_STOCK` and
    `CONSUMPTION_DEVIATION`, see that enum's own docstring). The mortality/FCR breach signals
    above are computed directly from `weekly_kpi`/`feed_conversion_ratio` instead of trying to
    find alert rows that don't exist — which is what the task's own item 1 already asked for as
    the first two signals anyway, independent of the (mis-named) alert-type check in item 2's
    example.
    """
    from apps.alerts.services import open_problem_alerts
    from apps.batches.models import BatchStatus, PoultryBatch

    # Logs fetched once for every batch: weekly_kpi and feed_conversion_ratio each walk them.
    active_batches = list(
        PoultryBatch.objects.filter(house__farm=farm, status=BatchStatus.ACTIVE).prefetch_related('daily_logs')
    )
    breaches = []  # [(batch, 'mortalité'|'IC')]
    for batch in active_batches:
        kpi = weekly_kpi(batch)
        weeks = kpi['weeks']
        if weeks and weeks[-1]['mortalityPct'] > MORTALITY_REFERENCE_RANGE[1] / len(weeks):
            breaches.append((batch, 'mortalité'))
        fcr = feed_conversion_ratio(batch)
        if fcr is not None and fcr > FCR_REFERENCE_RANGE[1]:
            breaches.append((batch, 'IC'))

    open_alerts = open_problem_alerts(farm)
    open_count = open_alerts.count()
    danger_open = open_alerts.filter(severity='danger').exists()

    reasons = [f'{kind} au-dessus de la norme sur la bande {batch.name or batch.batch_code}' for batch, kind in breaches]
    if open_count:
        reasons.append(f"{open_count} alerte{'s' if open_count > 1 else ''} ouverte{'s' if open_count > 1 else ''}")

    if len(breaches) >= 2 or danger_open:
        tier, label = 'critical', 'Critique'
    elif len(breaches) == 1 or open_count >= 1:
        tier, label = 'watch', 'À surveiller'
    else:
        tier, label = 'good', 'Bonne'
        reasons = ['Aucune alerte ouverte, mortalité et IC dans la norme sur toutes les bandes actives']

    return {'tier': tier, 'label': label, 'reason': ', '.join(reasons)}


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
