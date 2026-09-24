"""Integration chain 6 — alert rule -> alert generated -> SMS / notification dispatch.

Scheduled reminders: a protocol line with a time slot, saved through the API, becomes a DAILY
AlertRule; the per-minute evaluator (`fire_scheduled_alerts`, what Beat runs) fires it at the
slot's start, creates the Alert and one SMS per recipient, and the SMS task hands each to the
provider. Event alerts go through the user's notification preference. Real database; the SMS
gateway is the console provider (config/settings.py forces it under tests), except where a
failing gateway is the point of the test.
"""
import datetime as dt
from unittest import mock
from zoneinfo import ZoneInfo

from django.utils import timezone
from rest_framework.test import APITestCase

from apps.alerts.models import (
    Alert, AlertRule, AlertRuleType, NotificationChannel, NotificationPreference, SmsMessage, SmsStatus, TriggerMode,
)
from apps.alerts.services import fire_scheduled_alerts, trigger_alert
from apps.alerts.tasks import MAX_RETRIES, send_sms_task
from apps.batches.models import BatchStatus, PoultryBatch, ProductionType
from apps.core.models import Farm, User, UserRole, create_role_profile
from apps.houses.models import PoultryHouse
from apps.protocols.models import ProtocolCategory

DOUALA = ZoneInfo('Africa/Douala')


