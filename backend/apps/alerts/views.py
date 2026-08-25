from rest_framework import generics
from rest_framework.permissions import IsAuthenticated

from apps.alerts.models import Alert, AlertRule, NotificationPreference, SmsMessage
from apps.alerts.serializers import (
    AlertRuleSerializer,
    AlertSerializer,
    NotificationPreferenceSerializer,
    SmsMessageSerializer,
)
from apps.core.permissions import IsAdminOrFarmManager


class AlertRuleListCreateView(generics.ListCreateAPIView):
    """GET/POST /api/alert-rules/ — list/create alert rules for the farm.
    Reserved to Admin / Farm Manager (section 8) for both listing and creation."""

    serializer_class = AlertRuleSerializer
    permission_classes = [IsAdminOrFarmManager]

    def get_queryset(self):
        return AlertRule.objects.filter(farm=self.request.user.farm)


class AlertListView(generics.ListAPIView):
    """GET /api/alerts/ — filterable by ?batch_code=."""

    serializer_class = AlertSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = Alert.objects.filter(rule__farm=self.request.user.farm)
        batch_code = self.request.query_params.get('batch_code')
        if batch_code:
            qs = qs.filter(batch_id=batch_code)
        return qs


class SmsMessageListView(generics.ListAPIView):
    """GET /api/sms-messages/ — SMS send history (provider status, retry attempts).
    Reserved to Admin / Farm Manager."""

    serializer_class = SmsMessageSerializer
    permission_classes = [IsAdminOrFarmManager]

    def get_queryset(self):
        return SmsMessage.objects.filter(alert__rule__farm=self.request.user.farm)


class NotificationPreferenceListView(generics.ListCreateAPIView):
    """GET/PUT /api/notification-preferences/ — list is scoped to the requesting user; create/update sets their own."""

    serializer_class = NotificationPreferenceSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return NotificationPreference.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)
