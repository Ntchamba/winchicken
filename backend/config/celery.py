import os

from celery import Celery
from celery.schedules import crontab

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

app = Celery('winchicken')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()

# Static beat_schedule rather than django-celery-beat — no new dependency, consistent with the
# existing `CELERY_*` settings style. Run with `celery -A config beat`.
app.conf.beat_schedule = {
    # NOTE: there is deliberately NO automatic stock-deduction entry here. Stock is only ever
    # deducted by an explicit user action ("Marquer comme fait" on a protocol task occurrence,
    # or executing a composition) — see docs/deviations.md. The 2026-08-28 daily-stock-consumption
    # task was removed 2026-08-31.
    # Time-based trigger for SCHEDULED task reminders (2026-08-30) — every minute, since
    # AlertRule.trigger_time is hour:minute-specific. apps.alerts.services.fire_scheduled_alerts
    # is idempotent, so a minute cadence + a small catch-up window is safe.
    'check-scheduled-alerts': {
        'task': 'apps.alerts.tasks.check_scheduled_alerts',
        'schedule': crontab(),  # every minute
    },
}
