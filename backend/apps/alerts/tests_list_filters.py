"""GET /api/alerts/?open=1 — the dashboard's "open alerts" card.

It filtered RESOLVED out of page 1 of every alert (20 rows, newest first), so an unresolved alert
vanished from the dashboard as soon as 20 newer alerts existed, resolved or not.
"""
import datetime as dt

from django.utils import timezone
from rest_framework.test import APITestCase

from apps.alerts.models import Alert, AlertRule, AlertRuleType, AlertStatus, TriggerMode
from apps.core.models import Farm, User, UserRole, create_role_profile


class OpenAlertFilterTests(APITestCase):
    def setUp(self):
        self.farm = Farm.objects.create(name='Ferme Alertes')
        admin = User.objects.create_user(email='admin@alertes.local', password='x', name='A', role=UserRole.ADMIN, farm=self.farm)
        create_role_profile(admin)
        self.client.force_authenticate(user=admin)
        rule = AlertRule.objects.create(farm=self.farm, rule_type=AlertRuleType.LOW_STOCK, trigger_mode=TriggerMode.EVENT)
        self.old_open = Alert.objects.create(rule=rule, status=AlertStatus.NEW, message='Stock bas : provende')
        Alert.objects.filter(pk=self.old_open.pk).update(triggered_at=timezone.now() - dt.timedelta(days=10))
        for i in range(25):
            Alert.objects.create(rule=rule, status=AlertStatus.RESOLVED, message=f'Réglée {i}')

    def test_the_old_open_alert_is_off_the_unfiltered_first_page(self):
        ids = [r['id'] for r in self.client.get('/api/alerts/').data['results']]
        self.assertNotIn(self.old_open.id, ids)

    def test_open_lists_only_unresolved_alerts(self):
        rows = self.client.get('/api/alerts/', {'open': '1'}).data['results']
        self.assertEqual([r['id'] for r in rows], [self.old_open.id])
