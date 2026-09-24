"""One definition of "the day of the cycle": 0 on the start date, counted in farm-local days.

The dashboard used to recompute it in the browser, 1-based and from UTC, and read one day ahead
of the house page ("jour 22" vs "Jour 21"). These tests pin the helper at its boundaries and the
invariant that broke: the batch API and the house's task view report the same day.
"""
import datetime as dt
from unittest.mock import patch

from rest_framework.test import APITestCase

from apps.batches.models import BatchStatus, PoultryBatch, ProductionType
from apps.batches.services import day_of_cycle
from apps.core.models import Farm, User, UserRole, create_role_profile
from apps.houses.models import PoultryHouse

TODAY = dt.date(2026, 9, 24)


class DayOfCycleTests(APITestCase):
    def setUp(self):
        self.farm = Farm.objects.create(name='Ferme Jour')
        self.house = PoultryHouse.objects.create(house_code=f'H-DOC-{self.farm.id}', farm=self.farm, name='B1', max_capacity=600)
        admin = User.objects.create_user(email='admin@doc.local', password='x', name='A', role=UserRole.ADMIN, farm=self.farm)
        create_role_profile(admin)
        self.client.force_authenticate(user=admin)

    def batch(self, start):
        return PoultryBatch.objects.create(
            batch_code=f'B-DOC-{self.farm.id}', house=self.house, production_type=ProductionType.BROILER,
            initial_count=600, start_date=start, status=BatchStatus.ACTIVE,
        )

    def test_the_start_date_is_day_zero_and_the_next_day_is_one(self):
        b = self.batch(TODAY)
        self.assertEqual(day_of_cycle(b, TODAY), 0)
        self.assertEqual(day_of_cycle(b, TODAY + dt.timedelta(days=1)), 1)

    def test_a_batch_starting_later_has_a_negative_day(self):
        self.assertEqual(day_of_cycle(self.batch(TODAY + dt.timedelta(days=3)), TODAY), -3)

    def test_defaults_to_the_farm_local_today(self):
        b = self.batch(TODAY - dt.timedelta(days=21))
        with patch('django.utils.timezone.localdate', return_value=TODAY):
            self.assertEqual(day_of_cycle(b), 21)

    def test_farm_midnight_not_utc_midnight_turns_the_day(self):
        # 00:30 in Douala is still 23:30 UTC the previous day: the farm is already on day 22.
        b = self.batch(dt.date(2026, 9, 3))
        farm_now = dt.datetime(2026, 9, 24, 23, 30, tzinfo=dt.timezone.utc)  # = 25/09 00:30 Douala
        with patch('django.utils.timezone.now', return_value=farm_now):
            self.assertEqual(day_of_cycle(b), 22)

    def test_the_batch_api_and_the_house_task_view_agree(self):
        b = self.batch(TODAY - dt.timedelta(days=21))
        with patch('django.utils.timezone.localdate', return_value=TODAY):
            listed = self.client.get('/api/batches/').data
            tasks = self.client.get(f'/api/houses/{self.house.house_code}/tasks-now/').data
        rows = listed['results'] if isinstance(listed, dict) else listed
        row = next(r for r in rows if r['batch_code'] == b.batch_code)
        self.assertEqual(row['day_of_cycle'], 21)
        self.assertEqual(tasks['dayOfCycle'], row['day_of_cycle'])
