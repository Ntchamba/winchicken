"""Shared protocol logic used by both the onboarding endpoint and the live protocol editor.

`UNIT_TO_DAYS` moved here from apps.protocols.views (2026-08-25) so `expand_protocol_to_alert_rules`
can share it without a views->views import.
"""
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

UNIT_TO_DAYS = {'DAY': 1, 'WEEK': 7, 'MONTH': 30}


def to_days(value, unit):
    return value * UNIT_TO_DAYS.get(unit, 1)


def expand_protocol_to_alert_rules(batch):
    """(Re)generates PROTOCOL_TASK AlertRule rows for `batch` from its house's current
    ProtocolTemplate lines, one per line, each scheduled at `batch.start_date + from_value`
    (converted to days). Called both at batch creation (apps.protocols.views.OnboardingView,
    apps.batches.views.PoultryBatchListCreateView.perform_create) and whenever the house's
    protocol is saved for a house with an active batch (apps.houses.views.HouseProtocolView.put)
    — this is the single place that logic lives, so both call sites stay in sync automatically.

    2026-08-25: no such expansion existed anywhere in the codebase before this — the cahier des
    charges (section 4.6) documents the *intent* ("Étendu en lignes AlertRule à la création
    d'une bande, décalées par rapport à PoultryBatch.startDate"), but nothing implemented it
    (docs/deviations.md #16). This function is that implementation, extended to also handle
    protocol *edits* on an already-active batch (not just batch creation) per this task's Part C.

    "Regenerate" means: delete the batch's not-yet-fired PROTOCOL_TASK rules (future-dated
    ONE_TIME rows, and every recurring per-time-slot row), then recreate from the current
    protocol. Past-dated ONE_TIME rows and anything already deactivated (a fired ONE_TIME) are
    left untouched — once a date has gone by, a stale reminder is indistinguishable from "already
    happened", and nothing marks Alert/SmsMessage rows sent automatically (see AlertRule's
    docstring). Wrapped in one transaction so a failure can't leave a batch half-regenerated.

    Two shapes of rule per line (2026-08-31 — "fire at the configured créneaux"):
      * line HAS `ProtocolTimeSlot` rows → one DAILY rule per slot, `trigger_time =
        slot.start_time`, no `scheduled_date`. `apps.alerts.services.fire_scheduled_alerts` then
        fires it at that wall-clock time on every day the line's day-range covers.
      * line has NO slots → a single ONE_TIME rule at 08:00 on `start_date + from_value` — a
        one-off "do this around day X" with no specific time, unchanged from before.
    """
    from django.db.models import Q

    from apps.alerts.models import AlertRule, AlertRuleType, ScheduleFrequency, TriggerMode
    from apps.protocols.models import ProtocolTemplate

    today = timezone.localdate()

    with transaction.atomic():
        AlertRule.objects.filter(
            Q(scheduled_date__gte=today) | Q(scheduled_date__isnull=True),
            batch=batch, rule_type=AlertRuleType.PROTOCOL_TASK, active=True,
        ).delete()

        new_rules = []
        for line in ProtocolTemplate.objects.filter(house=batch.house).prefetch_related('time_slots'):
            slots = list(line.time_slots.all())
            if slots:
                for slot in slots:
                    new_rules.append(AlertRule(
                        farm=batch.house.farm,
                        rule_type=AlertRuleType.PROTOCOL_TASK,
                        trigger_mode=TriggerMode.SCHEDULED,
                        frequency=ScheduleFrequency.DAILY,
                        trigger_time=slot.start_time,
                        batch=batch,
                        protocol_line=line,
                    ))
                continue
            scheduled_date = batch.start_date + timedelta(days=to_days(line.from_value, line.from_unit))
            if scheduled_date < today:
                continue
            new_rules.append(AlertRule(
                farm=batch.house.farm,
                rule_type=AlertRuleType.PROTOCOL_TASK,
                trigger_mode=TriggerMode.SCHEDULED,
                frequency=ScheduleFrequency.ONE_TIME,
                trigger_time='08:00',
                batch=batch,
                protocol_line=line,
                scheduled_date=scheduled_date,
            ))
        AlertRule.objects.bulk_create(new_rules)

    return new_rules
