"""No NaN or infinite quantity reaches the database, through any door.

Python's float() — and DRF's FloatField, which uses it — accepts "nan", "inf", "-inf" and "1e400"
(which overflows to inf), and Postgres stores all of them. One such row poisons every total that
sums it: a NaN sale quantity makes the sale's total Decimal('NaN'), every finance figure NaN, and
the JSON the Finances page reads invalid. These tests knock on each door: the serializer field
mapping, the stock-movement and sale APIs, the daily quick entry, the Excel number parser and
the coverage query.
"""
import datetime as dt
from decimal import Decimal
from unittest.mock import patch

from django.test import SimpleTestCase
from rest_framework import serializers
from rest_framework.test import APITestCase

from apps.batches.models import BatchStatus, PoultryBatch, ProductionType
from apps.core.fields import FiniteFloatField
from apps.core.models import Farm, User, UserRole, create_role_profile
from apps.core.xlsx import as_number
from apps.finance.models import Sale
from apps.houses.models import PoultryHouse
from apps.stock.models import StockCategory, StockItem, StockMovement

NOT_FINITE = ['nan', 'NaN', 'inf', '-inf', 'Infinity', '1e400']


class FiniteFloatFieldTests(SimpleTestCase):
    def test_refuses_every_non_finite_spelling_in_french(self):
        field = FiniteFloatField()
        for raw in NOT_FINITE + [float('nan'), float('inf')]:
            with self.assertRaises(serializers.ValidationError, msg=raw) as ctx:
                field.run_validation(raw)
            self.assertIn('nombre', str(ctx.exception.detail[0]))

    def test_accepts_ordinary_numbers(self):
        field = FiniteFloatField()
        self.assertEqual(field.run_validation('12.5'), 12.5)
        self.assertEqual(field.run_validation(0), 0.0)
        self.assertEqual(field.run_validation(-3), -3.0)

    def test_every_model_float_field_is_mapped_to_it(self):
        from apps.finance.serializers import SaleSerializer
        from apps.stock.serializers import StockMovementSerializer
        self.assertIsInstance(SaleSerializer().fields['quantity'], FiniteFloatField)
        self.assertIsInstance(StockMovementSerializer().fields['quantity'], FiniteFloatField)
        self.assertIsInstance(StockMovementSerializer().fields['production_quantity'], FiniteFloatField)


class ExcelNumberTests(SimpleTestCase):
    def test_french_decimals_and_blanks(self):
        self.assertEqual(as_number('12,5'), 12.5)
        self.assertEqual(as_number(' 7 '), 7.0)
        self.assertIsNone(as_number(''))
        self.assertIsNone(as_number(None))
        self.assertIsNone(as_number('douze'))

    def test_non_finite_cells_are_not_numbers(self):
        for raw in NOT_FINITE + [float('nan'), float('inf')]:
            self.assertIsNone(as_number(raw), raw)

    def test_the_protocol_import_uses_the_same_parser(self):
        from apps.protocols.xlsx_import import _as_number
        for raw in ['12,5', 'nan', '1e400', '', None]:
            self.assertEqual(_as_number(raw), as_number(raw), raw)


class ApiDoorsTests(APITestCase):
    def setUp(self):
        self.farm = Farm.objects.create(name='Ferme Nombres')
        admin = User.objects.create_user(email='admin@nb.local', password='x', name='A', role=UserRole.ADMIN, farm=self.farm)
        create_role_profile(admin)
        self.client.force_authenticate(user=admin)
        feed = StockCategory.objects.get(farm=self.farm, kind='FEED')
        self.item = StockItem.objects.create(
            item_code=f'NB-{self.farm.id}', farm=self.farm, category=feed, name='Aliment', unit='kg',
            alert_threshold=0, unit_price=Decimal('1'),
        )
        house = PoultryHouse.objects.create(house_code=f'H-NB-{self.farm.id}', farm=self.farm, name='B', max_capacity=100)
        self.batch = PoultryBatch.objects.create(
            batch_code=f'B-NB-{self.farm.id}', house=house, production_type=ProductionType.BROILER,
            initial_count=100, start_date=dt.date(2026, 9, 1), status=BatchStatus.ACTIVE,
        )

    def test_stock_movement_quantity(self):
        for raw in NOT_FINITE:
            resp = self.client.post('/api/stock-movements/', {
                'item': self.item.item_code, 'movement_type': 'IN', 'quantity': raw, 'movement_date': '2026-09-24',
            }, format='json')
            self.assertEqual(resp.status_code, 400, raw)
        self.assertFalse(StockMovement.objects.exists())

    def test_sale_quantity(self):
        for raw in NOT_FINITE:
            resp = self.client.post('/api/sales/', {
                'product_type': 'BIRD', 'quantity': raw, 'unit_price': '1500', 'sale_date': '2026-09-24',
            }, format='json')
            self.assertEqual(resp.status_code, 400, raw)
        self.assertFalse(Sale.objects.exists())

    def test_quick_entry_answers_400_not_500(self):
        url = f'/api/batches/{self.batch.batch_code}/daily-logs/quick-entry/'
        with patch('django.utils.timezone.localdate', return_value=dt.date(2026, 9, 24)):
            for field in ('mortality', 'eggsCollected', 'avgSampleWeight'):
                for raw in ('inf', 'nan', '1e400'):
                    resp = self.client.put(url, {'date': '2026-09-24', field: raw}, format='json')
                    self.assertEqual(resp.status_code, 400, (field, raw))

    def test_coverage_query(self):
        for raw in ('nan', 'inf'):
            resp = self.client.get(f'/api/stock-items/{self.item.item_code}/coverage/', {'quantity_per_day': raw, 'days': 7})
            self.assertEqual(resp.status_code, 400, raw)
