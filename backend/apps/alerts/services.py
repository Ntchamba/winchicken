import hashlib
import logging
from datetime import timedelta
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.alerts.models import (
    Alert, AlertRule, AlertRuleType, NotificationChannel, NotificationPreference,
    ScheduleFrequency, TriggerMode,
)
from apps.alerts.tasks import send_sms_task

logger = logging.getLogger(__name__)

# How many minutes back from "now" to still fire a scheduled reminder, so a brief Beat outage
# (worker restart, redis hiccup) doesn't silently skip one. The per-rule idempotency check
# below stops the catch-up run from re-firing anything already sent. Decision: 3 minutes — long
# enough for a normal restart, short enough that a reminder is never meaningfully late.
SCHEDULED_ALERT_TOLERANCE_MINUTES = 3


def _idempotency_key(rule_type, batch_code, recipient, salt):
    raw = f'{rule_type}:{batch_code}:{recipient}:{salt}'
    return hashlib.sha256(raw.encode()).hexdigest()[:40]


def trigger_alert(farm, rule_type, message, severity='warning', batch=None, salt=''):
    """Creates (or reuses) an EVENT AlertRule + Alert, then queues SMS for users who opted in.

    Routine reminders can be routed to PUSH instead of SMS via NotificationPreference — SMS
    stays reserved for alerts the user actually chose to receive by SMS.
    """
    rule, _ = AlertRule.objects.get_or_create(
        farm=farm, rule_type=rule_type, trigger_mode='EVENT', defaults={'active': True}
    )
    alert = Alert.objects.create(rule=rule, batch=batch, message=message, severity=severity)

    recipients = NotificationPreference.objects.filter(
        user__farm=farm, rule_type=rule_type, active=True, preferred_channel=NotificationChannel.SMS
    ).select_related('user')

    for pref in recipients:
        if not pref.user.phone:
            continue
        idempotency_key = _idempotency_key(rule_type, batch.batch_code if batch else 'farm', pref.user.phone, salt)
        sms, created = alert.sms_messages.get_or_create(
            idempotency_key=idempotency_key,
            defaults={'recipient': pref.user.phone},
        )
        if created:
            transaction.on_commit(lambda sms_id=sms.id: send_sms_task.delay(sms_id))

    return alert


def check_low_stock(item):
    from apps.stock.calculations import current_quantity

    if current_quantity(item) >= item.alert_threshold:
        return
    trigger_alert(
        farm=item.farm,
        rule_type=AlertRuleType.LOW_STOCK,
        message=f'{item.name} sous le seuil ({current_quantity(item)}{item.unit} < {item.alert_threshold}{item.unit})',
        severity='danger',
        salt=str(current_quantity(item)),
    )


def check_consumption_deviation(daily_log):
    if not daily_log.feed_consumed_kg:
        return
    ratio = daily_log.water_consumed_l / daily_log.feed_consumed_kg
    if 1.6 <= ratio <= 2.2:
        return
    batch = daily_log.batch
    trigger_alert(
        farm=batch.house.farm,
        rule_type=AlertRuleType.CONSUMPTION_DEVIATION,
        message=f'Ratio eau/aliment {ratio:.2f} hors norme 1,6-2,2 — {batch.batch_code}',
        severity='warning',
        batch=batch,
        salt=str(daily_log.log_date),
    )


# ---------------------------------------------------------------------------
# SCHEDULED task reminders — the time-based trigger (2026-08-30)
# ---------------------------------------------------------------------------
# SCHEDULED AlertRule rows (PROTOCOL_TASK, WEIGHING_REMINDER) store a `trigger_time` and were
# always created correctly, but nothing evaluated them — this project had no per-minute Beat
# schedule. `fire_scheduled_alerts` is that evaluator, run every minute by
# `apps.alerts.tasks.check_scheduled_alerts`. It reuses the existing day-range / weighing
# helpers (no parallel schedule logic) and the existing task-reminder templates, and creates
# ordinary `Alert` rows so the notification bell + SMS path behave exactly as for EVENT alerts.


def _trigger_time_window(now_local):
    """Q over AlertRule.trigger_time in [now - tolerance, now], handling the midnight wrap."""
    end = now_local.time()
    start = (now_local - timedelta(minutes=SCHEDULED_ALERT_TOLERANCE_MINUTES)).time()
    if start <= end:
        return Q(trigger_time__gte=start, trigger_time__lte=end)
    return Q(trigger_time__gte=start) | Q(trigger_time__lte=end)


def _weekday_token(d):
    return d.strftime('%a').upper()[:3]  # MON, TUE, ...


def _rule_should_fire_today(rule, today_local):
    """Whether `rule`'s schedule says today is a firing day — delegates to the same helpers the
    live "tâches à effectuer maintenant" view uses so the two never diverge."""
    from apps.batches.models import BatchStatus
    from apps.batches.services import weighing_reminder_task
    from apps.houses.services import _protocol_line_occurrence

    batch = rule.batch
    if batch is None or batch.status != BatchStatus.ACTIVE:
        return False  # every SCHEDULED reminder type is batch-scoped

    if rule.active_days:
        allowed = {t.strip().upper()[:3] for t in rule.active_days.replace(',', ' ').split() if t.strip()}
        if allowed and _weekday_token(today_local) not in allowed:
            return False

    day_of_cycle = (today_local - batch.start_date).days
    if day_of_cycle < 0:
        return False

    if rule.rule_type == AlertRuleType.WEIGHING_REMINDER:
        return weighing_reminder_task(batch, day_of_cycle) is not None  # DAILY/WEEKLY/MONTHLY cadence

    if rule.protocol_line_id and _protocol_line_occurrence(rule.protocol_line, day_of_cycle) is None:
        return False  # protocol edited since — today is outside the originating line's day range

    if (
        rule.frequency == ScheduleFrequency.ONE_TIME
        and rule.scheduled_date is not None
        and rule.scheduled_date != today_local
    ):
        return False

    return True


