"""Batch creation refuses values no real flock can have — through both creation paths.

Campaign 9 (exploratory, finding B4/B7): POST /api/batches/ accepted 0 birds, 10^9 birds in a
100-bird house, a start in 1900 (day 46 289 of the cycle) or in 2200 (day -63 284) and a planned
end before the start. POST /api/protocols/onboarding/ — the path the UI actually uses for
"+ Nouvelle bande" — validated nothing at all: seven inputs answered 500 (DataError,
IntegrityError, ValueError, OverflowError, KeyError) and the rest were stored as given,
including an empty house name and a production type of "DRAGON".
"""
import datetime as dt

from django.utils import timezone
from rest_framework.test import APITestCase

from apps.batches.models import PoultryBatch
from apps.core.models import Farm, User, UserRole, create_role_profile
from apps.houses.models import PoultryHouse

LINE = [{'categoryIndex': 0, 'from_value': 0, 'from_unit': 'DAY', 'until_end': True, 'what': 'x', 'details': ''}]


class BatchValidationBase(APITestCase):
    def setUp(self):
        self.farm = Farm.objects.create(name='Ferme Validation')
        admin = User.objects.create_user(email='admin@valid.local', password='x', name='A', role=UserRole.ADMIN, farm=self.farm)
        create_role_profile(admin)
        self.client.force_authenticate(user=admin)
        self.today = timezone.localdate()


class BatchesEndpointTests(BatchValidationBase):
    def setUp(self):
        super().setUp()
        self.house = PoultryHouse.objects.create(house_code=f'H-{self.farm.id}-001', farm=self.farm, name='A', max_capacity=100)

    def post(self, **over):
        body = {'name': 'Bande', 'house_code': self.house.house_code, 'production_type': 'BROILER',
                'initial_count': 50, 'start_date': self.today.isoformat(), **over}
        return self.client.post('/api/batches/', body, format='json')

    def assertRefused(self, response, field):
        self.assertEqual(response.status_code, 400, response.content[:300])
        self.assertIn(field, response.data)
        self.assertFalse(PoultryBatch.objects.exists())

    def test_a_valid_batch_is_still_created(self):
        self.assertEqual(self.post().status_code, 201)

    def test_zero_birds(self):
        self.assertRefused(self.post(initial_count=0), 'initial_count')

    def test_more_birds_than_the_house_holds(self):
        self.assertRefused(self.post(initial_count=101), 'initial_count')

    def test_exactly_the_capacity_is_fine(self):
        self.assertEqual(self.post(initial_count=100).status_code, 201)

    def test_start_in_1900(self):
        self.assertRefused(self.post(start_date='1900-01-01'), 'start_date')

    def test_start_in_2200(self):
        self.assertRefused(self.post(start_date='2200-01-01'), 'start_date')

    def test_planned_end_before_start(self):
        self.assertRefused(self.post(planned_end_date=(self.today - dt.timedelta(days=1)).isoformat()), 'planned_end_date')

    def test_a_layer_flock_started_18_months_ago_is_fine(self):
        self.assertEqual(self.post(start_date=(self.today - dt.timedelta(days=540)).isoformat()).status_code, 201)


class OnboardingEndpointTests(BatchValidationBase):
    def post(self, house=None, batch=None):
        body = {'house': {'name': 'Bâtiment', 'maxCapacity': 100, **(house or {})},
                'batch': {'name': 'Bande', 'initialCount': 50, 'startDate': self.today.isoformat(),
                          'productionType': 'BROILER', 'growthCycleValue': 45, 'growthCycleUnit': 'DAY', **(batch or {})},
                'protocolLines': LINE}
        return self.client.post('/api/protocols/onboarding/', body, format='json')

    def assertRefused(self, response):
        self.assertEqual(response.status_code, 400, response.content[:300])
        self.assertFalse(PoultryHouse.objects.exists(), 'nothing may be half-created')

    def test_a_valid_request_is_still_created(self):
        response = self.post()
        self.assertEqual(response.status_code, 201, response.content[:300])
        self.assertEqual(PoultryBatch.objects.get().planned_end_date, self.today + dt.timedelta(days=45))

    def test_house_without_a_batch_is_still_allowed(self):
        body = {'house': {'name': 'Vide', 'maxCapacity': 10}, 'protocolLines': LINE}
        self.assertEqual(self.client.post('/api/protocols/onboarding/', body, format='json').status_code, 201)

    def test_house_name_too_long(self):
        self.assertRefused(self.post(house={'name': 'H' * 10000}))

    def test_house_name_empty(self):
        self.assertRefused(self.post(house={'name': '   '}))

    def test_negative_capacity(self):
        self.assertRefused(self.post(house={'maxCapacity': -5}))

    def test_capacity_not_a_number(self):
        self.assertRefused(self.post(house={'maxCapacity': 'abc'}))

    def test_negative_birds(self):
        self.assertRefused(self.post(batch={'initialCount': -5}))

    def test_birds_not_a_number(self):
        self.assertRefused(self.post(batch={'initialCount': 'abc'}))

    def test_more_birds_than_capacity(self):
        self.assertRefused(self.post(batch={'initialCount': 10 ** 9}))

    def test_start_in_1900_and_2200(self):
        self.assertRefused(self.post(batch={'startDate': '1900-01-01'}))
        self.assertRefused(self.post(batch={'startDate': '2200-01-01'}))

    def test_batch_name_too_long(self):
        self.assertRefused(self.post(batch={'name': 'B' * 10000}))

    def test_negative_or_absurd_growth_cycle(self):
        self.assertRefused(self.post(batch={'growthCycleValue': -10}))
        self.assertRefused(self.post(batch={'growthCycleValue': 10 ** 9}))
        self.assertRefused(self.post(batch={'growthCycleValue': 'abc'}))

    def test_unknown_production_type_and_weighing_frequency(self):
        self.assertRefused(self.post(batch={'productionType': 'DRAGON'}))
        self.assertRefused(self.post(batch={'weighingFrequency': 'HOURLY'}))

    def test_unknown_cycle_unit(self):
        self.assertRefused(self.post(batch={'growthCycleUnit': 'YEAR'}))

    def test_errors_are_french_and_keyed_by_section(self):
        response = self.post(batch={'initialCount': 10 ** 9})
        self.assertIn('batch', response.data)
        self.assertIn('capacité', str(response.data['batch']))
