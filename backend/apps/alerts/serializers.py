from rest_framework import serializers

from apps.alerts.models import Alert, AlertRule, NotificationPreference, SmsMessage


class AlertRuleSerializer(serializers.ModelSerializer):
    """GET/POST payload for /api/alert-rules/. EVENT-mode rules (LOW_STOCK,
    CONSUMPTION_DEVIATION) are actually created automatically via `get_or_create` the first time
    they fire (see apps.alerts.services.trigger_alert) — manual creation through this endpoint is
    mainly useful for SCHEDULED-mode rules or for pre-seeding threshold values."""

    class Meta:
        model = AlertRule
        fields = ['id', 'rule_type', 'trigger_mode', 'threshold', 'frequency', 'trigger_time', 'active_days', 'active']
        read_only_fields = ['id']
        extra_kwargs = {
            'threshold': {'help_text': 'Set for EVENT-mode rules; null for SCHEDULED-mode rules.'},
            'frequency': {'help_text': 'Set for SCHEDULED-mode rules (DAILY/WEEKLY/ONE_TIME); null for EVENT-mode rules.'},
        }

    def create(self, validated_data):
        validated_data['farm'] = self.context['request'].user.farm
        return super().create(validated_data)


class AlertSerializer(serializers.ModelSerializer):
    """GET /api/alerts/ response row — a triggered occurrence of an AlertRule."""

    ruleType = serializers.CharField(source='rule.rule_type', read_only=True)

    class Meta:
        model = Alert
        fields = ['id', 'rule', 'ruleType', 'batch', 'triggered_at', 'status', 'message', 'severity']
        read_only_fields = ['id', 'triggered_at']


class SmsMessageSerializer(serializers.ModelSerializer):
    """GET /api/sms-messages/ response row — read-only history of one SMS send attempt,
    including its exponential-backoff retry state (see apps.alerts.tasks.send_sms_task)."""

    class Meta:
        model = SmsMessage
        fields = [
            'id', 'alert', 'recipient', 'idempotency_key', 'provider_status',
            'provider', 'retry_count', 'next_retry_at', 'sent_at', 'created_at',
        ]
        read_only_fields = fields


class NotificationPreferenceSerializer(serializers.ModelSerializer):
    """GET/POST payload for /api/notification-preferences/ — one (user, rule_type) channel
    preference. `user` is always the requesting user in practice (the view forces it in
    perform_create, ignoring any `user` submitted in the body) despite `user` being a writable
    field on this serializer."""

    class Meta:
        model = NotificationPreference
        fields = ['id', 'user', 'rule_type', 'preferred_channel', 'active']
        read_only_fields = ['id']
