from datetime import date, timedelta

from rest_framework import status
from rest_framework.test import APITestCase

from apps.alerts.models import Alert, AlertRuleType
from apps.batches.models import BatchStatus, DailyLog, PoultryBatch, ProductionType
from apps.core.models import Farm, User, UserRole, create_role_profile
from apps.houses.models import PoultryHouse
from apps.protocols.models import ProtocolCategory, ProtocolTemplate
from apps.stock.calculations import current_quantity, stock_evolution
from apps.stock.models import MovementType, StockCategory, StockItem, StockMovement, Supplier
from apps.stock.services import run_daily_consumption


def _make_user(farm, role=UserRole.ADMIN, email='admin@stock-test.local'):
    user = User.objects.create_user(email=email, password='x', name='U', role=role, farm=farm)
    create_role_profile(user)
    return user


class StockCategorySeedingTests(APITestCase):
    def test_new_farm_seeds_four_stock_categories(self):
        farm = Farm.objects.create(name='Ferme Seed')
        cats = StockCategory.objects.filter(farm=farm)
        self.assertEqual(cats.count(), 4)
        self.assertEqual(
            set(cats.values_list('kind', flat=True)),
            {'FEED', 'VETERINARY', 'EQUIPMENT', 'BEDDING'},
        )
        self.assertEqual([c.label for c in cats.order_by('sort_order')],
                         ['Aliment', 'Vétérinaire', 'Équipement', 'Litière'])


