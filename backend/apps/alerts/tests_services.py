"""Boundaries of apps.alerts.services and the SMS task: the two automatic thresholds (water/feed
ratio, low stock), who receives an SMS, the scheduled-reminder window (including the wrap past
midnight), the per-rule day filters, and the SMS retry ladder.
"""
import datetime as dt
from decimal import Decimal
from unittest.mock import patch
from zoneinfo import ZoneInfo

from celery.exceptions import Retry
from django.conf import settings
from django.test import TestCase

from apps.alerts import tasks
from apps.alerts.models import (
    Alert, AlertRule, AlertRuleType, NotificationChannel, NotificationPreference, ScheduleFrequency,
    SmsMessage, SmsStatus, TriggerMode,
)
from apps.alerts.services import check_consumption_deviation, check_low_stock, fire_scheduled_alerts, trigger_alert
from apps.batches.models import BatchStatus, DailyLog, PoultryBatch, ProductionType
from apps.core.models import Farm, User, UserRole, create_role_profile
from apps.houses.models import PoultryHouse
from apps.stock.models import MovementType, StockCategory, StockItem, StockMovement

FARM_TZ = ZoneInfo(settings.FARM_TIME_ZONE)
START = dt.date(2026, 9, 1)


def at_farm(y, mo, d, h, mi):
    return dt.datetime(y, mo, d, h, mi, tzinfo=FARM_TZ)


class AlertsBase(TestCase):
    def setUp(self):
        self.farm = Farm.objects.create(name='Ferme Alertes')
        self.house = PoultryHouse.objects.create(house_code=f'H-AL-{self.farm.id}', farm=self.farm, name='Nord', max_capacity=500)
        self.batch = PoultryBatch.objects.create(
            batch_code=f'B-AL-{self.farm.id}', house=self.house, production_type=ProductionType.BROILER,
            initial_count=100, start_date=START, status=BatchStatus.ACTIVE,
        )

    def user(self, email, phone='+237600000001'):
        u = User.objects.create_user(email=email, password='x', name='Paul', role=UserRole.FARM_MANAGER, farm=self.farm, phone=phone)
        create_role_profile(u)
        return u


class ConsumptionDeviationTests(AlertsBase):
    def log(self, feed, water):
        # Saving a DailyLog runs the check through a signal; call it directly as well is not
        # needed — count the Alert rows it leaves.
        return DailyLog.objects.create(batch=self.batch, log_date=START, feed_consumed_kg=feed, water_consumed_l=water)

    def deviations(self):
        return Alert.objects.filter(rule__rule_type=AlertRuleType.CONSUMPTION_DEVIATION)

    def test_no_feed_logged_means_no_ratio_and_no_alert(self):
        self.log(0, 50)
        self.assertFalse(self.deviations().exists())

    def test_ratio_exactly_at_either_bound_is_normal(self):
        self.log(100, 160)
        DailyLog.objects.all().delete()
        self.log(100, 220)
        self.assertFalse(self.deviations().exists())

    def test_ratio_just_outside_either_bound_alerts(self):
        self.log(100, 159)
        self.assertEqual(self.deviations().count(), 1)
        DailyLog.objects.all().delete()
        DailyLog.objects.create(batch=self.batch, log_date=START + dt.timedelta(days=1), feed_consumed_kg=100, water_consumed_l=221)
        self.assertEqual(self.deviations().count(), 2)

    def test_message_uses_french_decimals(self):
        self.log(100, 159)
        self.assertIn('Ratio eau/aliment 1,59 hors norme 1,6-2,2', self.deviations().get().message)


class LowStockTests(AlertsBase):
    def setUp(self):
        super().setUp()
        feed = StockCategory.objects.get(farm=self.farm, kind='FEED')
        self.item = StockItem.objects.create(
            item_code=f'FEE-AL-{self.farm.id}', farm=self.farm, category=feed, name='Aliment démarrage',
            unit='kg', alert_threshold=10, unit_price=Decimal('1'),
        )

    def move(self, qty, kind=MovementType.IN):
        StockMovement.objects.create(item=self.item, movement_type=kind, quantity=qty, movement_date=START)

    def lows(self):
        return Alert.objects.filter(rule__rule_type=AlertRuleType.LOW_STOCK)

    def test_exactly_at_the_threshold_is_low(self):
        # Same rule as the badge, the stock screen and the overview (apps.stock.calculations.is_low).
        self.move(10)
        self.assertTrue(self.lows().exists())

    def test_above_the_threshold_is_not_low(self):
        self.move(10.5)
        self.assertFalse(self.lows().exists())

    def test_just_below_the_threshold_is_a_danger_alert(self):
        self.move(9.5)
        alert = self.lows().get()
        self.assertEqual(alert.severity, 'danger')
        self.assertIn('Aliment démarrage sous le seuil (9,5 kg pour un seuil de 10 kg)', alert.message)

    def test_counts_out_movements(self):
        self.move(20)
        self.move(11, MovementType.OUT)
        self.assertTrue(self.lows().exists())

    def test_reads_the_on_hand_quantity_once(self):
        self.move(20)
        StockMovement.objects.create(item=self.item, movement_type=MovementType.OUT, quantity=15, movement_date=START)
        # One aggregate query (IN minus OUT) for the quantity; it used to be computed three times,
        # then twice (one query per movement type).
        with self.assertNumQueries(1):
            with patch('apps.alerts.services.trigger_alert'):
                check_low_stock(self.item)


