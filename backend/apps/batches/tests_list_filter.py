"""GET /api/batches/?status= — the farm-wide "which batch is in each house" question.

The sidebar and the dashboard used to take the first page of /api/batches/ (20 rows, newest
start date first) and pick the ACTIVE ones out of it. A layer flock runs ~18 months while broiler
houses turn over every 6-7 weeks, so after a year the active layer batch sits past row 20 and its
house shows as empty. Asking the API for ACTIVE batches only keeps the answer on one page: a
house holds at most one active batch.
"""
import datetime as dt

from rest_framework.test import APITestCase

from apps.batches.models import BatchStatus, DailyLog, PoultryBatch, ProductionType
from apps.core.models import Farm, User, UserRole, create_role_profile
from apps.houses.models import PoultryHouse


class BatchListStatusFilterTests(APITestCase):
    def setUp(self):
        self.farm = Farm.objects.create(name='Ferme Filtre')
        self.layers = PoultryHouse.objects.create(house_code=f'H-LAY-{self.farm.id}', farm=self.farm, name='Pondeuses', max_capacity=2000)
        self.broilers = PoultryHouse.objects.create(house_code=f'H-BRO-{self.farm.id}', farm=self.farm, name='Chair', max_capacity=600)
        admin = User.objects.create_user(email='admin@filtre.local', password='x', name='A', role=UserRole.ADMIN, farm=self.farm)
        create_role_profile(admin)
        self.client.force_authenticate(user=admin)

        start = dt.date(2025, 3, 1)
        self.layer_batch = PoultryBatch.objects.create(
            batch_code=f'B-LAY-{self.farm.id}', house=self.layers, production_type=ProductionType.LAYER,
            initial_count=2000, start_date=start, status=BatchStatus.ACTIVE,
        )
        for i in range(25):  # 25 closed broiler cycles, all started after the layer flock
            PoultryBatch.objects.create(
                batch_code=f'B-BRO-{self.farm.id}-{i}', house=self.broilers, production_type=ProductionType.BROILER,
                initial_count=600, start_date=start + dt.timedelta(days=14 * (i + 1)), status=BatchStatus.CLOSED,
            )

    @staticmethod
    def rows(response):
        return response.data['results'] if isinstance(response.data, dict) else response.data

    def test_the_unfiltered_first_page_really_misses_the_old_active_batch(self):
        codes = [r['batch_code'] for r in self.rows(self.client.get('/api/batches/'))]
        self.assertNotIn(self.layer_batch.batch_code, codes)

    def test_status_active_returns_the_old_active_batch(self):
        rows = self.rows(self.client.get('/api/batches/', {'status': 'ACTIVE'}))
        self.assertEqual([r['batch_code'] for r in rows], [self.layer_batch.batch_code])

    def test_status_combines_with_house_code(self):
        rows = self.rows(self.client.get('/api/batches/', {'status': 'ACTIVE', 'house_code': self.broilers.house_code}))
        self.assertEqual(rows, [])

    def test_an_unknown_status_is_refused_in_french(self):
        response = self.client.get('/api/batches/', {'status': 'nimportequoi'})
        self.assertEqual(response.status_code, 400)
        self.assertIn('Statut inconnu', str(response.data))


class DailyLogWeighedFilterTests(APITestCase):
    """GET /api/batches/{code}/daily-logs/?weighed=1 — "Pesées récentes".

    Daily logs are ordered oldest first and paginated by 20, so the weighing section's list stopped
    at day 20 of the cycle: from day 21 a new weighing never appeared under the form that saved it.
    """

    def setUp(self):
        self.farm = Farm.objects.create(name='Ferme Pesée')
        house = PoultryHouse.objects.create(house_code=f'H-W-{self.farm.id}', farm=self.farm, name='B1', max_capacity=600)
        admin = User.objects.create_user(email='admin@pesee.local', password='x', name='A', role=UserRole.ADMIN, farm=self.farm)
        create_role_profile(admin)
        self.client.force_authenticate(user=admin)
        start = dt.date(2026, 8, 1)
        self.batch = PoultryBatch.objects.create(
            batch_code=f'B-W-{self.farm.id}', house=house, production_type=ProductionType.BROILER,
            initial_count=600, start_date=start, status=BatchStatus.ACTIVE,
        )
        for day in range(30):
            DailyLog.objects.create(
                batch=self.batch, log_date=start + dt.timedelta(days=day), mortality=0,
                avg_sample_weight=None if day % 3 else 0.04 + day * 0.05,
            )
        self.url = f'/api/batches/{self.batch.batch_code}/daily-logs/'

    def test_weighed_returns_only_weighed_days_newest_first(self):
        rows = self.client.get(self.url, {'weighed': '1'}).data['results']
        dates = [r['log_date'] for r in rows]
        self.assertEqual(dates[0], '2026-08-28')  # day 27, the last weighed day
        self.assertEqual(dates, sorted(dates, reverse=True))
        self.assertTrue(all(r['avg_sample_weight'] is not None for r in rows))
        self.assertEqual(len(rows), 10)

    def test_without_the_flag_the_list_is_unchanged(self):
        response = self.client.get(self.url)
        self.assertEqual(response.data['count'], 30)
        self.assertEqual(response.data['results'][0]['log_date'], '2026-08-01')