def _already_fired(rule, batch):
    """A scheduled rule fires at most once per local day. `Alert` has no date/time columns, so
    "this occurrence already fired" = an Alert for this rule+batch in the last 10 minutes —
    comfortably wider than the 3-minute catch-up window, far narrower than a day's cadence, and
    with no midnight-boundary edge case."""
    since = timezone.now() - timedelta(minutes=10)
    return Alert.objects.filter(rule=rule, batch=batch, triggered_at__gte=since).exists()


def _resolve_scheduled_reminder(rule):
    """[(recipient User, message str), ...] for a fired SCHEDULED rule, via the existing
    task-reminder template building blocks. PROTOCOL_TASK -> the line's assigned employees else
    the batch Fermier, timed to the matching ProtocolTimeSlot when there is one.
    WEIGHING_REMINDER -> the rule's assignees else the batch Fermier.

    A list since 2026-09-16 (FIX 7): both carriers hold several assignees now, and picking one of
    them would silently leave the others unwarned. Each gets their own message, greeted by name;
    they still share the single occurrence.
    """
    from apps.alerts.templates import render_task_reminder, resolve_task_reminder_recipients

    batch = rule.batch
    house_name = batch.house.name

    if rule.rule_type == AlertRuleType.WEIGHING_REMINDER:
        recipients = list(rule.assignees.all()) or ([batch.farmer] if batch.farmer else [])
        return [
            (recipient, render_task_reminder(recipient, 'la pesée d’un échantillon de la bande', house_name))
            for recipient in recipients
        ]

    line = rule.protocol_line
    if line is None:
        return []
    recipients = resolve_task_reminder_recipients(line, batch)
    slots = list(line.time_slots.all())
    start_time = next((s.start_time for s in slots if s.start_time == rule.trigger_time), None)
    if start_time is None and slots:
        start_time = slots[0].start_time
    return [
        (recipient, render_task_reminder(recipient, line.what, house_name, start_time=start_time))
        for recipient in recipients
    ]


def _queue_reminder_sms(alert, recipient, message):
    """Queue one SMS for the reminder's resolved recipient — same idempotent get_or_create +
    on_commit(send_sms_task.delay) as `trigger_alert`. Not gated by NotificationPreference:
    scheduled task reminders are personal job assignments to the responsible user, not the
    opt-in farm-wide EVENT alerts that preference table throttles."""
    if not recipient or not recipient.phone:
        return
    # One SMS per rule per local day. Keyed on rule id (not trigger_time) because several
    # protocol lines can share one créneau, and each line's rule must get its own SMS.
    key = _idempotency_key(
        alert.rule.rule_type,
        alert.batch.batch_code if alert.batch else 'farm',
        recipient.phone,
        salt=f'{alert.rule_id}:{alert.triggered_at.date()}',
    )
    sms, created = alert.sms_messages.get_or_create(
        idempotency_key=key, defaults={'recipient': recipient.phone},
    )
    if created:
        transaction.on_commit(lambda sms_id=sms.id: send_sms_task.delay(sms_id))


def fire_scheduled_alerts(now=None):
    """Create the Alert + queue the SMS for every active SCHEDULED AlertRule whose trigger_time
    matches the current farm-local time (within a 3-minute catch-up window) and whose schedule
    says it is due today. Returns the Alert rows created this run. Idempotent — safe to run
    every minute and to re-run after a delay."""
    now_local = (now or timezone.now()).astimezone(ZoneInfo(settings.FARM_TIME_ZONE))
    today_local = now_local.date()
    logger.info('fire_scheduled_alerts: farm_tz=%s local_now=%s', settings.FARM_TIME_ZONE, now_local.isoformat())

    rules = (
        AlertRule.objects
        .filter(_trigger_time_window(now_local), trigger_mode=TriggerMode.SCHEDULED, active=True, trigger_time__isnull=False)
        .select_related('batch', 'batch__house', 'batch__house__farm', 'batch__farmer', 'protocol_line')
        .prefetch_related('assignees', 'protocol_line__assignees')
    )

    created = []
    for rule in rules:
        if not _rule_should_fire_today(rule, today_local):
            continue
        if _already_fired(rule, rule.batch):
            continue

        reminders = _resolve_scheduled_reminder(rule)
        with transaction.atomic():
            # One Alert per occurrence (it is the farm's record that the task came due), but one
            # SMS per assignee — `_queue_reminder_sms` keys its idempotency on the recipient's
            # phone, so several messages under one Alert do not collide.
            alert = Alert.objects.create(
                rule=rule, batch=rule.batch, message=reminders[0][1] if reminders else '', severity='info',
            )
            for recipient, message in reminders:
                _queue_reminder_sms(alert, recipient, message)
            if rule.frequency == ScheduleFrequency.ONE_TIME:
                AlertRule.objects.filter(pk=rule.pk).update(active=False)  # fire once, never re-evaluate
        created.append(alert)

    return created
