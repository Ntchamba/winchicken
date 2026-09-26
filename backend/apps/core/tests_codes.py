"""Server-generated codes (`H-2-003`, `BATCH-2026-004`, `FEE-2-007`, ...) after a deletion.

Every generator used to be "count the rows, add one". Delete any row that is not the newest
and the count falls back onto a code that is still in use: the next create hit the primary key
and answered 500 — not once but on every later attempt, because the count never moves again.
On the farm that read as "Nouveau bâtiment" being broken for good after one house was removed
(campaign 9, exploratory finding B1).
"""
import datetime as dt

from django.db import IntegrityError
from rest_framework.test import APITestCase

from apps.batches.models import BatchStatus, PoultryBatch
from apps.core.codes import create_with_code, next_sequential_code
from apps.core.models import Farm, User, UserRole, create_role_profile
from apps.houses.models import PoultryHouse
from apps.stock.models import StockCategory, StockItem


class NextSequentialCodeTests(APITestCase):
    def setUp(self):
        self.farm = Farm.objects.create(name='Ferme Codes')

    def house(self, code):
        return PoultryHouse.objects.create(house_code=code, farm=self.farm, name=code, max_capacity=10)

    def test_first_code_starts_at_one(self):
        self.assertEqual(next_sequential_code(PoultryHouse, 'house_code', 'H-9-'), 'H-9-001')

    def test_follows_the_highest_suffix_not_the_row_count(self):
        self.house('H-9-001')
        self.house('H-9-003')  # 002 was deleted: count+1 would hand out 003 again
        self.assertEqual(next_sequential_code(PoultryHouse, 'house_code', 'H-9-'), 'H-9-004')

    def test_ignores_other_prefixes_and_non_numeric_suffixes(self):
        self.house('H-91-050')  # a different farm id that merely starts with the same digit
        self.house('H-9-legacy')
        self.assertEqual(next_sequential_code(PoultryHouse, 'house_code', 'H-9-'), 'H-9-001')

    def test_width_grows_past_the_padding(self):
        self.house('H-9-999')
        self.assertEqual(next_sequential_code(PoultryHouse, 'house_code', 'H-9-'), 'H-9-1000')

    def test_create_with_code_retries_a_collision(self):
        self.house('H-9-001')
        codes = iter(['H-9-001', 'H-9-002'])  # the first attempt loses the race
        made = create_with_code(lambda: self.house(next(codes)))
        self.assertEqual(made.house_code, 'H-9-002')

    def test_create_with_code_gives_up_eventually(self):
        self.house('H-9-001')
        with self.assertRaises(IntegrityError):
            create_with_code(lambda: self.house('H-9-001'), attempts=3)


class CreateAfterDeleteApiTests(APITestCase):
    def setUp(self):
        self.farm = Farm.objects.create(name='Ferme Suppression')
        admin = User.objects.create_user(email='admin@codes.local', password='x', name='A', role=UserRole.ADMIN, farm=self.farm)
        create_role_profile(admin)
        self.client.force_authenticate(user=admin)

    def new_house(self, name):
        response = self.client.post('/api/houses/', {'name': name, 'max_capacity': 100}, format='json')
        self.assertEqual(response.status_code, 201, response.content[:300])
        return response.data['house_code']

    def test_house_can_be_created_after_deleting_an_older_one(self):
        first, second = self.new_house('A'), self.new_house('B')
        self.assertEqual(self.client.delete(f'/api/houses/{first}/').status_code, 204)
        third = self.new_house('C')
        self.assertNotIn(third, (first, second))
        self.new_house('D')  # and it keeps working, not just once

    def test_batch_can_be_created_after_its_older_sibling_house_is_deleted(self):
        houses = [self.new_house(n) for n in 'ABC']
        codes = []
        for h in houses[:2]:
            r = self.client.post('/api/batches/', {'name': h, 'house_code': h, 'production_type': 'BROILER',
                                                    'initial_count': 10, 'start_date': dt.date.today().isoformat()}, format='json')
            self.assertEqual(r.status_code, 201, r.content[:300])
            codes.append(r.data['batch_code'])
        self.client.delete(f'/api/houses/{houses[0]}/')  # cascades the first batch
        r = self.client.post('/api/batches/', {'name': 'C', 'house_code': houses[2], 'production_type': 'BROILER',
                                                'initial_count': 10, 'start_date': dt.date.today().isoformat()}, format='json')
        self.assertEqual(r.status_code, 201, r.content[:300])
        self.assertNotIn(r.data['batch_code'], codes)
        self.assertEqual(PoultryBatch.objects.filter(status=BatchStatus.ACTIVE).count(), 2)

    def test_stock_item_code_follows_the_highest_not_the_count(self):
        category = StockCategory.objects.filter(farm=self.farm, kind='FEED').first() or StockCategory.objects.create(
            farm=self.farm, label='Aliment', kind='FEED')
        StockItem.objects.create(item_code=f'FEE-{self.farm.id}-002', farm=self.farm, category=category, name='Seul', unit='kg')
        r = self.client.post(f'/api/farms/{self.farm.id}/stock-items/', {'name': 'Nouveau', 'unit': 'kg', 'kind': 'FEED'}, format='json')
        self.assertEqual(r.status_code, 201, r.content[:300])
        self.assertEqual(r.data['item_code'], f'FEE-{self.farm.id}-003')