class StockCategoryApiTests(APITestCase):
    def setUp(self):
        self.farm = Farm.objects.create(name='Ferme Cat API')
        self.admin = _make_user(self.farm)
        self.worker = _make_user(self.farm, role=UserRole.WORKER, email='worker@stock-test.local')
        self.client.force_authenticate(user=self.admin)

    def test_add_custom_category_appends_and_is_custom_kind(self):
        resp = self.client.post(
            f'/api/farms/{self.farm.id}/stock-categories/', {'label': 'Biosécurité', 'icon': 'ShoppingCart'}, format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        self.assertEqual(resp.data['kind'], 'CUSTOM')
        self.assertEqual(resp.data['sort_order'], 4)

    def test_add_category_rejects_unknown_icon(self):
        resp = self.client.post(
            f'/api/farms/{self.farm.id}/stock-categories/', {'label': 'X', 'icon': 'NotARealIcon'}, format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_worker_cannot_add_category(self):
        self.client.force_authenticate(user=self.worker)
        resp = self.client.post(
            f'/api/farms/{self.farm.id}/stock-categories/', {'label': 'X', 'icon': 'Package'}, format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_delete_category_cascades_its_items(self):
        cat = StockCategory.objects.get(farm=self.farm, kind='FEED')
        StockItem.objects.create(item_code='FEE-1-001', farm=self.farm, category=cat, name='Aliment', unit='kg')
        resp = self.client.delete(f'/api/stock-categories/{cat.id}/')
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(StockItem.objects.filter(item_code='FEE-1-001').exists())

    def test_put_items_with_custom_category_id(self):
        cat = StockCategory.objects.create(farm=self.farm, label='Divers', icon='Package', sort_order=9)
        resp = self.client.put(
            f'/api/farms/{self.farm.id}/stock-items/',
            {'items': [{'category': cat.id, 'name': 'Bidon', 'unit': 'unité', 'alert_threshold': 2}]},
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        self.assertEqual(resp.data['items'][0]['category'], cat.id)
        self.assertEqual(resp.data['items'][0]['category_kind'], 'CUSTOM')
        self.assertTrue(resp.data['items'][0]['item_code'].startswith('CUS-'))


class SupplierApiTests(APITestCase):
    def setUp(self):
        self.farm = Farm.objects.create(name='Ferme Supplier')
        self.admin = _make_user(self.farm)
        self.client.force_authenticate(user=self.admin)

    def test_supplier_crud_and_item_link(self):
        create = self.client.post(
            f'/api/farms/{self.farm.id}/suppliers/',
            {'name': 'Provende SARL', 'contact': '+237600000000', 'email': 'contact@provende.example'}, format='json',
        )
        self.assertEqual(create.status_code, status.HTTP_201_CREATED, create.data)
        supplier_id = create.data['id']

        cat = StockCategory.objects.get(farm=self.farm, kind='FEED')
        self.client.put(
            f'/api/farms/{self.farm.id}/stock-items/',
            {'items': [{'category': cat.id, 'name': 'Aliment démarrage', 'unit': 'kg', 'supplier': supplier_id}]},
            format='json',
        )

        listing = self.client.get(f'/api/farms/{self.farm.id}/suppliers/')
        row = listing.data['results'][0] if 'results' in listing.data else listing.data[0]
        self.assertEqual(row['item_names'], ['Aliment démarrage'])

        deleted = self.client.delete(f'/api/suppliers/{supplier_id}/')
        self.assertEqual(deleted.status_code, status.HTTP_204_NO_CONTENT)
        # Item survives, supplier link nulled (SET_NULL).
        item = StockItem.objects.get(name='Aliment démarrage')
        self.assertIsNone(item.supplier_id)


class StockEvolutionTests(APITestCase):
    def setUp(self):
        self.farm = Farm.objects.create(name='Ferme Evolution')
        self.admin = _make_user(self.farm)
        self.client.force_authenticate(user=self.admin)
        self.cat = StockCategory.objects.get(farm=self.farm, kind='FEED')
        self.item = StockItem.objects.create(
            item_code='FEE-1-001', farm=self.farm, category=self.cat, name='Aliment', unit='kg', alert_threshold=50,
        )

    def test_running_balance_by_calendar_date(self):
        StockMovement.objects.create(item=self.item, movement_type=MovementType.IN, quantity=100, movement_date=date(2026, 1, 1))
        StockMovement.objects.create(item=self.item, movement_type=MovementType.OUT, quantity=30, movement_date=date(2026, 1, 3))
        StockMovement.objects.create(item=self.item, movement_type=MovementType.IN, quantity=10, movement_date=date(2026, 1, 5))

        series = stock_evolution(self.farm)
        self.assertEqual(len(series), 1)
        entry = series[0]
        self.assertEqual(entry['alertThreshold'], 50)
        self.assertEqual(entry['points'], [
            {'date': '2026-01-01', 'quantity': 100.0},
            {'date': '2026-01-03', 'quantity': 70.0},
            {'date': '2026-01-05', 'quantity': 80.0},
        ])

    def test_endpoint_empty_points_when_no_movements(self):
        resp = self.client.get(f'/api/farms/{self.farm.id}/stock-evolution/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data[0]['points'], [])


class DailyConsumptionTests(APITestCase):
    def setUp(self):
        self.farm = Farm.objects.create(name='Ferme Consumption')
        self.house = PoultryHouse.objects.create(house_code='H-C-1', farm=self.farm, name='Salle', max_capacity=1000)
        self.category = ProtocolCategory.objects.create(house=self.house, label='Alimentation', icon='Soup')
        self.cat = StockCategory.objects.get(farm=self.farm, kind='FEED')
        self.item = StockItem.objects.create(
            item_code='FEE-1-001', farm=self.farm, category=self.cat, name='Aliment démarrage', unit='kg',
            alert_threshold=50,
        )
        self.today = date(2026, 3, 10)
        # Batch started 9 days ago → day_of_cycle == 9 today; line covers day 1..15.
        self.batch = PoultryBatch.objects.create(
            batch_code='BATCH-C-1', house=self.house, production_type=ProductionType.BROILER,
            initial_count=500, start_date=self.today - timedelta(days=9), status=BatchStatus.ACTIVE,
        )
        self.line = ProtocolTemplate.objects.create(
            house=self.house, category=self.category, from_value=1, from_unit='DAY',
            to_value=15, to_unit='DAY', what='Aliment démarrage', stock_item=self.item, quantity_per_day=40,
        )

    def test_creates_one_out_per_matching_row(self):
        created = run_daily_consumption(today=self.today)
        self.assertEqual(len(created), 1)
        mv = created[0]
        self.assertEqual(mv.movement_type, MovementType.OUT)
        self.assertEqual(mv.quantity, 40)
        self.assertEqual(mv.movement_date, self.today)
        self.assertEqual(mv.batch_id, self.batch.batch_code)
        self.assertEqual(mv.protocol_line_id, self.line.id)

    def test_is_idempotent_same_day(self):
        run_daily_consumption(today=self.today)
        second = run_daily_consumption(today=self.today)
        self.assertEqual(second, [])
        self.assertEqual(
            StockMovement.objects.filter(item=self.item, batch=self.batch, movement_date=self.today).count(), 1,
        )

    def test_nothing_created_when_day_outside_range(self):
        outside = self.batch.start_date + timedelta(days=40)  # day_of_cycle 40, line ends at 15
        created = run_daily_consumption(today=outside)
        self.assertEqual(created, [])

    def test_closed_batch_ignored(self):
        self.batch.status = BatchStatus.CLOSED
        self.batch.save(update_fields=['status'])
        self.assertEqual(run_daily_consumption(today=self.today), [])

    def test_triggers_low_stock_alert_when_threshold_crossed(self):
        # 60 on hand, threshold 50, daily draw 40 → after today's OUT, 20 < 50 → LOW_STOCK.
        StockMovement.objects.create(item=self.item, movement_type=MovementType.IN, quantity=60, movement_date=self.today - timedelta(days=1))
        run_daily_consumption(today=self.today)
        self.assertEqual(current_quantity(self.item), 20)
        self.assertTrue(
            Alert.objects.filter(rule__rule_type=AlertRuleType.LOW_STOCK, rule__farm=self.farm).exists()
        )

    def test_management_command_runs(self):
        from django.core.management import call_command
        from io import StringIO

        out = StringIO()
        call_command('run_stock_consumption', '--date', self.today.isoformat(), stdout=out)
        self.assertIn('1 stock movement(s) created', out.getvalue())

    def test_dose_per_bird_scales_with_current_count(self):
        # "Dose par bande" mode: quantity == dose_per_bird * batch.current_count (500 birds).
        self.line.quantity_per_day = None
        self.line.dose_per_bird = 0.5
        self.line.save(update_fields=['quantity_per_day', 'dose_per_bird'])
        created = run_daily_consumption(today=self.today)
        self.assertEqual(len(created), 1)
        self.assertEqual(created[0].quantity, 250)

    def test_dose_per_bird_skips_empty_batch(self):
        # All birds dead → current_count 0 → computed quantity 0 → no movement.
        DailyLog.objects.create(batch=self.batch, log_date=self.today, mortality=self.batch.initial_count)
        self.line.quantity_per_day = None
        self.line.dose_per_bird = 0.5
        self.line.save(update_fields=['quantity_per_day', 'dose_per_bird'])
        self.assertEqual(run_daily_consumption(today=self.today), [])


class CoverageEndpointTests(APITestCase):
    def setUp(self):
        self.farm = Farm.objects.create(name='Ferme Coverage')
        self.admin = _make_user(self.farm)
        self.client.force_authenticate(user=self.admin)
        self.cat = StockCategory.objects.get(farm=self.farm, kind='FEED')
        self.item = StockItem.objects.create(
            item_code='FEE-1-001', farm=self.farm, category=self.cat, name='Aliment', unit='kg',
        )
        StockMovement.objects.create(item=self.item, movement_type=MovementType.IN, quantity=100, movement_date=date(2026, 1, 1))

    def test_insufficient_when_days_needed_exceeds_days_remaining(self):
        resp = self.client.get(
            f'/api/stock-items/{self.item.item_code}/coverage/', {'quantity_per_day': 40, 'days': 10},
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['currentQuantity'], 100)
        self.assertEqual(resp.data['daysRemaining'], 2.5)
        self.assertEqual(resp.data['daysNeeded'], 10)
        self.assertFalse(resp.data['sufficient'])

    def test_sufficient_when_stock_covers_period(self):
        resp = self.client.get(
            f'/api/stock-items/{self.item.item_code}/coverage/', {'quantity_per_day': 5, 'days': 10},
        )
        self.assertTrue(resp.data['sufficient'])

    def test_dose_per_bird_coverage_scales_with_live_birds(self):
        house = PoultryHouse.objects.create(house_code='H-COV-1', farm=self.farm, name='S', max_capacity=1000)
        PoultryBatch.objects.create(
            batch_code='B-COV-1', house=house, production_type=ProductionType.BROILER,
            initial_count=200, start_date=date(2026, 1, 1), status=BatchStatus.ACTIVE,
        )
        # 100 on hand, 0.5/bird * 200 birds = 100/day → 1 day of cover, need 10 → insufficient.
        resp = self.client.get(
            f'/api/stock-items/{self.item.item_code}/coverage/', {'dose_per_bird': 0.5, 'days': 10},
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['dailyRate'], 100)
        self.assertEqual(resp.data['daysRemaining'], 1.0)
        self.assertFalse(resp.data['sufficient'])


class ManualStockMovementTests(APITestCase):
    def setUp(self):
        self.farm = Farm.objects.create(name='Ferme Manual')
        self.admin = _make_user(self.farm)
        self.client.force_authenticate(user=self.admin)
        self.cat = StockCategory.objects.get(farm=self.farm, kind='EQUIPMENT')
        self.item = StockItem.objects.create(
            item_code='EQU-1-001', farm=self.farm, category=self.cat, name='Abreuvoir', unit='unité',
        )

    def test_manual_in_movement_with_note_adds_stock(self):
        resp = self.client.post('/api/stock-movements/', {
            'item': self.item.item_code, 'movement_type': 'IN', 'quantity': 12,
            'movement_date': '2026-04-01', 'note': 'Don coopérative',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        mv = StockMovement.objects.get(id=resp.data['id'])
        self.assertEqual(mv.note, 'Don coopérative')
        self.assertIsNone(mv.batch_id)
        self.assertIsNone(mv.protocol_line_id)
        self.assertEqual(current_quantity(self.item), 12)

    def test_worker_cannot_create_movement(self):
        worker = _make_user(self.farm, role=UserRole.WORKER, email='worker@stock-test.local')
        self.client.force_authenticate(user=worker)
        resp = self.client.post('/api/stock-movements/', {
            'item': self.item.item_code, 'movement_type': 'IN', 'quantity': 1, 'movement_date': '2026-04-01',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