class SmsRecipientsTests(AlertsBase):
    def pref(self, user, channel=NotificationChannel.SMS, active=True, rule_type=AlertRuleType.LOW_STOCK):
        return NotificationPreference.objects.create(user=user, rule_type=rule_type, preferred_channel=channel, active=active)

    def fire(self, salt='s1'):
        """Runs trigger_alert and its on-commit callbacks; returns the SMS ids handed to the
        worker. (Other callbacks — the desktop push every Alert queues — run too, harmlessly.)"""
        with patch('apps.alerts.services.send_sms_task') as task, patch('apps.alerts.tasks.send_web_push_task'):
            with self.captureOnCommitCallbacks(execute=True):
                trigger_alert(self.farm, AlertRuleType.LOW_STOCK, 'test', severity='danger', salt=salt)
        return [c.args[0] for c in task.delay.call_args_list]

    def test_only_active_sms_preferences_with_a_phone_receive(self):
        self.pref(self.user('a@al.local', phone='+237600000001'))
        self.pref(self.user('b@al.local', phone=''))
        self.pref(self.user('c@al.local', phone='+237600000003'), active=False)
        self.pref(self.user('d@al.local', phone='+237600000004'), channel=NotificationChannel.EMAIL)
        self.pref(self.user('e@al.local', phone='+237600000005'), rule_type=AlertRuleType.CONSUMPTION_DEVIATION)
        queued = self.fire()
        self.assertEqual(list(SmsMessage.objects.values_list('recipient', flat=True)), ['+237600000001'])
        self.assertEqual(len(queued), 1)

    def test_same_occurrence_twice_queues_one_sms_and_does_not_crash(self):
        # A second trigger of the same occurrence (same salt): e.g. correcting a day's log while
        # its water/feed ratio is still out of range. It used to raise IntegrityError — the SMS
        # lookup was scoped to the new Alert while the key is unique across all of them — and
        # the save that triggered it failed with a 500.
        self.pref(self.user('a@al.local'))
        self.assertEqual(len(self.fire('same')), 1)
        self.assertEqual(self.fire('same'), [])
        self.assertEqual(SmsMessage.objects.count(), 1)


