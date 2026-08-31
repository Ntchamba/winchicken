from datetime import timedelta

from celery import shared_task
from django.utils import timezone

from apps.alerts.models import SmsMessage, SmsStatus
from apps.alerts.providers import get_sms_provider

MAX_RETRIES = 5
BASE_BACKOFF_SECONDS = 30


@shared_task
def check_scheduled_alerts():
    """Celery Beat entry point — runs every minute (see `config.celery.app.conf.beat_schedule`).
    Fires the Alert + SMS for any active SCHEDULED AlertRule whose `trigger_time` matches the
    current farm-local time and whose schedule says it is due today. Idempotent — safe to run
    every minute and to re-run after a delay (brief Beat outage). Returns the number of Alerts
    created, for the task result log."""
    from apps.alerts.services import fire_scheduled_alerts

    created = fire_scheduled_alerts()
    return len(created)


@shared_task
def send_web_push_task(farm_id: int, payload: dict):
    """Deliver one desktop notification `payload` to every browser subscribed for the farm.
    Queued (never inline) by `apps.alerts.notify.notify_farm` on transaction commit. Returns
    the number of successful deliveries."""
    from apps.alerts.push import send_web_push_to_farm

    return send_web_push_to_farm(farm_id, payload)


@shared_task(bind=True, max_retries=MAX_RETRIES)
def send_sms_task(self, sms_message_id: int):
    """Sends one SmsMessage. Idempotent via idempotency_key — safe to replay on worker crash.

    Never called synchronously from a view; always queued after the triggering write commits.
    """
    try:
        sms = SmsMessage.objects.get(pk=sms_message_id)
    except SmsMessage.DoesNotExist:
        return

    if sms.provider_status in (SmsStatus.SENT, SmsStatus.DELIVERED):
        return  # already handled — idempotency guard against task replay

    provider = get_sms_provider()
    result = provider.send(sms.recipient, sms.alert.message)

    if result['success']:
        sms.provider_status = SmsStatus.SENT
        sms.provider = result.get('provider_message_id') or 'unknown'
        sms.sent_at = timezone.now()
        sms.save(update_fields=['provider_status', 'provider', 'sent_at'])
        return

    sms.retry_count += 1
    if sms.retry_count >= MAX_RETRIES:
        sms.provider_status = SmsStatus.FAILED
        sms.save(update_fields=['provider_status', 'retry_count'])
        return

    backoff_seconds = BASE_BACKOFF_SECONDS * (2 ** (sms.retry_count - 1))
    sms.next_retry_at = timezone.now() + timedelta(seconds=backoff_seconds)
    sms.save(update_fields=['retry_count', 'next_retry_at'])
    raise self.retry(countdown=backoff_seconds)
