from datetime import time

from django.test import TestCase

from apps.alerts.templates import build_task_reminders, render_task_reminder
from apps.batches.models import PoultryBatch, ProductionType
from apps.core.models import Civility, Farm, User, UserRole, create_role_profile
from apps.houses.models import PoultryHouse
from apps.protocols.models import ProtocolCategory, ProtocolTemplate, ProtocolTimeSlot


class TaskReminderTemplateTests(TestCase):
    """Part B of the civility/task-reminder task — `apps.alerts.templates.build_task_reminders`.
    Covers the three scenarios from the task's own Verification section."""

    def setUp(self):
        self.farm = Farm.objects.create(name='Ferme Ndoye')
        self.house = PoultryHouse.objects.create(house_code='H-R-1', farm=self.farm, name='Salle 1', max_capacity=1000)
        self.farmer = User.objects.create_user(
            email='farmer@winchicken.test', password='x', name='Fatou Diop',
            civility=Civility.MME, role=UserRole.FARMER, farm=self.farm,
        )
        create_role_profile(self.farmer)
        self.batch = PoultryBatch.objects.create(
            batch_code='BATCH-R-1', house=self.house, farmer=self.farmer,
            production_type=ProductionType.BROILER, initial_count=500, start_date='2026-01-01',
        )
        self.category = ProtocolCategory.objects.create(house=self.house, label='Alimentation', icon='Soup')
        self.worker = User.objects.create_user(
            email='worker@winchicken.test', password='x', name='Jean Dupont',
            civility=Civility.M, role=UserRole.WORKER, farm=self.farm,
        )
        create_role_profile(self.worker)

    def test_two_time_slots_produce_two_correctly_timed_reminders(self):
        line = ProtocolTemplate.objects.create(
            house=self.house, category=self.category, assigned_to=self.worker,
            from_value=1, to_value=1, what='le nourrissage',
        )
        ProtocolTimeSlot.objects.create(protocol_line=line, start_time=time(7, 0), end_time=time(9, 0))
        ProtocolTimeSlot.objects.create(protocol_line=line, start_time=time(18, 0), end_time=time(20, 0))

        reminders = build_task_reminders(line, self.batch)

        self.assertEqual(len(reminders), 2)
        (recipient_1, message_1), (recipient_2, message_2) = reminders
        self.assertEqual(recipient_1, self.worker)
        self.assertEqual(recipient_2, self.worker)
        self.assertEqual(message_1, "Bonjour Monsieur Jean, merci d'effectuer le nourrissage à Salle 1 à 07h00.")
        self.assertEqual(message_2, "Bonjour Monsieur Jean, merci d'effectuer le nourrissage à Salle 1 à 18h00.")

    def test_no_time_slot_renders_aujourdhui_not_a_dangling_clause(self):
        line = ProtocolTemplate.objects.create(
            house=self.house, category=self.category, assigned_to=self.worker,
            from_value=1, to_value=5, what='le nettoyage',
        )

        reminders = build_task_reminders(line, self.batch)

        self.assertEqual(len(reminders), 1)
        recipient, message = reminders[0]
        self.assertEqual(recipient, self.worker)
        self.assertEqual(message, "Bonjour Monsieur Jean, merci d'effectuer le nettoyage à Salle 1 aujourd'hui.")

    def test_unassigned_task_falls_back_to_batch_farmer(self):
        line = ProtocolTemplate.objects.create(
            house=self.house, category=self.category, assigned_to=None,
            from_value=1, to_value=1, what='la vaccination Newcastle',
        )

        reminders = build_task_reminders(line, self.batch)

        self.assertEqual(len(reminders), 1)
        recipient, message = reminders[0]
        self.assertEqual(recipient, self.farmer)
        self.assertEqual(message, "Bonjour Madame Fatou, merci d'effectuer la vaccination Newcastle à Salle 1 aujourd'hui.")

    def test_no_assignee_and_no_farmer_sends_nothing(self):
        self.batch.farmer = None
        self.batch.save()
        line = ProtocolTemplate.objects.create(
            house=self.house, category=self.category, assigned_to=None,
            from_value=1, to_value=1, what='le nourrissage',
        )

        self.assertEqual(build_task_reminders(line, self.batch), [])

    def test_render_task_reminder_uses_first_token_of_full_name(self):
        message = render_task_reminder(self.farmer, 'le nourrissage', 'Salle 1', start_time=time(7, 0))
        self.assertEqual(message, "Bonjour Madame Fatou, merci d'effectuer le nourrissage à Salle 1 à 07h00.")


