"""Daily figures and manual stock movements refuse values nothing on a farm can produce.

Campaign 9 (exploratory): the quick entry stored an average sample weight of 10 000 kg and of
1e300 kg, and 1 000 000 000 eggs from 797 broilers (B3); POST /daily-logs/ for a day already
logged answered 500 (B2); a manual stock IN of -5 and a movement dated 2200 were stored (B6).
"""
import datetime as dt

from django.utils import timezone
from rest_framework.test import APITestCase

from apps.batches.models import BatchStatus, DailyLog, PoultryBatch, ProductionType
from apps.core.models import Farm, User, UserRole, create_role_profile
from apps.houses.models import PoultryHouse
from apps.stock.models import StockCategory, StockItem, StockMovement


class PlausibilityBase(APITestCase):
    def setUp(self):
        self.farm = Farm.objects.create(name='Ferme Plausible')
        admin = User.objects.create_user(email='admin@plaus.local', password='x', name='A', role=UserRole.ADMIN, farm=self.farm)
        create_role_profile(admin)
        self.client.force_authenticate(user=admin)
        self.today = timezone.localdate()
        house = PoultryHouse.objects.create(house_code=f'H-{self.farm.id}-001', farm=self.farm, name='A', max_capacity=100)
        self.batch = PoultryBatch.objects.create(
            batch_code=f'B-PL-{self.farm.id}', house=house, production_type=ProductionType.LAYER, name='Pondeuses',
            initial_count=100, start_date=self.today - dt.timedelta(days=10), status=BatchStatus.ACTIVE,
        )
        self.quick = f'/api/batches/{self.batch.batch_code}/daily-logs/quick-entry/'
        self.logs = f'/api/batches/{self.batch.batch_code}/daily-logs/'

    def put(self, **body):
        return self.client.put(self.quick, {'date': self.today.isoformat(), **body}, format='json')


class QuickEntryPlausibilityTests(PlausibilityBase):
    def test_a_real_weight_is_stored(self):
        self.assertEqual(self.put(avgSampleWeight=1.85).status_code, 200)
        self.assertEqual(DailyLog.objects.get().avg_sample_weight, 1.85)

    def test_grams_typed_as_kilos_are_refused_with_a_hint(self):
        response = self.put(avgSampleWeight=1500)
        self.assertEqual(response.status_code, 400)
        self.assertIn('kilos', response.data['detail'])
        self.assertFalse(DailyLog.objects.exists())

    def test_absurd_weights_are_refused(self):
        for weight in (10000, 1e300, 15.01):
            self.assertEqual(self.put(avgSampleWeight=weight).status_code, 400, weight)

    def test_eggs_up_to_the_flock_are_fine_beyond_are_not(self):
        self.assertEqual(self.put(eggsCollected=100).status_code, 200)
        self.assertEqual(self.put(eggsCollected=101).status_code, 400)
        self.assertEqual(self.put(eggsCollected=10 ** 9).status_code, 400)
        self.assertEqual(DailyLog.objects.get().eggs_collected, 100)

    def test_eggs_ceiling_follows_the_day_mortality(self):
        self.assertEqual(self.put(mortality=10, eggsCollected=91).status_code, 400)
        self.assertEqual(self.put(mortality=10, eggsCollected=90).status_code, 200)


class DailyLogPostTests(PlausibilityBase):
    def test_a_second_post_for_the_same_day_is_a_400_not_a_500(self):
        day = self.today.isoformat()
        self.assertEqual(self.client.post(self.logs, {'log_date': day, 'mortality': 1}, format='json').status_code, 201)
        response = self.client.post(self.logs, {'log_date': day, 'mortality': 2}, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertIn('log_date', response.data)
        self.assertEqual(DailyLog.objects.get().mortality, 1)

    def test_weight_rule_applies_here_too(self):
        response = self.client.post(self.logs, {'log_date': self.today.isoformat(), 'avg_sample_weight': 10000}, format='json')
        self.assertEqual(response.status_code, 400)


class ManualStockMovementTests(PlausibilityBase):
    def setUp(self):
        super().setUp()
        category = StockCategory.objects.create(farm=self.farm, label='Aliment', kind='FEED')
        self.item = StockItem.objects.create(item_code=f'FEE-{self.farm.id}-001', farm=self.farm, category=category, name='Provende', unit='kg')

    def post(self, **over):
        body = {'item': self.item.item_code, 'movement_type': 'IN', 'quantity': 5, 'movement_date': self.today.isoformat(), **over}
        return self.client.post('/api/stock-movements/', body, format='json')

    def test_a_real_restock_is_stored(self):
        self.assertEqual(self.post().status_code, 201)

    def test_negative_and_zero_quantities_are_refused(self):
        for q in (-5, 0):
            self.assertEqual(self.post(quantity=q).status_code, 400, q)
            self.assertEqual(self.post(quantity=q, movement_type='OUT').status_code, 400, q)
        self.assertFalse(StockMovement.objects.exists())

    def test_a_future_date_is_refused(self):
        self.assertEqual(self.post(movement_date='2200-01-01').status_code, 400)
        self.assertEqual(self.post(movement_date=(self.today + dt.timedelta(days=1)).isoformat()).status_code, 400)


class StockItemParameterTests(PlausibilityBase):
    """The stock form's PUT and the Excel import stored a -50 alert threshold and a -100 FCFA
    unit price (campaign 9, finding B9)."""

    def setUp(self):
        super().setUp()
        self.category = StockCategory.objects.create(farm=self.farm, label='Aliment', kind='FEED')

    def put(self, **over):
        row = {'category': self.category.id, 'name': 'Provende', 'unit': 'kg', 'alert_threshold': 5, 'unit_price': '450', **over}
        return self.client.put(f'/api/farms/{self.farm.id}/stock-items/', {'items': [row]}, format='json')

    def test_real_parameters_are_saved(self):
        self.assertEqual(self.put().status_code, 200)

    def test_negative_threshold_or_price_is_refused(self):
        response = self.put(alert_threshold=-50)
        self.assertEqual(response.status_code, 400)
        self.assertIn("Article « Provende » — Seuil d'alerte", response.data['detail'])
        self.assertEqual(self.put(unit_price='-100').status_code, 400)
        self.assertFalse(StockItem.objects.exists())

    def test_raw_values_that_used_to_crash_are_400_per_line(self):
        for over in ({'name': 'Z' * 10000}, {'alert_threshold': 'abc'}, {'unit_price': '100000000000000000000'}):
            response = self.put(**over)
            self.assertEqual(response.status_code, 400, over)
            self.assertIn('0', response.data['items'])
        row = {'category': self.category.id, 'unit': 'kg'}  # no name at all
        response = self.client.put(f'/api/farms/{self.farm.id}/stock-items/', {'items': [row]}, format='json')
        self.assertEqual(response.status_code, 400)

    def test_a_blank_unit_is_still_accepted_as_before(self):
        self.assertEqual(self.put(unit='').status_code, 200)
