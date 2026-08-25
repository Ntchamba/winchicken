from django.conf import settings
from django.db import models

from apps.batches.models import PoultryBatch
from apps.core.models import Farm


class AlertRuleType(models.TextChoices):
    """Only LOW_STOCK (apps.alerts.services.check_low_stock, via StockMovement post_save) and
    CONSUMPTION_DEVIATION (check_consumption_deviation, via DailyLog post_save) are actually
    wired to a triggering signal in this codebase. VACCINE_DUE, PROFITABILITY_THRESHOLD and
    SANITARY_VOID_END exist as choices (and can be created manually via /api/alert-rules/) but
    nothing currently evaluates or fires them automatically — see docs/deviations.md."""

    LOW_STOCK = 'LOW_STOCK', 'Low stock'
    VACCINE_DUE = 'VACCINE_DUE', 'Vaccine due'
    CONSUMPTION_DEVIATION = 'CONSUMPTION_DEVIATION', 'Consumption deviation'
    PROFITABILITY_THRESHOLD = 'PROFITABILITY_THRESHOLD', 'Profitability threshold'
    SANITARY_VOID_END = 'SANITARY_VOID_END', 'Sanitary void end'


class TriggerMode(models.TextChoices):
    EVENT = 'EVENT', 'Event'
    SCHEDULED = 'SCHEDULED', 'Scheduled'


class ScheduleFrequency(models.TextChoices):
    DAILY = 'DAILY', 'Daily'
    WEEKLY = 'WEEKLY', 'Weekly'
    ONE_TIME = 'ONE_TIME', 'One time'


class AlertRule(models.Model):
    """EVENT rules set `threshold`; SCHEDULED rules set `trigger_time` + `frequency`.

    Only EVENT-mode rules (LOW_STOCK, CONSUMPTION_DEVIATION) actually fire in this codebase, via
    `apps.alerts.services.trigger_alert`'s `get_or_create` called from the two Django signal
    handlers in `apps.alerts.signals`. SCHEDULED-mode rules can be created through
    /api/alert-rules/ but nothing evaluates `trigger_time`/`frequency`/`active_days` — there is
    no Celery Beat schedule configured anywhere in this project (`config/celery.py` has no
    `beat_schedule`), so a SCHEDULED AlertRule never actually triggers an Alert. See
    docs/deviations.md.
    """

    farm = models.ForeignKey(Farm, on_delete=models.CASCADE, related_name='alert_rules')
    rule_type = models.CharField(max_length=32, choices=AlertRuleType.choices)
    trigger_mode = models.CharField(max_length=16, choices=TriggerMode.choices)
    threshold = models.FloatField(null=True, blank=True)
    frequency = models.CharField(max_length=16, choices=ScheduleFrequency.choices, null=True, blank=True)
    trigger_time = models.TimeField(null=True, blank=True)
    active_days = models.CharField(max_length=64, blank=True)
    active = models.BooleanField(default=True)

    def __str__(self):
        return f'{self.rule_type} ({self.trigger_mode})'


class AlertStatus(models.TextChoices):
    NEW = 'NEW', 'New'
    SENT = 'SENT', 'Sent'
    RESOLVED = 'RESOLVED', 'Resolved'


class Alert(models.Model):
    """One triggered occurrence of an AlertRule. Created by `apps.alerts.services.trigger_alert`,
    which also queues an SmsMessage per opted-in recipient. `status` defaults to NEW and is
    otherwise unmanaged by any code path in this codebase — nothing transitions it to SENT or
    RESOLVED automatically (frontend/manual PATCH only, and no such PATCH endpoint currently
    exists either; see docs/deviations.md)."""

    rule = models.ForeignKey(AlertRule, on_delete=models.CASCADE, related_name='alerts')
    batch = models.ForeignKey(PoultryBatch, on_delete=models.CASCADE, null=True, blank=True, related_name='alerts')
    triggered_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=16, choices=AlertStatus.choices, default=AlertStatus.NEW)
    message = models.CharField(max_length=500, blank=True)
    severity = models.CharField(max_length=16, default='warning')

    class Meta:
        ordering = ['-triggered_at']

    def __str__(self):
        return f'{self.rule.rule_type} · {self.triggered_at}'


class SmsStatus(models.TextChoices):
    PENDING = 'PENDING', 'Pending'
    SENT = 'SENT', 'Sent'
    DELIVERED = 'DELIVERED', 'Delivered'
    FAILED = 'FAILED', 'Failed'


class SmsMessage(models.Model):
    """retry_count / next_retry_at implement the exponential backoff required by the SMS gateway.
    idempotency_key prevents duplicates if Celery replays the task (e.g. worker crash after provider call).
    """

    alert = models.ForeignKey(Alert, on_delete=models.CASCADE, related_name='sms_messages')
    recipient = models.CharField(max_length=32)
    idempotency_key = models.CharField(max_length=128, unique=True)
    provider_status = models.CharField(max_length=16, choices=SmsStatus.choices, default=SmsStatus.PENDING)
    provider = models.CharField(max_length=64, blank=True)
    retry_count = models.PositiveIntegerField(default=0)
    next_retry_at = models.DateTimeField(null=True, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.recipient} · {self.provider_status}'


class NotificationChannel(models.TextChoices):
    SMS = 'SMS', 'SMS'
    PUSH = 'PUSH', 'Push'
    EMAIL = 'EMAIL', 'Email'


class NotificationPreference(models.Model):
    """Per-user, per-alert-type volume control — reserves SMS for critical alerts."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='notification_preferences')
    rule_type = models.CharField(max_length=32, choices=AlertRuleType.choices)
    preferred_channel = models.CharField(max_length=8, choices=NotificationChannel.choices, default=NotificationChannel.SMS)
    active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['user', 'rule_type'], name='one_preference_per_user_per_rule_type')
        ]

    def __str__(self):
        return f'{self.user_id} · {self.rule_type} · {self.preferred_channel}'
