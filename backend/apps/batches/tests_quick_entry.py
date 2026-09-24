"""The daily quick entry (mortality / eggs / weight) — the one write a worker makes every day from a
phone. Boundaries of the mortality ceiling, the upsert semantics, and every input the API must
refuse with a French 400 rather than a 500 or a silently stored nonsense value.
"""
import datetime as dt
from unittest.mock import patch

from rest_framework.test import APITestCase

from apps.batches.models import BatchStatus, DailyLog, PoultryBatch, ProductionType
from apps.batches.services import record_quick_entry
from apps.core.models import Farm, User, UserRole, create_role_profile
from apps.houses.models import PoultryHouse

TODAY = dt.date(2026, 9, 24)
START = dt.date(2026, 9, 1)


def frozen_today():
    return patch('django.utils.timezone.localdate', return_value=TODAY)


class QuickEntryBase(APITestCase):
    def setUp(self):
        self.farm = Farm.objects.create(name='Ferme Saisie')
        house = PoultryHouse.objects.create(house_code=f'H-QE-{self.farm.id}', farm=self.farm, name='B1', max_capacity=500)
        self.batch = PoultryBatch.objects.create(
            batch_code=f'B-QE-{self.farm.id}', house=house, production_type=ProductionType.BROILER,
            initial_count=100, start_date=START, status=BatchStatus.ACTIVE,
        )
        worker = User.objects.create_user(email='ouvrier@qe.local', password='x', name='Ouvrier', role=UserRole.WORKER, farm=self.farm)
        create_role_profile(worker)
        self.client.force_authenticate(user=worker)
        self.url = f'/api/batches/{self.batch.batch_code}/daily-logs/quick-entry/'

    def put(self, **body):
        body.setdefault('date', TODAY.isoformat())
        with frozen_today():
            return self.client.put(self.url, body, format='json')


class RecordQuickEntryTests(QuickEntryBase):
    """The service: the mortality ceiling and "an omitted field keeps its value"."""

    def test_mortality_equal_to_the_whole_flock_is_accepted(self):
        _, pct, _, error = record_quick_entry(self.batch, TODAY, mortality=100)
        self.assertIsNone(error)
        self.assertEqual(pct, 100.0)

    def test_mortality_one_above_the_flock_is_refused(self):
        log, _, _, error = record_quick_entry(self.batch, TODAY, mortality=101)
        self.assertIsNone(log)
        self.assertIn("effectif actuel", error)
        self.assertFalse(DailyLog.objects.exists())

    def test_correcting_a_day_adds_its_previous_mortality_back_to_the_ceiling(self):
        record_quick_entry(self.batch, TODAY, mortality=40)
        # 60 birds left, but correcting today's 40 may go up to 100.
        _, _, _, error = record_quick_entry(self.batch, TODAY, mortality=100)
        self.assertIsNone(error)
        self.assertEqual(DailyLog.objects.get().mortality, 100)

    def test_omitted_fields_keep_their_value(self):
        record_quick_entry(self.batch, TODAY, mortality=3, eggs_collected=50, avg_sample_weight=1.2)
        record_quick_entry(self.batch, TODAY, eggs_collected=60)
        log = DailyLog.objects.get()
        self.assertEqual((log.mortality, log.eggs_collected, log.avg_sample_weight), (3, 60, 1.2))

    def test_zero_is_a_value_not_an_omission(self):
        record_quick_entry(self.batch, TODAY, mortality=3)
        record_quick_entry(self.batch, TODAY, mortality=0)
        self.assertEqual(DailyLog.objects.get().mortality, 0)


class QuickEntryValidationTests(QuickEntryBase):
    """Every refused input answers 400 with a French `detail`, and writes nothing."""

    def assertRefused(self, resp, fragment):
        self.assertEqual(resp.status_code, 400, resp.content)
        self.assertIn(fragment, resp.data['detail'])
        self.assertFalse(DailyLog.objects.exists())

    def test_valid_entry_is_saved(self):
        resp = self.put(mortality=2, eggsCollected=0, avgSampleWeight=0.8)
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(DailyLog.objects.get().mortality, 2)

    def test_date_is_required(self):
        self.assertRefused(self.put(date=''), 'date')

    def test_an_impossible_date_is_refused(self):
        self.assertRefused(self.put(date='2026-13-45', mortality=1), 'date')

    def test_today_is_accepted_but_tomorrow_is_refused(self):
        self.assertRefused(self.put(date=(TODAY + dt.timedelta(days=1)).isoformat(), mortality=1), 'futur')
        self.assertEqual(self.put(date=TODAY.isoformat(), mortality=1).status_code, 200)

    def test_the_start_date_is_accepted_but_the_day_before_is_refused(self):
        self.assertRefused(self.put(date=(START - dt.timedelta(days=1)).isoformat(), mortality=1), 'avant le début')
        self.assertEqual(self.put(date=START.isoformat(), mortality=1).status_code, 200)

    def test_a_closed_batch_is_refused(self):
        PoultryBatch.objects.filter(pk=self.batch.pk).update(status=BatchStatus.CLOSED)
        self.assertRefused(self.put(mortality=1), 'clôturée')

    def test_mortality_must_be_a_whole_number(self):
        self.assertRefused(self.put(mortality='abc'), 'mortalité')
        self.assertRefused(self.put(mortality=1.5), 'mortalité')

    def test_negative_mortality_is_refused(self):
        self.assertRefused(self.put(mortality=-1), 'mortalité')

    def test_eggs_must_be_a_whole_number_at_least_zero(self):
        self.assertRefused(self.put(eggsCollected=-1), 'œufs')
        self.assertRefused(self.put(eggsCollected='douze'), 'œufs')

    def test_weight_must_be_above_zero(self):
        self.assertRefused(self.put(avgSampleWeight=0), 'poids')
        self.assertRefused(self.put(avgSampleWeight=-0.5), 'poids')
        self.assertRefused(self.put(avgSampleWeight='lourd'), 'poids')
        self.assertEqual(self.put(avgSampleWeight=0.01).status_code, 200)
