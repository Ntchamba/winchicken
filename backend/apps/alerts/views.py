import base64
import hashlib
import hmac

from django.conf import settings
from rest_framework import generics, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.alerts.models import Alert, AlertRule, NotificationPreference, SmsMessage, SmsStatus
from apps.alerts.serializers import (
    AlertRuleSerializer,
    AlertSerializer,
    AlertUpdateSerializer,
    NotificationPreferenceSerializer,
    SmsMessageSerializer,
)
from apps.core.permissions import IsAdminOrFarmManager

TWILIO_STATUS_MAP = {
    'queued': SmsStatus.PENDING,
    'sending': SmsStatus.PENDING,
    'sent': SmsStatus.SENT,
    'delivered': SmsStatus.DELIVERED,
    'undelivered': SmsStatus.FAILED,
    'failed': SmsStatus.FAILED,
}


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


class AlertDetailView(generics.RetrieveUpdateAPIView):
    """GET/PATCH /api/alerts/{id}/ — acknowledge (SENT) or resolve (RESOLVED) an alert.
    Any authenticated user of the farm can transition an alert's status (matches AlertListView's
    read access — acknowledging an alert isn't a privileged action)."""

    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        if self.request.method in ('PATCH', 'PUT'):
            return AlertUpdateSerializer
        return AlertSerializer

    def get_queryset(self):
        return Alert.objects.filter(rule__farm=self.request.user.farm)


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


def _verify_twilio_signature(request, auth_token):
    """Twilio's webhook signing scheme: HMAC-SHA1 of the full callback URL with every POST
    param (sorted by key, key+value concatenated with no separator) appended, keyed with the
    account's auth token, base64-encoded, compared against the X-Twilio-Signature header.
    https://www.twilio.com/docs/usage/webhooks/webhooks-security
    """
    signature = request.headers.get('X-Twilio-Signature')
    if not signature or not auth_token:
        return False

    url = request.build_absolute_uri(request.path)
    data = url
    for key in sorted(request.POST.keys()):
        data += key + request.POST[key]

    computed = base64.b64encode(
        hmac.new(auth_token.encode('utf-8'), data.encode('utf-8'), hashlib.sha1).digest()
    ).decode('utf-8')

    return hmac.compare_digest(computed, signature)


class SmsDeliveryWebhookView(APIView):
    """POST /api/alerts/sms/webhook/ — Twilio delivery-status callback
    (SMS_STATUS_CALLBACK_URL). Verifies X-Twilio-Signature before touching the DB; a request
    with a missing/invalid signature is rejected with 403 and never updates anything.
    Public by design (called by Twilio, not a logged-in account) but rate-limited via the
    'sms_webhook' throttle scope."""

    permission_classes = [AllowAny]
    throttle_scope = 'sms_webhook'

    def post(self, request):
        if not _verify_twilio_signature(request, settings.SMS_PROVIDER_API_KEY):
            return Response({'detail': 'Invalid signature.'}, status=status.HTTP_403_FORBIDDEN)

        message_sid = request.POST.get('MessageSid') or request.POST.get('SmsSid')
        message_status = (request.POST.get('MessageStatus') or '').lower()
        if not message_sid or message_status not in TWILIO_STATUS_MAP:
            return Response({'detail': 'Unrecognized payload.'}, status=status.HTTP_400_BAD_REQUEST)

        updated = SmsMessage.objects.filter(provider=message_sid).update(
            provider_status=TWILIO_STATUS_MAP[message_status]
        )
        return Response({'updated': updated}, status=status.HTTP_200_OK)
