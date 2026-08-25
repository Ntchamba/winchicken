import hashlib

from django.db import transaction

from apps.alerts.models import Alert, AlertRule, AlertRuleType, NotificationChannel, NotificationPreference
from apps.alerts.tasks import send_sms_task


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
