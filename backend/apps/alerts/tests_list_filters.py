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


class TaskRemindersAreNotOpenProblemsTests(APITestCase):
    """2026-09-25: every daily task reminder is stored as an Alert (and sent as a push + SMS), and
    nothing resolves it, so "open alerts" grew by every reminder ever sent — 46 on the test farm,
    next to a dashboard tile saying 6, and a health score stuck on "À surveiller"."""

    def setUp(self):
        self.farm = Farm.objects.create(name='Ferme Rappels')
        admin = User.objects.create_user(email='admin@rappels.local', password='x', name='A', role=UserRole.ADMIN, farm=self.farm)
        create_role_profile(admin)
        self.client.force_authenticate(user=admin)
        task = AlertRule.objects.create(farm=self.farm, rule_type=AlertRuleType.PROTOCOL_TASK, trigger_mode=TriggerMode.SCHEDULED)
        weighing = AlertRule.objects.create(farm=self.farm, rule_type=AlertRuleType.WEIGHING_REMINDER, trigger_mode=TriggerMode.SCHEDULED)
        for i in range(30):
            Alert.objects.create(rule=task, message=f'Tâche à effectuer {i}', severity='info')
        Alert.objects.create(rule=weighing, message='Pesée', severity='info')
        self.stock = AlertRule.objects.create(farm=self.farm, rule_type=AlertRuleType.LOW_STOCK, trigger_mode=TriggerMode.EVENT)

    def test_reminders_stay_listed_but_are_not_open_problems(self):
        self.assertEqual(self.client.get('/api/alerts/').data['count'], 31)
        self.assertEqual(self.client.get('/api/alerts/', {'open': '1'}).data['count'], 0)
        score = self.client.get('/api/batches/health-score/').data
        self.assertEqual(score['tier'], 'good', score)

    def test_a_real_problem_is_counted_the_same_by_the_list_and_the_health_score(self):
        Alert.objects.create(rule=self.stock, message='Stock bas : provende', severity='warning')
        Alert.objects.create(rule=self.stock, message='Stock bas : vaccin', severity='warning')
        self.assertEqual(self.client.get('/api/alerts/', {'open': '1'}).data['count'], 2)
        score = self.client.get('/api/batches/health-score/').data
        self.assertEqual(score['tier'], 'watch')
        self.assertIn('2 alertes ouvertes', score['reason'])


class EmptyMessageAlertTests(APITestCase):
    """Live QA 2026-09-25: a reminder stored with an empty message (before the unaddressed-reminder
    fix) showed as a card with only a date on the Alertes page."""

    def setUp(self):
        from datetime import date

        from apps.batches.models import PoultryBatch, ProductionType
        from apps.houses.models import PoultryHouse
        from apps.protocols.models import ProtocolCategory, ProtocolTemplate

        self.farm = Farm.objects.create(name='Ferme Messages')
        admin = User.objects.create_user(email='admin@messages.local', password='x', name='A', role=UserRole.ADMIN, farm=self.farm)
        create_role_profile(admin)
        self.client.force_authenticate(user=admin)
        house = PoultryHouse.objects.create(house_code='H-MSG-1', farm=self.farm, name='Salle 1', max_capacity=100)
        cat = ProtocolCategory.objects.create(house=house, label='Alimentation', icon='Soup')
        line = ProtocolTemplate.objects.create(house=house, category=cat, from_value=1, what='Aliment démarrage')
        batch = PoultryBatch.objects.create(batch_code='B-MSG-1', house=house, production_type=ProductionType.BROILER,
                                            initial_count=50, start_date=date(2026, 9, 1))
        self.task_rule = AlertRule.objects.create(farm=self.farm, rule_type=AlertRuleType.PROTOCOL_TASK,
                                                  trigger_mode=TriggerMode.SCHEDULED, batch=batch, protocol_line=line)
        self.stock_rule = AlertRule.objects.create(farm=self.farm, rule_type=AlertRuleType.LOW_STOCK, trigger_mode=TriggerMode.EVENT)

    def test_an_empty_reminder_reads_as_the_task_that_came_due(self):
        Alert.objects.create(rule=self.task_rule, message='')
        row = self.client.get('/api/alerts/').data['results'][0]
        self.assertEqual(row['message'], 'Tâche à effectuer : Aliment démarrage à Salle 1.')

    def test_an_empty_problem_alert_reads_as_its_type_in_french(self):
        Alert.objects.create(rule=self.stock_rule, message='')
        self.assertEqual(self.client.get('/api/alerts/').data['results'][0]['message'], 'Stock bas')

    def test_a_message_is_left_as_it_is(self):
        Alert.objects.create(rule=self.stock_rule, message='Provende sous le seuil')
        self.assertEqual(self.client.get('/api/alerts/').data['results'][0]['message'], 'Provende sous le seuil')

    def test_describing_empty_alerts_costs_no_query_per_row(self):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        Alert.objects.create(rule=self.task_rule, message='')
        with CaptureQueriesContext(connection) as one:
            self.client.get('/api/alerts/')
        for _ in range(5):
            Alert.objects.create(rule=self.task_rule, message='')
        with CaptureQueriesContext(connection) as six:
            self.client.get('/api/alerts/')
        self.assertEqual(len(six.captured_queries), len(one.captured_queries))