class FireScheduledAlertsTests(TestCase):
    """The per-minute time-based trigger — apps.alerts.services.fire_scheduled_alerts."""

    def setUp(self):
        from datetime import timedelta
        from zoneinfo import ZoneInfo

        from django.conf import settings
        from django.utils import timezone

        self.tz = ZoneInfo(settings.FARM_TIME_ZONE)
        self.now = timezone.now().astimezone(self.tz).replace(hour=8, minute=0, second=0, microsecond=0)
        self.today = self.now.date()
        self.start = self.today - timedelta(days=1)  # day_of_cycle == 1 at self.now

        self.farm = Farm.objects.create(name='Ferme Alerte')
        self.house = PoultryHouse.objects.create(house_code='H-A-1', farm=self.farm, name='Salle 1', max_capacity=1000)
        self.farmer = User.objects.create_user(
            email='farmer@alerte.test', password='x', name='Awa Sow', civility=Civility.MME,
            role=UserRole.FARMER, farm=self.farm, phone='+237600000001',
        )
        create_role_profile(self.farmer)
        self.batch = PoultryBatch.objects.create(
            batch_code='BATCH-A-1', house=self.house, farmer=self.farmer,
            production_type=ProductionType.BROILER, initial_count=500, start_date=self.start,
        )
        self.category = ProtocolCategory.objects.create(house=self.house, label='Alimentation', icon='Soup')
        self.line = ProtocolTemplate.objects.create(
            house=self.house, category=self.category, assigned_to=None,
            from_value=1, from_unit='DAY', to_value=10, to_unit='DAY', what='le nourrissage',
        )

    def _make_rule(self, **overrides):
        from apps.alerts.models import AlertRule, AlertRuleType, ScheduleFrequency, TriggerMode

        defaults = dict(
            farm=self.farm, rule_type=AlertRuleType.PROTOCOL_TASK, trigger_mode=TriggerMode.SCHEDULED,
            frequency=ScheduleFrequency.ONE_TIME, trigger_time=self.now.time(), active=True,
            batch=self.batch, protocol_line=self.line, scheduled_date=self.today,
        )
        defaults.update(overrides)
        return AlertRule.objects.create(**defaults)

    def _fire(self, at=None):
        from apps.alerts.services import fire_scheduled_alerts
        return fire_scheduled_alerts(now=at or self.now)

    def test_fires_alert_and_sms_for_matching_rule(self):
        from apps.alerts.models import Alert, SmsMessage

        rule = self._make_rule()
        created = self._fire()

        self.assertEqual(len(created), 1)
        alert = created[0]
        self.assertEqual(alert.rule_id, rule.id)
        self.assertEqual(alert.batch_id, self.batch.pk)
        self.assertEqual(alert.message, "Bonjour Madame Awa, merci d'effectuer le nourrissage à Salle 1 aujourd'hui.")
        sms = SmsMessage.objects.get(alert=alert)
        self.assertEqual(sms.recipient, '+237600000001')
        self.assertEqual(Alert.objects.filter(rule=rule).count(), 1)

    def test_is_idempotent_within_the_window(self):
        self._make_rule()
        self.assertEqual(len(self._fire()), 1)
        self.assertEqual(len(self._fire(at=self.now.replace(minute=2))), 0)

    def test_one_time_rule_deactivates_after_firing(self):
        rule = self._make_rule()
        self._fire()
        rule.refresh_from_db()
        self.assertFalse(rule.active)

    def test_does_not_fire_for_closed_batch(self):
        from apps.batches.models import BatchStatus

        self.batch.status = BatchStatus.CLOSED
        self.batch.save(update_fields=['status'])
        self._make_rule()
        self.assertEqual(self._fire(), [])

    def test_does_not_fire_outside_protocol_line_day_range(self):
        from datetime import timedelta

        self.batch.start_date = self.today  # day_of_cycle 0, line starts at day 1
        self.batch.save(update_fields=['start_date'])
        self._make_rule(scheduled_date=self.today + timedelta(days=1))
        self.assertEqual(self._fire(), [])

    def test_tolerance_window_catches_recent_miss_not_old_one(self):
        self._make_rule(trigger_time=self.now.replace(minute=0).time())
        self.assertEqual(len(self._fire(at=self.now.replace(minute=2))), 1)  # 2 min late -> fires

        from apps.alerts.models import Alert
        Alert.objects.all().delete()
        self.assertEqual(self._fire(at=self.now.replace(minute=5)), [])  # 5 min late -> outside 3-min window

    def test_comparison_is_farm_local_not_utc(self):
        from django.utils import timezone

        from apps.alerts.models import AlertRule

        utc_now = timezone.now()
        farm_now = utc_now.astimezone(self.tz)
        self.assertNotEqual(utc_now.hour, farm_now.hour)  # Africa/Douala is never UTC

        self._make_rule(trigger_time=utc_now.time().replace(second=0, microsecond=0))
        self.assertEqual(self._fire(at=utc_now), [])  # matches UTC minute -> must NOT fire

        AlertRule.objects.all().delete()
        self._make_rule(trigger_time=farm_now.time().replace(second=0, microsecond=0))
        self.assertEqual(len(self._fire(at=utc_now)), 1)  # matches farm-local minute -> fires

    def test_weighing_reminder_fires_and_stays_active(self):
        from apps.alerts.models import AlertRule, AlertRuleType, ScheduleFrequency

        self.batch.start_date = self.today
        self.batch.weighing_frequency = 'DAY'
        self.batch.save(update_fields=['start_date', 'weighing_frequency'])
        rule = AlertRule.objects.create(
            farm=self.farm, rule_type=AlertRuleType.WEIGHING_REMINDER, trigger_mode='SCHEDULED',
            frequency=ScheduleFrequency.DAILY, trigger_time=self.now.time(), active=True, batch=self.batch,
        )
        created = self._fire()
        self.assertEqual(len(created), 1)
        self.assertIn('la pesée', created[0].message)
        rule.refresh_from_db()
        self.assertTrue(rule.active)

    def test_inactive_rule_never_fires(self):
        """A rule whose trigger_time matches exactly is still skipped when active=False."""
        self._make_rule(active=False)
        self.assertEqual(self._fire(), [])

    def test_one_time_rule_does_not_refire_after_its_first_firing(self):
        """After a ONE_TIME rule fires (and is deactivated), a later run well outside the
        10-minute idempotency window still does not re-fire it."""
        from datetime import timedelta

        from apps.alerts.models import Alert

        rule = self._make_rule()
        self.assertEqual(len(self._fire()), 1)
        rule.refresh_from_db()
        self.assertFalse(rule.active)

        Alert.objects.all().delete()  # drop the idempotency signal entirely
        later = self.now + timedelta(minutes=1)  # still inside the trigger-time window
        self.assertEqual(self._fire(at=later), [])  # active=False alone keeps it out

    def test_console_provider_sends_with_no_network_call(self):
        """SMS_PROVIDER=console: get_sms_provider() is the local console provider, and running
        the queued send_sms_task end-to-end marks the SmsMessage SENT without any real gateway
        call (no mock, no patched network)."""
        from django.test import override_settings

        from apps.alerts.models import SmsMessage, SmsStatus
        from apps.alerts.providers import get_sms_provider
        from apps.alerts.providers.console import ConsoleSmsProvider
        from apps.alerts.tasks import send_sms_task

        with override_settings(SMS_PROVIDER='console'):
            self.assertIsInstance(get_sms_provider(), ConsoleSmsProvider)
            self._make_rule()
            self.assertEqual(len(self._fire()), 1)
            sms = SmsMessage.objects.get()
            self.assertEqual(sms.provider_status, SmsStatus.PENDING)  # queued, not yet sent
            send_sms_task(sms.id)  # run the real task body against the real console provider

        sms.refresh_from_db()
        self.assertEqual(sms.provider_status, SmsStatus.SENT)
        self.assertEqual(sms.provider, 'console-local')  # ConsoleSmsProvider's marker, no gateway hit
        self.assertEqual(sms.recipient, '+237600000001')
