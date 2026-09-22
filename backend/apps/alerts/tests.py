import base64
import hashlib
import hmac
from datetime import date, timedelta

from django.test import TestCase, override_settings
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from apps.alerts.models import Alert, AlertRule, AlertRuleType, AlertStatus, ScheduleFrequency, TriggerMode
from apps.alerts.tasks import evaluate_scheduled_alert_rules
from apps.core.models import Farm, User, UserRole, create_role_profile


class ScheduledAlertRuleEvaluationTests(TestCase):
    """apps.alerts.tasks.evaluate_scheduled_alert_rules — the Celery Beat periodic task that
    drives SCHEDULED-mode AlertRule rows (see config/celery.py's beat_schedule)."""

    def setUp(self):
        self.farm = Farm.objects.create(name='Test Farm')

    def test_one_time_rule_due_today_fires_once(self):
        rule = AlertRule.objects.create(
            farm=self.farm, rule_type=AlertRuleType.VACCINE_DUE, trigger_mode=TriggerMode.SCHEDULED,
            frequency=ScheduleFrequency.ONE_TIME, fire_date=date.today(), note='Newcastle vaccine',
        )
        evaluate_scheduled_alert_rules.run()
        rule.refresh_from_db()
        self.assertIsNotNone(rule.fired_at)
        self.assertEqual(Alert.objects.filter(rule__farm=self.farm).count(), 1)

        # Running it again the same day must not create a second Alert.
        evaluate_scheduled_alert_rules.run()
        self.assertEqual(Alert.objects.filter(rule__farm=self.farm).count(), 1)

    def test_one_time_rule_not_yet_due_does_not_fire(self):
        AlertRule.objects.create(
            farm=self.farm, rule_type=AlertRuleType.VACCINE_DUE, trigger_mode=TriggerMode.SCHEDULED,
            frequency=ScheduleFrequency.ONE_TIME, fire_date=date.today() + timedelta(days=3),
        )
        evaluate_scheduled_alert_rules.run()
        self.assertEqual(Alert.objects.filter(rule__farm=self.farm).count(), 0)


class AlertStatusTransitionTests(APITestCase):
    def setUp(self):
        self.farm = Farm.objects.create(name='Test Farm')
        self.rule = AlertRule.objects.create(farm=self.farm, rule_type=AlertRuleType.LOW_STOCK, trigger_mode=TriggerMode.EVENT)
        self.alert = Alert.objects.create(rule=self.rule, message='Low stock')

    def _auth_as(self, role):
        user = User.objects.create_user(email=f'{role.lower()}@test.com', name='T', role=role, farm=self.farm)
        create_role_profile(user)
        token = RefreshToken.for_user(user)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token.access_token}')

    def test_any_authenticated_user_can_acknowledge_an_alert(self):
        self._auth_as(UserRole.WORKER)
        resp = self.client.patch(f'/api/alerts/{self.alert.id}/', {'status': 'RESOLVED'})
        self.assertEqual(resp.status_code, 200)
        self.alert.refresh_from_db()
        self.assertEqual(self.alert.status, AlertStatus.RESOLVED)


@override_settings(SMS_PROVIDER_API_KEY='test-auth-token')
class SmsWebhookSignatureTests(APITestCase):
    def _sign(self, url, params, token):
        data = url + ''.join(k + params[k] for k in sorted(params))
        return base64.b64encode(hmac.new(token.encode(), data.encode(), hashlib.sha1).digest()).decode()

    def test_missing_signature_is_rejected(self):
        resp = self.client.post('/api/alerts/sms/webhook/', {'MessageSid': 'SM123', 'MessageStatus': 'delivered'})
        self.assertEqual(resp.status_code, 403)

    def test_valid_signature_is_accepted(self):
        params = {'MessageSid': 'SM123', 'MessageStatus': 'delivered'}
        url = 'http://testserver/api/alerts/sms/webhook/'
        signature = self._sign(url, params, 'test-auth-token')
        resp = self.client.post('/api/alerts/sms/webhook/', params, HTTP_X_TWILIO_SIGNATURE=signature)
        self.assertEqual(resp.status_code, 200)

    def test_forged_signature_is_rejected(self):
        params = {'MessageSid': 'SM123', 'MessageStatus': 'delivered'}
        resp = self.client.post('/api/alerts/sms/webhook/', params, HTTP_X_TWILIO_SIGNATURE='forged')
        self.assertEqual(resp.status_code, 403)
