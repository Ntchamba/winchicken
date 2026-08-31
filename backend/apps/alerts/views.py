from django.shortcuts import get_object_or_404
from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

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


class AlertMarkReadView(APIView):
    """POST /api/alerts/{id}/mark-read/ — sidebar notification bell "Marquer comme lu".
    Farm-scoped like AlertListView, so one farm can't mark another's alert read."""

    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        alert = get_object_or_404(Alert, pk=pk, rule__farm=request.user.farm)
        alert.is_read = True
        alert.save(update_fields=['is_read'])
        return Response(AlertSerializer(alert).data)


class AlertMarkAllReadView(APIView):
    """POST /api/alerts/mark-all-read/ — sidebar notification bell "Tout marquer comme lu"."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        Alert.objects.filter(rule__farm=request.user.farm, is_read=False).update(is_read=True)
        return Response({'status': 'ok'})


class AlertUnreadCountView(APIView):
    """GET /api/alerts/unread-count/ — badge count for the sidebar notification bell."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        count = Alert.objects.filter(rule__farm=request.user.farm, is_read=False).count()
        return Response({'count': count})


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


class PushPublicKeyView(APIView):
    """GET /api/push-public-key/ — the VAPID public key the service worker needs to subscribe,
    plus whether push is configured at all. Public-ish (any authenticated user)."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        from django.conf import settings
        return Response({
            'publicKey': settings.VAPID_PUBLIC_KEY,
            'enabled': settings.WEB_PUSH_ENABLED,
        })


class PushSubscriptionView(APIView):
    """POST /api/push-subscriptions/ — upsert the caller's browser Web Push subscription
    (body: the PushSubscription JSON from the browser). DELETE /api/push-subscriptions/ —
    remove it (body: {"endpoint": ...}). Scoped to the requesting user + their farm."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        from apps.alerts.models import PushSubscription

        endpoint = request.data.get('endpoint')
        keys = request.data.get('keys') or {}
        p256dh, auth = keys.get('p256dh'), keys.get('auth')
        if not (endpoint and p256dh and auth):
            return Response({'detail': 'Abonnement push invalide.'}, status=400)

        PushSubscription.objects.update_or_create(
            endpoint=endpoint,
            defaults={
                'farm': request.user.farm,
                'user': request.user,
                'p256dh': p256dh,
                'auth': auth,
                'user_agent': request.META.get('HTTP_USER_AGENT', '')[:255],
            },
        )
        return Response(status=201)

    def delete(self, request):
        from apps.alerts.models import PushSubscription

        endpoint = request.data.get('endpoint')
        if endpoint:
            PushSubscription.objects.filter(endpoint=endpoint, user=request.user).delete()
        return Response(status=204)
