"""Business logic for the batches app, kept out of views.py per this project's "thin views"
convention (2026-08-25 reorg — see docs/architecture.md). Views orchestrate HTTP concerns
(permissions, status codes, request parsing); anything with more than one DB step or a
computation beyond a one-line expression lives here instead.
"""
from django.db import transaction

from apps.batches.calculations import MORTALITY_REFERENCE_RANGE, mortality_pct
from apps.batches.models import DailyLog


def finalize_new_batch(batch):
    """Runs after a `PoultryBatch` row is created, from every creation path (onboarding, the
    plain `POST /api/batches/`) — expands the house's current protocol into this batch's
    `PROTOCOL_TASK` `AlertRule` rows, and (2026-08-25) generates its `WEIGHING_REMINDER` row if
    `weighing_frequency` was set at creation. Wrapped by the caller in the same transaction as
    the batch's own creation.
    """
    from apps.protocols.services import expand_protocol_to_alert_rules
    expand_protocol_to_alert_rules(batch)
    sync_weighing_reminder(batch)


def record_quick_entry(batch, log_date, mortality=None, eggs_collected=None, avg_sample_weight=None):
    """Upserts one day's `DailyLog` for the quick-entry panel — mortality, eggs, and (2026-08-25)
    average sample weight, each independently optional so a weighing logged on a day that
    already has a mortality entry (or vice versa) never blanks out the other field. `None` means
    "the user didn't fill this in this submission," not "clear it to empty": only fields
    actually provided are written to `defaults`, so an omitted field keeps whatever value the
    row already had (or the model default, for a brand new row — `mortality`'s NOT NULL column
    needs *some* value on create, so it resolves to the previous value if the row already
    existed, else 0).

    `PoultryBatch.current_count` (2026-08-25) is a computed property (`initial_count` minus the
    sum of every `DailyLog.mortality` for the batch — see that property's docstring), so nothing
    needs writing here to keep it in sync: correcting an already-logged day's mortality (e.g. 5
    → 3) just changes what the next read of `current_count` sums over, automatically, with no
    delta-tracking required. The bound check below still reads `batch.current_count` *before*
    this upsert lands, then adds back `previous_mortality` — mathematically that yields "what the
    count would be with today's mortality at zero," the correct ceiling for `resolved_mortality`,
    identical to what the old stored-and-decremented field's version of this check computed.

    Returns `(log, cumulative_mortality_pct, reference_range, error_detail_or_None)`.
    """
    existing = DailyLog.objects.filter(batch=batch, log_date=log_date).first()
    previous_mortality = existing.mortality if existing else 0
    resolved_mortality = mortality if mortality is not None else previous_mortality
    if resolved_mortality > batch.current_count + previous_mortality:
        return None, None, None, "Ne peut pas dépasser l'effectif actuel de la bande."

    defaults = {'mortality': resolved_mortality}
    if eggs_collected is not None:
        defaults['eggs_collected'] = eggs_collected
    if avg_sample_weight is not None:
        defaults['avg_sample_weight'] = avg_sample_weight

    with transaction.atomic():
        log, _created = DailyLog.objects.update_or_create(batch=batch, log_date=log_date, defaults=defaults)

    return log, mortality_pct(batch), list(MORTALITY_REFERENCE_RANGE), None


def sync_weighing_reminder(batch):
    """(Re)generates the recurring `WEIGHING_REMINDER` `AlertRule` for `batch` from
    `PoultryBatch.weighing_frequency` — reuses the exact same `AlertRule` mechanism as
    `apps.protocols.services.expand_protocol_to_alert_rules` (2026-08-25 task: "don't build a
    parallel scheduling system"), but shaped differently since a weighing reminder is genuinely
    *recurring* rather than the one-shot, single-`scheduled_date` PROTOCOL_TASK rows: one
    `SCHEDULED` row with `frequency` set to the matching `ScheduleFrequency` value, no
    `scheduled_date`/`protocol_line` (those stay specific to PROTOCOL_TASK). Always deletes any
    existing `WEIGHING_REMINDER` row for this batch first — there is at most one at a time —
    then recreates it only if `weighing_frequency` is set. Like every other `SCHEDULED` rule in
    this project, the row is created correctly but nothing fires it (no Celery Beat schedule);
    see `AlertRuleType.WEIGHING_REMINDER`'s docstring.
    """
    from apps.alerts.models import AlertRule, AlertRuleType, ScheduleFrequency, TriggerMode

    AlertRule.objects.filter(batch=batch, rule_type=AlertRuleType.WEIGHING_REMINDER).delete()
    if not batch.weighing_frequency:
        return None

    frequency_map = {
        'DAY': ScheduleFrequency.DAILY,
        'WEEK': ScheduleFrequency.WEEKLY,
        'MONTH': ScheduleFrequency.MONTHLY,
    }
    return AlertRule.objects.create(
        farm=batch.house.farm,
        rule_type=AlertRuleType.WEIGHING_REMINDER,
        trigger_mode=TriggerMode.SCHEDULED,
        frequency=frequency_map[batch.weighing_frequency],
        trigger_time='08:00',
        batch=batch,
    )


WEIGHING_RECURRENCE_LABELS = {'DAY': 'Quotidienne', 'WEEK': 'Hebdomadaire', 'MONTH': 'Mensuelle'}


def weighing_reminder_task(batch, day_of_cycle):
    """Live counterpart to `sync_weighing_reminder`'s persisted `AlertRule`, for
    `apps.houses.views.HouseTasksNowView` (2026-08-25) — same "tâches à effectuer maintenant"
    live-computation pattern already used for protocol lines
    (`apps.protocols.services.to_days`), just keyed off `PoultryBatch.weighing_frequency`
    instead of a `ProtocolTemplate` row. "Due today" = `day_of_cycle` is an exact multiple of
    the cadence in days, counting from day 0 (the batch's start date is always a due day).
    Returns `None` if no frequency is set or today isn't a due day.
    """
    if not batch.weighing_frequency:
        return None
    from apps.protocols.services import to_days

    cadence_days = to_days(1, batch.weighing_frequency)
    if day_of_cycle % cadence_days != 0:
        return None

    return {
        'id': f'weighing-{batch.batch_code}',
        'category': 'Pesée',
        'icon': 'ClipboardList',
        'what': 'Peser un échantillon de la bande',
        'details': 'Alimente la courbe de croissance (poids moyen).',
        'periodDay': None,
        'periodLength': None,
        'recurrence': WEIGHING_RECURRENCE_LABELS[batch.weighing_frequency],
    }
