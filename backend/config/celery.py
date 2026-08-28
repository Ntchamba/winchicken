import os

from celery import Celery
from celery.schedules import crontab

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

app = Celery('winchicken')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()

# The project's only Celery Beat schedule (2026-08-28, stock restructure Part E). Static
# beat_schedule rather than django-celery-beat — no new dependency, consistent with the
# existing `CELERY_*` settings style. Run with `celery -A config beat`. The pre-existing
# unfired SCHEDULED AlertRule types (PROTOCOL_TASK / WEIGHING_REMINDER) stay out of scope —
# see docs/deviations.md.
app.conf.beat_schedule = {
    'daily-stock-consumption': {
        'task': 'apps.stock.tasks.deduct_daily_stock_consumption',
        'schedule': crontab(hour=0, minute=0),
    },
}