class ScheduledWindowTests(AlertsBase):
    def rule(self, hh, mm, **kw):
        kw.setdefault('frequency', ScheduleFrequency.DAILY)
        kw.setdefault('rule_type', AlertRuleType.PROTOCOL_TASK)
        return AlertRule.objects.create(
            farm=self.farm, trigger_mode=TriggerMode.SCHEDULED,
            trigger_time=dt.time(hh, mm), batch=self.batch, **kw,
        )

    def fired(self, now):
        return {a.rule_id for a in fire_scheduled_alerts(now=now)}

    def test_fires_at_its_minute_and_up_to_three_minutes_late_not_four(self):
        r = self.rule(7, 0)
        self.assertEqual(self.fired(at_farm(2026, 9, 24, 6, 59)), set())
        self.assertEqual(self.fired(at_farm(2026, 9, 24, 7, 3)), {r.id})

    def test_four_minutes_late_is_missed(self):
        self.rule(7, 0)
        self.assertEqual(self.fired(at_farm(2026, 9, 24, 7, 4)), set())

    def test_the_window_wraps_past_midnight(self):
        r = self.rule(23, 59)
        self.assertEqual(self.fired(at_farm(2026, 9, 25, 0, 1)), {r.id})

    def test_a_later_run_inside_the_catch_up_window_does_not_fire_again(self):
        # 07:01 fires; 07:03 is still inside the 3-minute window for 07:00, so only the
        # "already fired in the last 10 minutes" guard stops a second SMS.
        r = self.rule(7, 0)
        with patch('django.utils.timezone.now', return_value=at_farm(2026, 9, 24, 7, 1)):
            self.assertEqual(self.fired(at_farm(2026, 9, 24, 7, 1)), {r.id})
        with patch('django.utils.timezone.now', return_value=at_farm(2026, 9, 24, 7, 3)):
            self.assertEqual(self.fired(at_farm(2026, 9, 24, 7, 3)), set())

    def test_active_days_filter(self):
        thursday = at_farm(2026, 9, 24, 7, 0)
        self.rule(7, 0, active_days='MON, WED')
        on_thursday = self.rule(7, 0, active_days='thu,fri')
        self.assertEqual(self.fired(thursday), {on_thursday.id})

    def test_closed_batch_and_not_yet_started_batch_do_not_fire(self):
        self.rule(7, 0)
        PoultryBatch.objects.filter(pk=self.batch.pk).update(status=BatchStatus.CLOSED)
        self.assertEqual(self.fired(at_farm(2026, 9, 24, 7, 0)), set())
        PoultryBatch.objects.filter(pk=self.batch.pk).update(status=BatchStatus.ACTIVE, start_date=dt.date(2026, 9, 25))
        self.assertEqual(self.fired(at_farm(2026, 9, 24, 7, 0)), set())

    def test_one_time_rule_fires_on_its_date_only_then_deactivates(self):
        r = self.rule(7, 0, frequency=ScheduleFrequency.ONE_TIME, scheduled_date=dt.date(2026, 9, 25))
        self.assertEqual(self.fired(at_farm(2026, 9, 24, 7, 0)), set())
        self.assertEqual(self.fired(at_farm(2026, 9, 25, 7, 0)), {r.id})
        r.refresh_from_db()
        self.assertFalse(r.active)

    def test_weekly_weighing_reminder_fires_every_seventh_day(self):
        PoultryBatch.objects.filter(pk=self.batch.pk).update(weighing_frequency="WEEK")
        r = self.rule(7, 0, rule_type=AlertRuleType.WEIGHING_REMINDER, frequency=ScheduleFrequency.WEEKLY)
        self.assertEqual(self.fired(at_farm(2026, 9, 15, 7, 0)), {r.id})   # day 14
        self.assertEqual(self.fired(at_farm(2026, 9, 16, 7, 0)), set())    # day 15


class SendSmsTaskTests(AlertsBase):
    def setUp(self):
        super().setUp()
        rule = AlertRule.objects.create(farm=self.farm, rule_type=AlertRuleType.LOW_STOCK, trigger_mode=TriggerMode.EVENT)
        alert = Alert.objects.create(rule=rule, message='Stock bas')
        self.sms = SmsMessage.objects.create(alert=alert, recipient='+237600000001', idempotency_key='k1')

    def provider(self, success):
        class Fake:
            calls = 0

            def send(self, to, body):
                Fake.calls += 1
                return {'success': success, 'provider_message_id': 'MSG1' if success else None}
        return Fake()

    def test_success_marks_sent_and_a_replay_does_not_resend(self):
        fake = self.provider(True)
        with patch.object(tasks, 'get_sms_provider', return_value=fake):
            tasks.send_sms_task(self.sms.id)
            tasks.send_sms_task(self.sms.id)
        self.sms.refresh_from_db()
        self.assertEqual(self.sms.provider_status, SmsStatus.SENT)
        self.assertEqual(type(fake).calls, 1)

    def test_a_failure_schedules_a_retry_with_backoff(self):
        with patch.object(tasks, 'get_sms_provider', return_value=self.provider(False)):
            with self.assertRaises(Retry):
                tasks.send_sms_task(self.sms.id)
        self.sms.refresh_from_db()
        self.assertEqual(self.sms.retry_count, 1)
        self.assertIsNotNone(self.sms.next_retry_at)
        self.assertEqual(self.sms.provider_status, SmsStatus.PENDING)

    def test_the_fifth_failure_gives_up(self):
        SmsMessage.objects.filter(pk=self.sms.pk).update(retry_count=tasks.MAX_RETRIES - 1)
        with patch.object(tasks, 'get_sms_provider', return_value=self.provider(False)):
            tasks.send_sms_task(self.sms.id)   # no Retry raised: it stops here
        self.sms.refresh_from_db()
        self.assertEqual(self.sms.provider_status, SmsStatus.FAILED)

    def test_a_deleted_message_is_ignored(self):
        self.assertIsNone(tasks.send_sms_task(999999))