class ScheduledReminderChainTests(APITestCase):
    def setUp(self):
        self.farm = Farm.objects.create(name='Ferme Rappels')
        self.people = {}
        for key, role, name, phone, civility in (
            ('admin', UserRole.ADMIN, 'Paul Admin', '', 'M'),
            ('awa', UserRole.WORKER, 'Awa Diallo', '+237600000011', 'MME'),
            ('ben', UserRole.WORKER, 'Ben Tchami', '+237600000012', 'M'),
            ('farmer', UserRole.FARMER, 'Joseph Mbarga', '+237600000013', 'M'),
            ('nophone', UserRole.WORKER, 'Sans Téléphone', '', 'M'),
        ):
            user = User.objects.create_user(email=f'{key}@rappels.local', password='x', name=name, role=role, farm=self.farm, phone=phone, civility=civility)
            create_role_profile(user)
            self.people[key] = user
        self.house = PoultryHouse.objects.create(house_code=f'H-{self.farm.id}-001', farm=self.farm, name='Poulailler A', max_capacity=500)
        self.today = timezone.localdate()
        self.batch = PoultryBatch.objects.create(
            batch_code=f'B-{self.farm.id}', house=self.house, production_type=ProductionType.BROILER, initial_count=500,
            start_date=self.today - dt.timedelta(days=2), status=BatchStatus.ACTIVE,
        )
        self.client.force_authenticate(user=self.people['admin'])
        feeding = ProtocolCategory.objects.get(house=self.house, label='Alimentation')
        response = self.client.put(f'/api/houses/{self.house.house_code}/protocol/', {'lines': [{
            'category': feeding.id, 'from_value': 1, 'from_unit': 'DAY', 'until_end': True, 'what': 'la distribution d’aliment',
            'details': '', 'time_slots': [{'start_time': '07:00', 'end_time': '08:00'}],
        }]}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.line_id = response.data[0]['id']

    def at(self, hhmm, day=None):
        h, m = map(int, hhmm.split(':'))
        return dt.datetime.combine(day or self.today, dt.time(h, m), tzinfo=DOUALA)

    def assign(self, *who):
        response = self.client.patch(
            f'/api/houses/{self.house.house_code}/tasks-now/{self.line_id}/assign/',
            {'assignees': [self.people[w].id for w in who]}, format='json',
        )
        self.assertEqual(response.status_code, 200, response.data)

    def fire(self, hhmm, day=None):
        # Django's clock is set to the simulated minute too, so Alert.triggered_at (auto_now_add)
        # and the SMS idempotency key agree with the evaluator's `now`, as they do in production.
        now = self.at(hhmm, day)
        with mock.patch('django.utils.timezone.now', return_value=now), \
                self.captureOnCommitCallbacks(execute=True):  # SMS tasks run on commit (eagerly under tests)
            return fire_scheduled_alerts(now=now)

    def test_saving_the_protocol_creates_a_daily_rule_at_the_slot(self):
        [rule] = AlertRule.objects.filter(batch=self.batch, rule_type=AlertRuleType.PROTOCOL_TASK)
        self.assertEqual((rule.trigger_mode, rule.frequency, str(rule.trigger_time)), (TriggerMode.SCHEDULED, 'DAILY', '07:00:00'))

    def test_the_slot_fires_one_alert_and_one_sent_sms_per_assignee(self):
        self.assign('awa', 'ben')
        [alert] = self.fire('07:01')
        self.assertEqual(alert.batch, self.batch)
        sms = {s.recipient: s for s in SmsMessage.objects.filter(alert=alert)}
        self.assertEqual(set(sms), {'+237600000011', '+237600000012'})
        self.assertTrue(all(s.provider_status == SmsStatus.SENT for s in sms.values()))
        self.assertIn('la distribution d’aliment', alert.message)
        self.assertIn('07h00', alert.message)

        # The bell and the unread badge see it.
        self.assertEqual(self.client.get('/api/alerts/unread-count/').data['count'], 1)

    def test_it_fires_once_per_day_and_only_in_its_window(self):
        self.assign('awa')
        self.assertEqual(len(self.fire('07:01')), 1)
        self.assertEqual(self.fire('07:02'), [])                      # same occurrence: not again
        self.assertEqual(self.fire('07:30'), [])                      # outside the 3-minute window
        self.assertEqual(self.fire('06:58'), [])                      # before it
        self.assertEqual(len(self.fire('07:00', self.today + dt.timedelta(days=1))), 1)  # tomorrow again
        self.assertEqual(SmsMessage.objects.count(), 2)

    def test_no_assignee_falls_back_to_the_batch_farmer(self):
        PoultryBatch.objects.filter(pk=self.batch.pk).update(farmer=self.people['farmer'])
        [alert] = self.fire('07:01')
        self.assertEqual(list(SmsMessage.objects.filter(alert=alert).values_list('recipient', flat=True)), ['+237600000013'])
        self.assertIn('Joseph', alert.message)

    def test_nobody_to_tell_still_records_a_readable_alert_and_sends_nothing(self):
        [alert] = self.fire('07:01')
        self.assertFalse(SmsMessage.objects.exists())
        self.assertIn('la distribution d’aliment', alert.message)  # was an empty row in the bell

    def test_an_assignee_without_a_phone_gets_no_sms_and_the_others_still_do(self):
        self.assign('awa', 'nophone')
        self.fire('07:01')
        self.assertEqual(list(SmsMessage.objects.values_list('recipient', flat=True)), ['+237600000011'])

    def test_a_closed_batch_is_not_reminded(self):
        self.assign('awa')
        PoultryBatch.objects.filter(pk=self.batch.pk).update(status=BatchStatus.CLOSED)
        self.assertEqual(self.fire('07:01'), [])

    def test_each_assignee_is_greeted_by_their_own_name(self):
        # The task used to send alert.message — Awa's greeting — to everyone on the reminder.
        self.assign('awa', 'ben')
        with self.assertLogs('winchicken.sms', level='INFO') as logs:
            self.fire('07:01')
        sent = {phone: next(line for line in logs.output if phone in line) for phone in ('+237600000011', '+237600000012')}
        self.assertIn('Madame Awa', sent['+237600000011'])
        self.assertIn('Monsieur Ben', sent['+237600000012'])
        self.assertNotIn('Awa', sent['+237600000012'])

    def test_an_sms_written_before_the_body_column_still_sends_the_alert_text(self):
        self.assign('awa')
        [alert] = self.fire('07:01')
        legacy = SmsMessage.objects.create(alert=alert, recipient='+237600000099', idempotency_key='legacy-row')
        with self.assertLogs('winchicken.sms', level='INFO') as logs:
            send_sms_task(legacy.id)
        self.assertIn(alert.message, logs.output[0])


class EventAlertDispatchTests(APITestCase):
    def setUp(self):
        self.farm = Farm.objects.create(name='Ferme Événements')
        self.sms_user = User.objects.create_user(email='sms@evt.local', password='x', name='SMS', role=UserRole.ADMIN, farm=self.farm, phone='+237600000021')
        self.push_user = User.objects.create_user(email='push@evt.local', password='x', name='Push', role=UserRole.FARM_MANAGER, farm=self.farm, phone='+237600000022')
        for user, channel in ((self.sms_user, NotificationChannel.SMS), (self.push_user, NotificationChannel.PUSH)):
            create_role_profile(user)
            NotificationPreference.objects.create(user=user, rule_type=AlertRuleType.LOW_STOCK, preferred_channel=channel)

    def raise_alert(self, salt='1'):
        with self.captureOnCommitCallbacks(execute=True):
            return trigger_alert(self.farm, AlertRuleType.LOW_STOCK, 'Provende sous le seuil', severity='danger', salt=salt)

    def test_only_the_users_who_chose_sms_get_one(self):
        alert = self.raise_alert()
        self.assertEqual(list(SmsMessage.objects.filter(alert=alert).values_list('recipient', 'provider_status')), [('+237600000021', SmsStatus.SENT)])

    def test_the_same_occurrence_twice_is_one_sms(self):
        self.raise_alert(salt='70')
        self.raise_alert(salt='70')
        self.assertEqual(Alert.objects.count(), 2)
        self.assertEqual(SmsMessage.objects.count(), 1)

    def test_a_failing_gateway_retries_then_gives_up_as_failed(self):
        failing = mock.Mock()
        failing.send.return_value = {'success': False, 'provider_message_id': None, 'error': 'réseau indisponible'}
        with mock.patch('apps.alerts.tasks.get_sms_provider', return_value=failing):
            alert = self.raise_alert()
        sms = SmsMessage.objects.get(alert=alert)
        self.assertEqual((sms.provider_status, sms.retry_count), (SmsStatus.FAILED, MAX_RETRIES))
        self.assertEqual(failing.send.call_count, MAX_RETRIES)

    def test_a_sent_sms_is_never_sent_again(self):
        alert = self.raise_alert()
        sms = SmsMessage.objects.get(alert=alert)
        with mock.patch('apps.alerts.tasks.get_sms_provider') as provider:
            send_sms_task(sms.id)
        provider.assert_not_called()
