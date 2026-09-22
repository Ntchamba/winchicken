import os

from celery import Celery
from celery.schedules import crontab

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

app = Celery('winchicken')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()

# Drives every SCHEDULED-mode AlertRule (recurring feeding/vaccination reminders,
# VACCINE_DUE/SANITARY_VOID_END rows generated from protocol lines) — see
# apps.alerts.tasks.evaluate_scheduled_alert_rules. Every 5 minutes matches that task's own
# SCHEDULE_WINDOW_MINUTES, so no scheduled rule's trigger_time is ever missed between two runs.
app.conf.beat_schedule = {
    'evaluate-scheduled-alert-rules': {
        'task': 'apps.alerts.tasks.evaluate_scheduled_alert_rules',
        'schedule': crontab(minute='*/5'),
    },
}
